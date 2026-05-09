#include "asr/AsrEngine.h"
#include "sherpa-onnx/c-api/cxx-api.h"

#include <chrono>
#include <exception>
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

} // namespace

int main(int argc, char* argv[]) {
    try {
    if (argc < 3) {
        std::cerr << "Usage: asr_from_wav <asr-sdk-root> <mono-16k-wav>\n";
        return 2;
    }

    const std::filesystem::path package_root = argv[1];
    const std::filesystem::path wav_path = argv[2];
    const auto wave = sherpa_onnx::cxx::ReadWave(wav_path.u8string());
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
