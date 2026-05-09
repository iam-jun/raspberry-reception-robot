#include "asr/AsrEngine.h"

#include <chrono>
#include <cmath>
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
    if (argc < 2) {
        std::cerr << "Usage: asr_push_stream <asr-sdk-root>\n";
        return 2;
    }

    asr::AsrEngine engine(make_config(argv[1]));
    engine.set_callbacks({
        [](const std::string& text) { std::cout << "partial: " << text << '\n'; },
        [](const std::string& text) { std::cout << "final: " << text << '\n'; },
        [](asr::AsrStatus status, const std::string& message) {
            std::cout << "status: " << asr::to_string(status) << " - " << message << '\n';
        },
        [](const asr::AsrMetrics& metrics) {
            if (metrics.vad_active) {
                std::cout << "vad active, processed RMS=" << metrics.processed_rms << '\n';
            }
        }
    });

    engine.load();
    engine.start_session();

    // Thay vòng lặp này bằng khung ALSA/PulseAudio/device-server trên Raspberry.
    // Mỗi vòng lặp sẽ đẩy âm thanh vào với chuẩn mono 16 kHz PCM khoảng 20-100 ms.
    constexpr int sample_rate = 16000;
    constexpr int chunk_samples = 1600;
    std::vector<float> chunk(chunk_samples, 0.0F);
    for (int i = 0; i < 100; ++i) {
        // Đưa âm thanh micro vào đây.
        engine.push_audio_f32(chunk.data(), chunk.size(), sample_rate);
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    engine.stop_session();
    engine.unload();
    return 0;
    } catch (const std::exception& error) {
        std::cerr << "asr_push_stream failed: " << error.what() << '\n';
        return 1;
    }
}
