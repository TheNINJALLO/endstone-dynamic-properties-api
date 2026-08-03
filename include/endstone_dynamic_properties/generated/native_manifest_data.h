#pragma once

#include "endstone_dynamic_properties/native_manifest.h"

#include <array>
#include <cstdint>
#include <string_view>

namespace endstone_dynamic_properties::generated {

struct GeneratedSymbolEntry {
    NativeDynamicPropertySymbol symbol{};
    std::uint64_t rva{};
    std::array<std::uint8_t, 24> fingerprint{};
    std::uint8_t fingerprint_size{};
};

inline constexpr std::string_view BdsPackageVersion = "1.26.33.1";
inline constexpr std::string_view RuntimeBds = "26.33";
inline constexpr std::string_view EndstoneVersion = "0.11.6";

#ifdef _WIN32
inline constexpr std::string_view Platform = "windows-x64";
inline constexpr std::string_view ArchiveSha256 =
    "fc6c0ad6f82cfb11c65c6756a1a8e49b21ffa8cc203da587df59df365d82a2ad";
inline constexpr std::string_view ExecutableSha256 =
    "4a0b867eee6c24310f405410b17e9794441b81ed8f2976cdd4cef54d0c441829";
inline constexpr std::uint64_t ExecutableSize = 207171408ULL;
#else
inline constexpr std::string_view Platform = "linux-x64";
inline constexpr std::string_view ArchiveSha256 =
    "68c52ababde987741029de091c09cd736fe894bc1fe99cf20f9ed5c659f0c180";
inline constexpr std::string_view ExecutableSha256 =
    "61995841f21baf9bfab96e0d9b0cb798501dcc9789dab68e496f3b8e3bc83375";
inline constexpr std::uint64_t ExecutableSize = 232842872ULL;
#endif

// Deliberately closed in source control. tools/activate_verified_manifest.py
// opens the proof fields only after every live and stored target, mutation
// hook, storage contract, and disposable-world probe has passed. Exact
// executable identity alone is evidence, not activation.
inline constexpr bool NativeManifestActivated = false;
inline constexpr bool ExactBuildMatch = false;
inline constexpr bool ExactBinaryHashMatch = false;
inline constexpr bool SymbolsValidated = false;
inline constexpr bool StorageContractsValidated = false;
inline constexpr bool ExternalHooksValidated = false;
inline constexpr bool StageProbePassed = false;
inline constexpr std::array<GeneratedSymbolEntry, 0> Symbols{};

} // namespace endstone_dynamic_properties::generated
