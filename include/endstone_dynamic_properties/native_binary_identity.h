#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <span>
#include <string>

namespace endstone_dynamic_properties {

struct RuntimeExecutableIdentity {
    std::filesystem::path path;
    std::string sha256;
    std::uint64_t size{};
    std::string error;
    [[nodiscard]] bool ok() const noexcept {
        return error.empty() && !path.empty() && !sha256.empty() && size != 0;
    }
};

[[nodiscard]] std::string sha256Bytes(std::span<const std::byte> bytes);
[[nodiscard]] std::string sha256File(const std::filesystem::path &path, std::string *error = nullptr);
[[nodiscard]] RuntimeExecutableIdentity inspectCurrentProcessExecutable();

} // namespace endstone_dynamic_properties
