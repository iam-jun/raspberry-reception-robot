#include "sherpa-onnx/c-api/c-api.h"

#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

struct WaveData {
    int sample_rate = 0;
    std::vector<float> samples;
};

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

std::uint32_t read_u32(std::ifstream& input) {
    std::uint8_t bytes[4] = {};
    input.read(reinterpret_cast<char*>(bytes), sizeof(bytes));
    return static_cast<std::uint32_t>(bytes[0]) |
           (static_cast<std::uint32_t>(bytes[1]) << 8U) |
           (static_cast<std::uint32_t>(bytes[2]) << 16U) |
           (static_cast<std::uint32_t>(bytes[3]) << 24U);
}

std::uint16_t read_u16(std::ifstream& input) {
    std::uint8_t bytes[2] = {};
    input.read(reinterpret_cast<char*>(bytes), sizeof(bytes));
    return static_cast<std::uint16_t>(bytes[0]) |
           static_cast<std::uint16_t>(bytes[1] << 8U);
}

void require_file(const std::filesystem::path& path, const char* label) {
    if (path.empty() || !std::filesystem::exists(path)) {
        throw std::runtime_error(std::string("Missing ") + label + ": " + path.u8string());
    }
}

WaveData read_wave_mono_16k(const std::filesystem::path& wav_path) {
    std::ifstream input(wav_path, std::ios::binary);
    if (!input) {
        throw std::runtime_error("Unable to open WAV file: " + wav_path.u8string());
    }

    char riff[4] = {};
    input.read(riff, sizeof(riff));
    (void)read_u32(input);
    char wave_tag[4] = {};
    input.read(wave_tag, sizeof(wave_tag));
    if (std::strncmp(riff, "RIFF", 4) != 0 || std::strncmp(wave_tag, "WAVE", 4) != 0) {
        throw std::runtime_error("Expected a RIFF/WAVE file: " + wav_path.u8string());
    }

    std::uint16_t audio_format = 0;
    std::uint16_t channels = 0;
    std::uint32_t sample_rate = 0;
    std::uint16_t bits_per_sample = 0;
    std::vector<char> pcm_data;

    while (input && (!audio_format || pcm_data.empty())) {
        char chunk_id[4] = {};
        input.read(chunk_id, sizeof(chunk_id));
        if (!input) {
            break;
        }
        const auto chunk_size = read_u32(input);
        const auto next_chunk = input.tellg() + static_cast<std::streamoff>(chunk_size);

        if (std::strncmp(chunk_id, "fmt ", 4) == 0) {
            audio_format = read_u16(input);
            channels = read_u16(input);
            sample_rate = read_u32(input);
            (void)read_u32(input);
            (void)read_u16(input);
            bits_per_sample = read_u16(input);
        } else if (std::strncmp(chunk_id, "data", 4) == 0) {
            pcm_data.resize(chunk_size);
            input.read(pcm_data.data(), static_cast<std::streamsize>(pcm_data.size()));
        }

        input.seekg(next_chunk);
    }

    if (audio_format != 1 || channels != 1 || sample_rate != 16000 || bits_per_sample != 16) {
        throw std::runtime_error("Expected PCM signed-16 mono 16 kHz WAV: " + wav_path.u8string());
    }

    WaveData wave;
    wave.sample_rate = static_cast<int>(sample_rate);
    wave.samples.reserve(pcm_data.size() / sizeof(std::int16_t));
    for (std::size_t offset = 0; offset + 1 < pcm_data.size(); offset += 2) {
        const auto lo = static_cast<std::uint8_t>(pcm_data[offset]);
        const auto hi = static_cast<std::uint8_t>(pcm_data[offset + 1]);
        const auto sample = static_cast<std::int16_t>(lo | static_cast<std::uint16_t>(hi << 8U));
        wave.samples.push_back(static_cast<float>(sample) / 32768.0F);
    }
    return wave;
}

} // namespace

int main(int argc, char* argv[]) {
    try {
        if (argc < 3) {
            std::cerr << "Usage: asr_from_wav <asr-sdk-root> <mono-16k-wav>\n";
            return 2;
        }

        const std::filesystem::path package_root = argv[1];
        const std::filesystem::path wav_path = argv[2];
        const auto model_dir = package_root / "models" / "sherpa-onnx-streaming-zipformer-ar_en_id_ja_ru_th_vi_zh-2025-02-10";
        const auto encoder = model_dir / "encoder-epoch-75-avg-11-chunk-16-left-128.int8.onnx";
        const auto decoder = model_dir / "decoder-epoch-75-avg-11-chunk-16-left-128.onnx";
        const auto joiner = model_dir / "joiner-epoch-75-avg-11-chunk-16-left-128.int8.onnx";
        const auto tokens = model_dir / "tokens.txt";

        require_file(encoder, "encoder");
        require_file(decoder, "decoder");
        require_file(joiner, "joiner");
        require_file(tokens, "tokens");

        const auto wave = read_wave_mono_16k(wav_path);
        if (wave.samples.empty()) {
            throw std::runtime_error("WAV contains no samples: " + wav_path.u8string());
        }

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
        config.decoding_method = "greedy_search";
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

        std::cout << "status: streaming - Decoding WAV" << std::endl;

        constexpr int chunk_samples = 3200;
        for (std::size_t offset = 0; offset < wave.samples.size(); offset += chunk_samples) {
            const auto count = std::min<std::size_t>(chunk_samples, wave.samples.size() - offset);
            SherpaOnnxOnlineStreamAcceptWaveform(
                stream,
                wave.sample_rate,
                wave.samples.data() + offset,
                static_cast<int32_t>(count));
            while (SherpaOnnxIsOnlineStreamReady(recognizer, stream)) {
                SherpaOnnxDecodeOnlineStream(recognizer, stream);
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

        std::cout << "final: " << text << std::endl;
        std::cout << "status: ready - WAV transcription complete" << std::endl;
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "asr_from_wav failed: " << error.what() << '\n';
        return 1;
    }
}
