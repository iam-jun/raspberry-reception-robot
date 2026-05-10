cmake_minimum_required(VERSION 3.20)

project(AsrEngineSdk LANGUAGES CXX)

option(ASR_ENGINE_BUILD_EXAMPLES "Build AsrEngine SDK examples" OFF)

if(NOT DEFINED SHERPA_ONNX_ROOT)
    set(SHERPA_ONNX_ROOT "" CACHE PATH "Path to sherpa-onnx prebuilt runtime root")
endif()

if(NOT SHERPA_ONNX_ROOT)
    message(FATAL_ERROR "Set SHERPA_ONNX_ROOT to a sherpa-onnx prebuilt runtime directory")
endif()

set(SHERPA_ONNX_INCLUDE_DIR "${SHERPA_ONNX_ROOT}/include")
set(SHERPA_ONNX_LIB_DIR "${SHERPA_ONNX_ROOT}/lib")
set(SHERPA_ONNX_CXX_API_HEADER "${SHERPA_ONNX_INCLUDE_DIR}/sherpa-onnx/c-api/cxx-api.h")

if(NOT EXISTS "${SHERPA_ONNX_CXX_API_HEADER}")
    message(FATAL_ERROR
            "sherpa-onnx C++ API header not found: ${SHERPA_ONNX_CXX_API_HEADER}\n"
            "Set SHERPA_ONNX_ROOT to the installed/prebuilt sherpa-onnx runtime root, not to a placeholder path.\n"
            "Expected layout:\n"
            "  <root>/include/sherpa-onnx/c-api/cxx-api.h\n"
            "  <root>/lib/libsherpa-onnx-cxx-api.so\n"
            "  <root>/lib/libsherpa-onnx-c-api.so\n"
            "  <root>/lib/libonnxruntime.so")
endif()

if(WIN32)
    set(SHERPA_ONNX_LIBS
            "${SHERPA_ONNX_LIB_DIR}/sherpa-onnx-cxx-api.lib"
            "${SHERPA_ONNX_LIB_DIR}/sherpa-onnx-c-api.lib"
            "${SHERPA_ONNX_LIB_DIR}/onnxruntime.lib"
    )
else()
    find_library(SHERPA_ONNX_CXX_API sherpa-onnx-cxx-api HINTS "${SHERPA_ONNX_LIB_DIR}" REQUIRED)
    find_library(SHERPA_ONNX_C_API sherpa-onnx-c-api HINTS "${SHERPA_ONNX_LIB_DIR}" REQUIRED)
    find_library(ONNXRUNTIME onnxruntime HINTS "${SHERPA_ONNX_LIB_DIR}" REQUIRED)
    set(SHERPA_ONNX_LIBS ${SHERPA_ONNX_CXX_API} ${SHERPA_ONNX_C_API} ${ONNXRUNTIME})
endif()

add_library(asr_engine STATIC
        src/AsrEngine.cpp
)

target_compile_features(asr_engine PUBLIC cxx_std_17)

target_include_directories(asr_engine
        PUBLIC
            "${CMAKE_CURRENT_SOURCE_DIR}/include"
        PRIVATE
            "${SHERPA_ONNX_INCLUDE_DIR}"
)

target_link_libraries(asr_engine PUBLIC ${SHERPA_ONNX_LIBS})

if(MSVC)
    target_compile_options(asr_engine PRIVATE /utf-8)
endif()

if(ASR_ENGINE_BUILD_EXAMPLES)
    add_executable(asr_from_wav examples/asr_from_wav.cpp)
    target_link_libraries(asr_from_wav PRIVATE ${SHERPA_ONNX_LIBS})
    target_include_directories(asr_from_wav PRIVATE "${SHERPA_ONNX_INCLUDE_DIR}")

    add_executable(asr_push_stream examples/asr_push_stream.cpp)
    target_link_libraries(asr_push_stream PRIVATE asr_engine)
    target_include_directories(asr_push_stream PRIVATE "${SHERPA_ONNX_INCLUDE_DIR}")

    if(WIN32)
        set(SHERPA_ONNX_DLLS
                "${SHERPA_ONNX_LIB_DIR}/sherpa-onnx-cxx-api.dll"
                "${SHERPA_ONNX_LIB_DIR}/sherpa-onnx-c-api.dll"
                "${SHERPA_ONNX_LIB_DIR}/onnxruntime.dll"
                "${SHERPA_ONNX_LIB_DIR}/onnxruntime_providers_shared.dll"
        )
        foreach(EXAMPLE_TARGET asr_from_wav asr_push_stream)
            foreach(SHERPA_DLL IN LISTS SHERPA_ONNX_DLLS)
                add_custom_command(TARGET ${EXAMPLE_TARGET} POST_BUILD
                        COMMAND ${CMAKE_COMMAND} -E copy_if_different
                                "${SHERPA_DLL}"
                                "$<TARGET_FILE_DIR:${EXAMPLE_TARGET}>/"
                        VERBATIM
                )
            endforeach()
        endforeach()
    endif()
endif()
