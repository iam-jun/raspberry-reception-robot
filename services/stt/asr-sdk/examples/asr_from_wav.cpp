#include "asr/AsrEngine.h"

#include <chrono>
#include <cstdint>
#include <cstring>
#include <exception>
#include <fstream>
#include <filesystem>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

namespace {

asr::AsrConfig make_config(const std::filesystem::path& package_root) {
    asr::AsrConfig config;
    config.model_dir = package_root / "models" / "sherpa-onnx-streaming-zipformer-ar_en_id_ja_ru_th_vi_zh-2025-02-10";
    config.denoiser_model = package_root / "models" / "sherpa-official-ns-vad" / "gtcrn_simple.onnx";
    config.vad_model = package_root / "models" / "sherpa-official-ns-vad" / "silero_vad.onnx";
    const auto hotwords = package_root / "hotwords" / "hotwords_vi.txt";
    const auto bpe_vocab = package_root / "models" / "sherpa-onnx-streaming-zipformer-ar_en_id_ja_ru_th_vi_zh-2025-02-10" / "bpe.vocab";
    if (std::filesystem::exists(hotwords) && std::filesystem::exists(bpe_vocab)) {
        config.hotwords_file = hotwords;
        config.bpe_vocab = bpe_vocab;
    }
    return config;
}

struct WaveData {
    int sample_rate = 0;
    std::vector<float> samples;
};

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
            (void)read_u32(input); // byte rate
            (void)read_u16(input); // block align
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
    const auto wave = read_wave_mono_16k(wav_path);
    if (wave.samples.empty() || wave.sample_rate != 16000) {
        std::cerr << "Expected a readable mono 16 kHz WAV: " << wav_path.u8string() << '\n';
        return 2;
    }

    asr::AsrEngine engine(make_config(package_root));
    engine.set_callbacks({
        [](const std::string& text) { std::cout << "partial: " << text << '\n'; },
        [](const std::string& text) { std::cout << "final: " << text << '\n'; },
        [](asr::AsrStatus status, const std::string& message) {
            std::cout << "status: " << asr::to_string(status) << " - " << message << '\n';
        },
        {}
    });

    engine.load();          // Loads ASR/NS/VAD models into RAM.
    engine.start_session(); // Starts accepting audio.

    constexpr std::size_t frame_samples = 1600;
    for (std::size_t offset = 0; offset < wave.samples.size(); offset += frame_samples) {
        const auto count = (std::min)(frame_samples, wave.samples.size() - offset);
        engine.push_audio_f32(wave.samples.data() + offset, count, 16000);
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }

    const std::vector<float> trailing_silence(16000 * 2, 0.0F);
    engine.push_audio_f32(trailing_silence.data(), trailing_silence.size(), 16000);
    std::this_thread::sleep_for(std::chrono::seconds(2));

    engine.stop_session(); // Clears stream state; models remain loaded.
    engine.unload();       // Releases model RAM.
    return 0;
    } catch (const std::exception& error) {
        std::cerr << "asr_from_wav failed: " << error.what() << '\n';
        return 1;
    }
}
