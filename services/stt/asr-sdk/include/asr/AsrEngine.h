#pragma once

#include <cstdint>
#include <cstddef>
#include <filesystem>
#include <functional>
#include <memory>
#include <string>

namespace asr {

enum class AsrStatus {
    Unloaded,
    Loading,
    Ready,
    Listening,
    Streaming,
    Error
};

struct AsrConfig {
    // Directory containing encoder/decoder/joiner/tokens for the streaming
    // Zipformer model.
    std::filesystem::path model_dir;

    // Optional explicit model files. Leave empty to use the standard filenames
    // from model_dir.
    std::filesystem::path encoder;
    std::filesystem::path decoder;
    std::filesystem::path joiner;
    std::filesystem::path tokens;

    // Official sherpa-onnx front-end models.
    std::filesystem::path denoiser_model;
    std::filesystem::path vad_model;

    // Optional BPE vocabulary and Vietnamese hotwords for contextual biasing.
    // If hotwords_file or hotwords_text is set, AsrEngine uses
    // modified_beam_search instead of greedy_search.
    std::filesystem::path bpe_vocab;
    std::filesystem::path hotwords_file;
    std::string hotwords_text;

    int sample_rate = 16000;
    int feature_dim = 80;
    int num_threads = 1;
    int max_active_paths = 4;
    float hotwords_score = 1.5F;

    bool enable_denoiser = true;
    bool enable_vad = true;
    bool enable_high_pass = true;
    bool enable_agc = true;

    // VAD gate settings. Pre-roll prevents losing the first syllable; hangover
    // keeps the stream alive briefly after speech drops.
    float vad_pre_roll_seconds = 0.30F;
    float vad_hangover_seconds = 2.20F;

    // Conservative AGC. It only applies while VAD is active.
    float agc_target_rms = 0.045F;
    float agc_max_gain = 3.0F;

    // Queue guard. If the caller feeds audio faster than the worker can decode,
    // the oldest unprocessed audio is dropped instead of growing RAM forever.
    float max_queue_seconds = 6.0F;
};

struct AsrMetrics {
    float input_rms = 0.0F;
    float input_peak = 0.0F;
    float processed_rms = 0.0F;
    float processed_peak = 0.0F;
    bool vad_active = false;
    std::uint64_t accepted_samples = 0;
    std::uint64_t processed_samples = 0;
    std::size_t queued_samples = 0;
};

struct AsrSnapshot {
    AsrStatus status = AsrStatus::Unloaded;
    std::string status_message;
    std::string partial_transcript;
    std::string committed_transcript;
    AsrMetrics metrics;
};

struct AsrCallbacks {
    // Called whenever the streaming decoder has a changed partial transcript.
    std::function<void(const std::string& text)> on_partial;

    // Called when sherpa endpointing finalizes a segment.
    std::function<void(const std::string& text)> on_final;

    // Called on status changes, including Loading, Ready, Listening, Streaming,
    // Error, and Unloaded.
    std::function<void(AsrStatus status, const std::string& message)> on_status;

    // Called after each processed audio chunk.
    std::function<void(const AsrMetrics& metrics)> on_metrics;
};

class AsrEngine {
public:
    explicit AsrEngine(AsrConfig config);
    ~AsrEngine();

    AsrEngine(const AsrEngine&) = delete;
    AsrEngine& operator=(const AsrEngine&) = delete;

    // Registers callbacks. It is safe to call before or after load().
    void set_callbacks(AsrCallbacks callbacks);

    // Loads sherpa-onnx recognizer, GTCRN denoiser, and Silero VAD into RAM.
    // After this returns successfully, the model is ready but not consuming
    // audio until start_session() is called.
    void load();

    // Stops active sessions and releases recognizer/front-end model RAM.
    // Call this when the process wants the model to "sleep".
    void unload();

    // Starts a new streaming recognition session. The model must already be
    // loaded. Audio pushed after this call is accepted by the internal queue.
    void start_session();

    // Ends the active streaming session and clears queued audio/transcript
    // state. The models remain loaded in RAM for fast next-session startup.
    void stop_session();

    // Feeds PCM float samples. Expected format is mono 16 kHz in [-1, 1].
    // If channels > 1, samples are downmixed by taking the first channel.
    void push_audio_f32(const float* samples, std::size_t frame_count, int sample_rate, int channels = 1);

    // Feeds PCM int16 samples. Expected format is mono 16 kHz.
    // If channels > 1, samples are downmixed by taking the first channel.
    void push_audio_i16(const std::int16_t* samples, std::size_t frame_count, int sample_rate, int channels = 1);

    AsrSnapshot snapshot() const;
    bool is_loaded() const;

private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

std::string to_string(AsrStatus status);

} // namespace asr
