#include "sherpa-onnx/c-api/c-api.h"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

const char* env_or_default(const char* name, const char* fallback) {
    const char* value = std::getenv(name);
    return value != nullptr && value[0] != '\0' ? value : fallback;
}

bool env_flag_enabled(const char* name) {
    const char* value = std::getenv(name);
    if (value == nullptr) {
        return false;
    }
    return std::strcmp(value, "1") == 0 ||
           std::strcmp(value, "true") == 0 ||
           std::strcmp(value, "TRUE") == 0 ||
           std::strcmp(value, "yes") == 0 ||
           std::strcmp(value, "YES") == 0;
}

int env_int_or_default(const char* name, int fallback) {
    const char* value = std::getenv(name);
    if (value == nullptr || value[0] == '\0') {
        return fallback;
    }
    try {
        return std::stoi(value);
    } catch (...) {
        return fallback;
    }
}

void require_file(const std::filesystem::path& path, const char* label) {
    if (path.empty() || !std::filesystem::exists(path)) {
        throw std::runtime_error(std::string("Missing ") + label + ": " + path.u8string());
    }
}

float rms(const std::vector<std::int16_t>& samples, std::size_t frames) {
    if (frames == 0) {
        return 0.0F;
    }
    double sum = 0.0;
    for (std::size_t i = 0; i < frames; ++i) {
        const double sample = static_cast<double>(samples[i]);
        sum += sample * sample;
    }
    return static_cast<float>(std::sqrt(sum / static_cast<double>(frames)));
}

std::string trim(std::string value) {
    auto is_space = [](unsigned char ch) { return std::isspace(ch) != 0; };
    value.erase(value.begin(), std::find_if(value.begin(), value.end(), [&](unsigned char ch) { return !is_space(ch); }));
    value.erase(std::find_if(value.rbegin(), value.rend(), [&](unsigned char ch) { return !is_space(ch); }).base(), value.end());
    return value;
}

std::string lower_ascii(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char ch) {
        return static_cast<char>(std::tolower(ch));
    });
    return value;
}

bool is_plausible_transcript(const std::string& text) {
    const std::string cleaned = trim(text);
    if (cleaned.empty()) {
        return false;
    }
    if (lower_ascii(cleaned) == "el") {
        return false;
    }
    return cleaned.size() >= 3;
}

} // namespace

