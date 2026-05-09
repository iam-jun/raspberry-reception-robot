#include "asr/AsrEngine.h"

#include "sherpa-onnx/c-api/cxx-api.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <deque>
#include <limits>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <utility>
#include <vector>

namespace asr {
namespace {

constexpr int kExpectedSampleRate = 16000;
constexpr std::size_t kDecodeChunkSamples = kExpectedSampleRate / 10;

std::string to_utf8_path(const std::filesystem::path& path) {
    return path.u8string();
}

std::string trim_text(std::string text) {
    while (!text.empty() && (text.front() == ' ' || text.front() == '\n' || text.front() == '\r' || text.front() == '\t')) {
        text.erase(text.begin());
    }
    while (!text.empty() && (text.back() == ' ' || text.back() == '\n' || text.back() == '\r' || text.back() == '\t')) {
        text.pop_back();
    }
    return text;
}

float compute_rms(const std::vector<float>& samples) {
    if (samples.empty()) {
        return 0.0F;
    }

    double sum = 0.0;
    for (const auto sample : samples) {
        sum += static_cast<double>(sample) * static_cast<double>(sample);
    }
    return static_cast<float>(std::sqrt(sum / static_cast<double>(samples.size())));
}

float compute_peak(const std::vector<float>& samples) {
    float peak = 0.0F;
    for (const auto sample : samples) {
        peak = (std::max)(peak, std::fabs(sample));
    }
    return peak;
}

} // namespace

std::string to_string(AsrStatus status) {
    switch (status) {
    case AsrStatus::Loading:
        return "loading";
    case AsrStatus::Ready:
        return "ready";
    case AsrStatus::Listening:
        return "listening";
    case AsrStatus::Streaming:
        return "streaming";
    case AsrStatus::Error:
        return "error";
    case AsrStatus::Unloaded:
    default:
        return "unloaded";
    }
}

class AsrEngine::Impl {
public:
    explicit Impl(AsrConfig config) : config_(std::move(config)) {}
    ~Impl() { unload(); }

    void set_callbacks(AsrCallbacks callbacks) {
        std::lock_guard<std::mutex> lock(mutex_);
        callbacks_ = std::move(callbacks);
    }

    void load() {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (loaded_) {
                return;
            }
            set_status_locked(AsrStatus::Loading, "Loading ASR models into RAM");
        }
        notify_status(AsrStatus::Loading, "Loading ASR models into RAM");

        try {
        auto recognizer = create_recognizer();
        auto denoiser = create_denoiser();
        auto vad = create_vad();

        {
            std::lock_guard<std::mutex> lock(mutex_);
            recognizer_ = std::move(recognizer);
            denoiser_ = std::move(denoiser);
            vad_ = std::move(vad);
            loaded_ = true;
            stop_worker_ = false;
            set_status_locked(AsrStatus::Ready, "ASR models loaded and ready");
            worker_ = std::thread(&Impl::worker_loop, this);
        }
        notify_status(AsrStatus::Ready, "ASR models loaded and ready");
        } catch (const std::exception& error) {
            {
                std::lock_guard<std::mutex> lock(mutex_);
                set_status_locked(AsrStatus::Error, error.what());
                loaded_ = false;
            }
            notify_status(AsrStatus::Error, error.what());
            throw;
        }
    }

    void unload() {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (!loaded_ && !worker_.joinable()) {
                clear_runtime_locked(true);
                recognizer_.reset();
                denoiser_.reset();
                vad_.reset();
                status_ = AsrStatus::Unloaded;
                status_message_ = "ASR models unloaded";
                return;
            }
            session_active_ = false;
            stop_session_requested_ = true;
            stop_worker_ = true;
            cv_.notify_all();
        }

        if (worker_.joinable()) {
            worker_.join();
        }

        {
            std::lock_guard<std::mutex> lock(mutex_);
            clear_runtime_locked(true);
            recognizer_.reset();
            denoiser_.reset();
            vad_.reset();
            loaded_ = false;
            stop_worker_ = false;
            set_status_locked(AsrStatus::Unloaded, "ASR models unloaded");
        }
        notify_status(AsrStatus::Unloaded, "ASR models unloaded");
    }

    void start_session() {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            require_loaded_locked();
            clear_runtime_locked(false);
            session_active_ = true;
            start_session_requested_ = true;
            stop_session_requested_ = false;
            set_status_locked(AsrStatus::Listening, "ASR session started; waiting for speech");
            cv_.notify_all();
        }
        notify_status(AsrStatus::Listening, "ASR session started; waiting for speech");
    }

    void stop_session() {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (!loaded_) {
                return;
            }
            session_active_ = false;
            start_session_requested_ = false;
            stop_session_requested_ = true;
            clear_runtime_locked(true);
            set_status_locked(AsrStatus::Ready, "ASR session stopped; models remain loaded");
            cv_.notify_all();
        }
        notify_status(AsrStatus::Ready, "ASR session stopped; models remain loaded");
    }

    void push_audio_f32(const float* samples, std::size_t frame_count, int sample_rate, int channels) {
        if (samples == nullptr || frame_count == 0) {
            return;
        }
        validate_audio_format(sample_rate, channels);

        std::vector<float> mono;
        mono.reserve(frame_count);
        const auto channel_count = channels > 0 ? channels : 1;
        for (std::size_t frame = 0; frame < frame_count; ++frame) {
            mono.push_back(std::clamp(samples[frame * channel_count], -1.0F, 1.0F));
        }

        enqueue_audio(std::move(mono));
    }

    void push_audio_i16(const std::int16_t* samples, std::size_t frame_count, int sample_rate, int channels) {
        if (samples == nullptr || frame_count == 0) {
            return;
        }
        validate_audio_format(sample_rate, channels);

        std::vector<float> mono;
        mono.reserve(frame_count);
        const auto channel_count = channels > 0 ? channels : 1;
        for (std::size_t frame = 0; frame < frame_count; ++frame) {
            mono.push_back(static_cast<float>(samples[frame * channel_count]) / 32768.0F);
        }

        enqueue_audio(std::move(mono));
    }

    AsrSnapshot snapshot() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return AsrSnapshot{status_, status_message_, partial_transcript_, committed_transcript_, metrics_};
    }

    bool is_loaded() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return loaded_;
    }