int main(int argc, char* argv[]) {
    try {
        if (argc < 2) {
            std::cerr << "Usage: asr_push_stream <asr-sdk-root>\n";
            return 2;
        }

        const std::filesystem::path package_root = argv[1];
        const auto model_dir = package_root / "models" / "sherpa-onnx-streaming-zipformer-ar_en_id_ja_ru_th_vi_zh-2025-02-10";
        const auto encoder = model_dir / "encoder-epoch-75-avg-11-chunk-16-left-128.int8.onnx";
        const auto decoder = model_dir / "decoder-epoch-75-avg-11-chunk-16-left-128.onnx";
        const auto joiner = model_dir / "joiner-epoch-75-avg-11-chunk-16-left-128.int8.onnx";
        const auto tokens = model_dir / "tokens.txt";

        require_file(encoder, "encoder");
        require_file(decoder, "decoder");
        require_file(joiner, "joiner");
        require_file(tokens, "tokens");

        const auto hotwords = package_root / "hotwords" / "hotwords_vi.txt";

        std::cout << "status: loading - Creating sherpa-onnx C API recognizer" << std::endl;

        SherpaOnnxOnlineRecognizerConfig config;
        std::memset(&config, 0, sizeof(config));
        config.feat_config.sample_rate = 16000;
        config.feat_config.feature_dim = 80;
        config.model_config.transducer.encoder = encoder.c_str();
        config.model_config.transducer.decoder = decoder.c_str();
        config.model_config.transducer.joiner = joiner.c_str();
        config.model_config.tokens = tokens.c_str();
        config.model_config.num_threads = 1;
        config.model_config.provider = "cpu";
        config.model_config.model_type = env_or_default("ASR_MODEL_TYPE", "zipformer2");
        config.model_config.debug = env_flag_enabled("ASR_DEBUG") ? 1 : 0;
        
        const bool has_hotwords = env_flag_enabled("ASR_ENABLE_HOTWORDS") && std::filesystem::exists(hotwords);
        if (has_hotwords) {
            config.hotwords_file = hotwords.c_str();
            config.hotwords_score = 1.5F; // Bias Vietnamese hotwords
        }

        config.decoding_method = has_hotwords ? "modified_beam_search" : "greedy_search";
        config.max_active_paths = 1;
        config.enable_endpoint = 1;
        config.rule1_min_trailing_silence = 2.0F;
        config.rule2_min_trailing_silence = 0.8F;
        config.rule3_min_utterance_length = 12.0F;

        const SherpaOnnxOnlineRecognizer* recognizer = SherpaOnnxCreateOnlineRecognizer(&config);
        if (recognizer == nullptr) {
            throw std::runtime_error("SherpaOnnxCreateOnlineRecognizer returned null");
        }

        const SherpaOnnxOnlineStream* stream = SherpaOnnxCreateOnlineStream(recognizer);
        if (stream == nullptr) {
            SherpaOnnxDestroyOnlineRecognizer(recognizer);
            throw std::runtime_error("SherpaOnnxCreateOnlineStream returned null");
        }

        std::cout << "status: streaming - Decoding stream" << std::endl;

        constexpr int chunk_samples = 1600; // 100ms
        std::vector<std::int16_t> pcm_chunk(chunk_samples, 0);
        std::vector<float> float_chunk(chunk_samples, 0.0F);

        const int min_speech_rms = env_int_or_default("ASR_MIN_SPEECH_RMS", 350);
        const int min_speech_frames = env_int_or_default("ASR_MIN_SPEECH_FRAMES", 3);
        int speech_frames = 0;
        bool heard_speech = false;
        std::string last_text = "";

        while (std::cin.read(reinterpret_cast<char*>(pcm_chunk.data()), chunk_samples * sizeof(std::int16_t)) || std::cin.gcount() > 0) {
            auto bytes_read = std::cin.gcount();
            auto frames = bytes_read / sizeof(std::int16_t);
            if (frames > 0) {
                const float chunk_rms = rms(pcm_chunk, static_cast<std::size_t>(frames));
                if (chunk_rms >= static_cast<float>(min_speech_rms)) {
                    ++speech_frames;
                    if (speech_frames >= min_speech_frames) {
                        heard_speech = true;
                    }
                } else if (!heard_speech) {
                    speech_frames = 0;
                    continue;
                }

                for (std::size_t i = 0; i < frames; ++i) {
                    float_chunk[i] = static_cast<float>(pcm_chunk[i]) / 32768.0F;
                }
                SherpaOnnxOnlineStreamAcceptWaveform(
                    stream,
                    16000,
                    float_chunk.data(),
                    static_cast<int32_t>(frames));
                
                while (SherpaOnnxIsOnlineStreamReady(recognizer, stream)) {
                    SherpaOnnxDecodeOnlineStream(recognizer, stream);
                }

                const SherpaOnnxOnlineRecognizerResult* result = SherpaOnnxGetOnlineStreamResult(recognizer, stream);
                if (result != nullptr && result->text != nullptr) {
                    std::string text = result->text;
                    if (text != last_text && is_plausible_transcript(text)) {
                        std::cout << "partial: " << text << std::endl;
                        last_text = text;
                    }
                    SherpaOnnxDestroyOnlineRecognizerResult(result);
                }

                if (SherpaOnnxOnlineStreamIsEndpoint(recognizer, stream)) {
                    const SherpaOnnxOnlineRecognizerResult* result = SherpaOnnxGetOnlineStreamResult(recognizer, stream);
                    std::string text = result != nullptr && result->text != nullptr ? result->text : "";
                    if (result != nullptr) {
                        SherpaOnnxDestroyOnlineRecognizerResult(result);
                    }
                    if (is_plausible_transcript(text)) {
                        std::cout << "final: " << text << std::endl;
                        last_text = "";
                    }
                    SherpaOnnxOnlineStreamReset(recognizer, stream);
                }
            }
        }

        SherpaOnnxOnlineStreamInputFinished(stream);
        while (SherpaOnnxIsOnlineStreamReady(recognizer, stream)) {
            SherpaOnnxDecodeOnlineStream(recognizer, stream);
        }

        const SherpaOnnxOnlineRecognizerResult* result = SherpaOnnxGetOnlineStreamResult(recognizer, stream);
        std::string text = result != nullptr && result->text != nullptr ? result->text : "";
        if (result != nullptr) {
            SherpaOnnxDestroyOnlineRecognizerResult(result);
        }

        SherpaOnnxDestroyOnlineStream(stream);
        SherpaOnnxDestroyOnlineRecognizer(recognizer);

        if (is_plausible_transcript(text) && text != last_text) {
            std::cout << "final: " << text << std::endl;
        }
        std::cout << "status: ready - Stream transcription complete" << std::endl;
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "asr_push_stream failed: " << error.what() << '\n';
        return 1;
    }
}