private:
    using OnlineRecognizer = sherpa_onnx::cxx::OnlineRecognizer;
    using OnlineStream = sherpa_onnx::cxx::OnlineStream;
    using OnlineSpeechDenoiser = sherpa_onnx::cxx::OnlineSpeechDenoiser;
    using VoiceActivityDetector = sherpa_onnx::cxx::VoiceActivityDetector;

    std::unique_ptr<OnlineRecognizer> create_recognizer() const {
        namespace sx = sherpa_onnx::cxx;

        const auto encoder = !config_.encoder.empty()
            ? config_.encoder
            : config_.model_dir / "encoder-epoch-75-avg-11-chunk-16-left-128.int8.onnx";
        const auto decoder = !config_.decoder.empty()
            ? config_.decoder
            : config_.model_dir / "decoder-epoch-75-avg-11-chunk-16-left-128.onnx";
        const auto joiner = !config_.joiner.empty()
            ? config_.joiner
            : config_.model_dir / "joiner-epoch-75-avg-11-chunk-16-left-128.int8.onnx";
        const auto tokens = !config_.tokens.empty() ? config_.tokens : config_.model_dir / "tokens.txt";

        require_file(encoder, "encoder");
        require_file(decoder, "decoder");
        require_file(joiner, "joiner");
        require_file(tokens, "tokens");

        sx::OnlineRecognizerConfig recognizer_config;
        recognizer_config.model_config.transducer.encoder = to_utf8_path(encoder);
        recognizer_config.model_config.transducer.decoder = to_utf8_path(decoder);
        recognizer_config.model_config.transducer.joiner = to_utf8_path(joiner);
        recognizer_config.model_config.tokens = to_utf8_path(tokens);
        recognizer_config.model_config.num_threads = config_.num_threads;
        recognizer_config.model_config.provider = "cpu";
        recognizer_config.feat_config.sample_rate = config_.sample_rate;
        recognizer_config.feat_config.feature_dim = config_.feature_dim;
        recognizer_config.enable_endpoint = true;
        recognizer_config.rule1_min_trailing_silence = 2.0F;
        recognizer_config.rule2_min_trailing_silence = 0.8F;
        recognizer_config.rule3_min_utterance_length = 12.0F;

        const bool has_hotwords = !config_.hotwords_file.empty() || !config_.hotwords_text.empty();
        if (has_hotwords) {
            recognizer_config.decoding_method = "modified_beam_search";
            recognizer_config.max_active_paths = config_.max_active_paths;
            recognizer_config.hotwords_score = config_.hotwords_score;
            if (!config_.hotwords_file.empty()) {
                require_file(config_.hotwords_file, "hotwords_file");
                recognizer_config.hotwords_file = to_utf8_path(config_.hotwords_file);
            }
            recognizer_config.hotwords_buf = config_.hotwords_text;

            const auto bpe_vocab = !config_.bpe_vocab.empty() ? config_.bpe_vocab : config_.model_dir / "bpe.vocab";
            if (std::filesystem::exists(bpe_vocab)) {
                recognizer_config.model_config.modeling_unit = "bpe";
                recognizer_config.model_config.bpe_vocab = to_utf8_path(bpe_vocab);
            } else {
                throw std::runtime_error(
                    "Hotwords require bpe.vocab for this BPE model. Generate bpe.vocab from bpe.model or disable hotwords.");
            }
        } else {
            recognizer_config.decoding_method = "greedy_search";
            recognizer_config.max_active_paths = 1;
        }

        auto recognizer = std::make_unique<OnlineRecognizer>(OnlineRecognizer::Create(recognizer_config));
        if (recognizer->Get() == nullptr) {
            throw std::runtime_error("Failed to load sherpa-onnx OnlineRecognizer");
        }
        return recognizer;
    }

    std::unique_ptr<OnlineSpeechDenoiser> create_denoiser() const {
        if (!config_.enable_denoiser) {
            return nullptr;
        }
        require_file(config_.denoiser_model, "denoiser_model");

        namespace sx = sherpa_onnx::cxx;
        sx::OnlineSpeechDenoiserConfig denoiser_config;
        denoiser_config.model.gtcrn.model = to_utf8_path(config_.denoiser_model);
        denoiser_config.model.num_threads = config_.num_threads;
        denoiser_config.model.provider = "cpu";

        auto denoiser = std::make_unique<OnlineSpeechDenoiser>(OnlineSpeechDenoiser::Create(denoiser_config));
        if (denoiser->Get() == nullptr) {
            throw std::runtime_error("Failed to load sherpa-onnx GTCRN OnlineSpeechDenoiser");
        }
        return denoiser;
    }

    std::unique_ptr<VoiceActivityDetector> create_vad() const {
        if (!config_.enable_vad) {
            return nullptr;
        }
        require_file(config_.vad_model, "vad_model");

        namespace sx = sherpa_onnx::cxx;
        sx::VadModelConfig vad_config;
        vad_config.silero_vad.model = to_utf8_path(config_.vad_model);
        vad_config.silero_vad.threshold = 0.5F;
        vad_config.silero_vad.min_silence_duration = 0.35F;
        vad_config.silero_vad.min_speech_duration = 0.15F;
        vad_config.silero_vad.window_size = 512;
        vad_config.silero_vad.max_speech_duration = 20.0F;
        vad_config.sample_rate = config_.sample_rate;
        vad_config.num_threads = config_.num_threads;
        vad_config.provider = "cpu";

        auto vad = std::make_unique<VoiceActivityDetector>(VoiceActivityDetector::Create(vad_config, 30.0F));
        if (vad->Get() == nullptr) {
            throw std::runtime_error("Failed to load sherpa-onnx Silero VoiceActivityDetector");
        }
        return vad;
    }

    static void require_file(const std::filesystem::path& path, const char* label) {
        if (path.empty() || !std::filesystem::exists(path)) {
            throw std::runtime_error(std::string("Missing ") + label + ": " + path.u8string());
        }
    }

    void validate_audio_format(int sample_rate, int channels) const {
        if (sample_rate != config_.sample_rate || sample_rate != kExpectedSampleRate) {
            throw std::runtime_error("AsrEngine expects 16 kHz PCM input. Resample before calling push_audio_*().");
        }
        if (channels <= 0) {
            throw std::runtime_error("AsrEngine expects channels >= 1.");
        }
    }

    void enqueue_audio(std::vector<float> mono) {
        std::lock_guard<std::mutex> lock(mutex_);
        if (!loaded_ || !session_active_ || status_ == AsrStatus::Error) {
            return;
        }

        metrics_.accepted_samples += mono.size();
        metrics_.input_rms = compute_rms(mono);
        metrics_.input_peak = compute_peak(mono);
        raw_queue_.insert(raw_queue_.end(), mono.begin(), mono.end());

        const auto max_queue_samples = static_cast<std::size_t>((std::max)(1.0F, config_.max_queue_seconds) * config_.sample_rate);
        const auto unread = unread_samples_locked();
        if (unread > max_queue_samples) {
            discard_oldest_locked(unread - max_queue_samples);
        }
        metrics_.queued_samples = unread_samples_locked();
        cv_.notify_one();
    }

    void worker_loop() {
        for (;;) {
            std::vector<float> chunk;
            bool should_start = false;
            bool should_stop = false;
            {
                std::unique_lock<std::mutex> lock(mutex_);
                cv_.wait(lock, [this] {
                    return stop_worker_ || start_session_requested_ || stop_session_requested_ || can_pop_audio_locked();
                });

                if (stop_worker_) {
                    break;
                }

                if (start_session_requested_) {
                    should_start = true;
                    start_session_requested_ = false;
                } else if (stop_session_requested_) {
                    should_stop = true;
                    stop_session_requested_ = false;
                } else if (!pop_audio_locked(chunk)) {
                    continue;
                }
            }

            if (should_start) {
                stream_ = std::make_unique<OnlineStream>(recognizer_->CreateStream());
                if (stream_->Get() == nullptr) {
                    fail("Failed to create sherpa-onnx OnlineStream");
                    continue;
                }
                continue;
            }

            if (should_stop) {
                stream_.reset();
                reset_frontend_state();
                continue;
            }

            if (!stream_) {
                continue;
            }

            auto processed = run_frontend(chunk);
            const auto metrics = metrics_after_frontend(chunk, processed);
            notify_metrics(metrics);

            auto asr_samples = run_vad_gate(processed, metrics.vad_active);
            if (asr_samples.empty()) {
                update_status(AsrStatus::Listening, "Waiting for speech after VAD");
                continue;
            }

            decode(asr_samples);
        }
    }

    bool can_pop_audio_locked() const {
        if (!session_active_ || raw_queue_.size() <= raw_read_offset_) {
            return false;
        }
        const auto min_samples = denoiser_ != nullptr
            ? static_cast<std::size_t>((std::max)(1, denoiser_->GetFrameShiftInSamples()))
            : kDecodeChunkSamples;
        return unread_samples_locked() >= min_samples;
    }

    bool pop_audio_locked(std::vector<float>& chunk) {
        if (!can_pop_audio_locked()) {
            return false;
        }
        const auto sample_count = denoiser_ != nullptr
            ? static_cast<std::size_t>((std::max)(1, denoiser_->GetFrameShiftInSamples()))
            : (std::min)(kDecodeChunkSamples, unread_samples_locked());
        chunk.assign(
            raw_queue_.begin() + static_cast<std::ptrdiff_t>(raw_read_offset_),
            raw_queue_.begin() + static_cast<std::ptrdiff_t>(raw_read_offset_ + sample_count));
        raw_read_offset_ += sample_count;
        compact_queue_locked(false);
        metrics_.queued_samples = unread_samples_locked();
        return true;
    }

    std::size_t unread_samples_locked() const {
        return raw_queue_.size() >= raw_read_offset_ ? raw_queue_.size() - raw_read_offset_ : 0;
    }

    void discard_oldest_locked(std::size_t sample_count) {
        raw_read_offset_ += (std::min)(sample_count, unread_samples_locked());
        compact_queue_locked(false);
    }

    void compact_queue_locked(bool release_memory) {
        if (raw_read_offset_ == 0) {
            return;
        }
        if (raw_read_offset_ >= raw_queue_.size()) {
            raw_read_offset_ = 0;
            if (release_memory) {
                std::vector<float>().swap(raw_queue_);
            } else {
                raw_queue_.clear();
            }
            return;
        }
        if (raw_read_offset_ < static_cast<std::size_t>(config_.sample_rate)) {
            return;
        }
        raw_queue_.erase(raw_queue_.begin(), raw_queue_.begin() + static_cast<std::ptrdiff_t>(raw_read_offset_));
        raw_read_offset_ = 0;
    }

    std::vector<float> run_frontend(const std::vector<float>& input) {
        auto frontend = input;
        if (config_.enable_high_pass) {
            for (auto& sample : frontend) {
                sample = high_pass(sample);
            }
        }

        if (denoiser_ != nullptr && !frontend.empty()) {
            const auto denoised = denoiser_->Run(frontend.data(), static_cast<int32_t>(frontend.size()), config_.sample_rate);
            frontend = denoised.samples;
        }

        return frontend;
    }

    AsrMetrics metrics_after_frontend(const std::vector<float>& input, std::vector<float>& processed) {
        bool vad_active = true;
        if (vad_ != nullptr && !processed.empty()) {
            vad_->AcceptWaveform(processed.data(), static_cast<int32_t>(processed.size()));
            vad_active = vad_->IsDetected();
            while (!vad_->IsEmpty()) {
                vad_->Pop();
            }
        }

        if (config_.enable_agc && vad_active) {
            apply_agc(processed);
        } else {
            agc_gain_ = 0.98F * agc_gain_ + 0.02F;
        }

        std::lock_guard<std::mutex> lock(mutex_);
        metrics_.input_rms = compute_rms(input);
        metrics_.input_peak = compute_peak(input);
        metrics_.processed_rms = compute_rms(processed);
        metrics_.processed_peak = compute_peak(processed);
        metrics_.vad_active = vad_active;
        metrics_.processed_samples += processed.size();
        metrics_.queued_samples = unread_samples_locked();
        return metrics_;
    }

    float high_pass(float sample) {
        const float output = sample - high_pass_last_input_ + (0.995F * high_pass_last_output_);
        high_pass_last_input_ = sample;
        high_pass_last_output_ = std::clamp(output, -1.0F, 1.0F);
        return high_pass_last_output_;
    }

    void apply_agc(std::vector<float>& samples) {
        const float rms = compute_rms(samples);
        if (rms <= std::numeric_limits<float>::epsilon()) {
            return;
        }
        const float desired_gain = std::clamp(config_.agc_target_rms / rms, 1.0F, config_.agc_max_gain);
        agc_gain_ = (0.92F * agc_gain_) + (0.08F * desired_gain);
        for (auto& sample : samples) {
            sample = std::clamp(sample * agc_gain_, -1.0F, 1.0F);
        }
    }

    std::vector<float> run_vad_gate(const std::vector<float>& processed, bool vad_active) {
        if (!config_.enable_vad || vad_ == nullptr) {
            return processed;
        }

        std::vector<float> output;
        const auto pre_roll_limit = static_cast<std::size_t>(config_.vad_pre_roll_seconds * config_.sample_rate);
        const auto hangover_samples = static_cast<std::size_t>(config_.vad_hangover_seconds * config_.sample_rate);

        if (!feeding_asr_) {
            pre_roll_buffer_.insert(pre_roll_buffer_.end(), processed.begin(), processed.end());
            while (pre_roll_buffer_.size() > pre_roll_limit) {
                pre_roll_buffer_.pop_front();
            }
            if (vad_active) {
                feeding_asr_ = true;
                hangover_remaining_samples_ = hangover_samples;
                output.assign(pre_roll_buffer_.begin(), pre_roll_buffer_.end());
                pre_roll_buffer_.clear();
            }
            return output;
        }

        output = processed;
        if (vad_active) {
            hangover_remaining_samples_ = hangover_samples;
            return output;
        }

        if (hangover_remaining_samples_ > processed.size()) {
            hangover_remaining_samples_ -= processed.size();
        } else {
            hangover_remaining_samples_ = 0;
            feeding_asr_ = false;
        }

        return output;
    }

    void decode(const std::vector<float>& samples) {
        stream_->AcceptWaveform(config_.sample_rate, samples.data(), static_cast<int32_t>(samples.size()));
        while (recognizer_->IsReady(stream_.get())) {
            recognizer_->Decode(stream_.get());
        }

        const auto result = recognizer_->GetResult(stream_.get());
        const auto text = trim_text(result.text);
        const bool endpoint = recognizer_->IsEndpoint(stream_.get());

        if (endpoint) {
            if (!text.empty()) {
                append_final(text);
                notify_final(text);
            }
            partial_transcript_.clear();
            recognizer_->Reset(stream_.get());
            update_status(AsrStatus::Listening, "Endpoint detected; waiting for next speech");
            return;
        }

        if (!text.empty() && text != last_partial_notified_) {
            {
                std::lock_guard<std::mutex> lock(mutex_);
                partial_transcript_ = text;
            }
            last_partial_notified_ = text;
            notify_partial(text);
        }
        update_status(AsrStatus::Streaming, "Streaming ASR decoding");
    }

    void append_final(const std::string& text) {
        std::lock_guard<std::mutex> lock(mutex_);
        if (!committed_transcript_.empty()) {
            committed_transcript_ += ' ';
        }
        committed_transcript_ += text;
        partial_transcript_.clear();
    }

    void reset_frontend_state() {
        high_pass_last_input_ = 0.0F;
        high_pass_last_output_ = 0.0F;
        agc_gain_ = 1.0F;
        feeding_asr_ = false;
        hangover_remaining_samples_ = 0;
        pre_roll_buffer_.clear();
        if (denoiser_ != nullptr) {
            denoiser_->Reset();
        }
        if (vad_ != nullptr) {
            vad_->Reset();
            vad_->Clear();
        }
    }

    void clear_runtime_locked(bool release_memory) {
        raw_read_offset_ = 0;
        if (release_memory) {
            std::vector<float>().swap(raw_queue_);
        } else {
            raw_queue_.clear();
        }
        pre_roll_buffer_.clear();
        partial_transcript_.clear();
        committed_transcript_.clear();
        last_partial_notified_.clear();
        metrics_ = {};
        feeding_asr_ = false;
        hangover_remaining_samples_ = 0;
    }

    void require_loaded_locked() const {
        if (!loaded_ || recognizer_ == nullptr) {
            throw std::runtime_error("Call AsrEngine::load() before start_session().");
        }
    }

    void fail(const std::string& message) {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            set_status_locked(AsrStatus::Error, message);
            session_active_ = false;
            clear_runtime_locked(true);
        }
        notify_status(AsrStatus::Error, message);
    }

    void update_status(AsrStatus status, const std::string& message) {
        bool changed = false;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            changed = status_ != status || status_message_ != message;
            set_status_locked(status, message);
        }
        if (changed) {
            notify_status(status, message);
        }
    }

    void set_status_locked(AsrStatus status, std::string message) {
        status_ = status;
        status_message_ = std::move(message);
    }

    AsrCallbacks callbacks_copy() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return callbacks_;
    }

    void notify_status(AsrStatus status, const std::string& message) const {
        const auto callbacks = callbacks_copy();
        if (callbacks.on_status) {
            callbacks.on_status(status, message);
        }
    }

    void notify_partial(const std::string& text) const {
        const auto callbacks = callbacks_copy();
        if (callbacks.on_partial) {
            callbacks.on_partial(text);
        }
    }

    void notify_final(const std::string& text) const {
        const auto callbacks = callbacks_copy();
        if (callbacks.on_final) {
            callbacks.on_final(text);
        }
    }

    void notify_metrics(const AsrMetrics& metrics) const {
        const auto callbacks = callbacks_copy();
        if (callbacks.on_metrics) {
            callbacks.on_metrics(metrics);
        }
    }

    AsrConfig config_;
    mutable std::mutex mutex_;
    std::condition_variable cv_;
    std::thread worker_;
    AsrCallbacks callbacks_;

    std::unique_ptr<OnlineRecognizer> recognizer_;
    std::unique_ptr<OnlineStream> stream_;
    std::unique_ptr<OnlineSpeechDenoiser> denoiser_;
    std::unique_ptr<VoiceActivityDetector> vad_;

    bool loaded_ = false;
    bool stop_worker_ = false;
    bool session_active_ = false;
    bool start_session_requested_ = false;
    bool stop_session_requested_ = false;

    std::vector<float> raw_queue_;
    std::size_t raw_read_offset_ = 0;
    std::deque<float> pre_roll_buffer_;

    float high_pass_last_input_ = 0.0F;
    float high_pass_last_output_ = 0.0F;
    float agc_gain_ = 1.0F;
    bool feeding_asr_ = false;
    std::size_t hangover_remaining_samples_ = 0;

    AsrStatus status_ = AsrStatus::Unloaded;
    std::string status_message_ = "ASR models unloaded";
    std::string partial_transcript_;
    std::string committed_transcript_;
    std::string last_partial_notified_;
    AsrMetrics metrics_;
};

AsrEngine::AsrEngine(AsrConfig config) : impl_(std::make_unique<Impl>(std::move(config))) {}
AsrEngine::~AsrEngine() = default;

void AsrEngine::set_callbacks(AsrCallbacks callbacks) {
    impl_->set_callbacks(std::move(callbacks));
}

void AsrEngine::load() {
    impl_->load();
}

void AsrEngine::unload() {
    impl_->unload();
}

void AsrEngine::start_session() {
    impl_->start_session();
}

void AsrEngine::stop_session() {
    impl_->stop_session();
}

void AsrEngine::push_audio_f32(const float* samples, std::size_t frame_count, int sample_rate, int channels) {
    impl_->push_audio_f32(samples, frame_count, sample_rate, channels);
}

void AsrEngine::push_audio_i16(const std::int16_t* samples, std::size_t frame_count, int sample_rate, int channels) {
    impl_->push_audio_i16(samples, frame_count, sample_rate, channels);
}

AsrSnapshot AsrEngine::snapshot() const {
    return impl_->snapshot();
}

bool AsrEngine::is_loaded() const {
    return impl_->is_loaded();
}

} // namespace asr
