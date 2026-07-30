#include "endstone_dynamic_properties/native_binary_identity.h"

#include <array>
#include <bit>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <limits>
#include <sstream>
#include <string>
#include <system_error>
#include <vector>

#ifdef _WIN32
#include <windows.h>
#else
#include <unistd.h>
#endif

namespace endstone_dynamic_properties {
namespace {

constexpr std::array<std::uint32_t, 64> K{
    0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u,
    0x3956c25bu, 0x59f111f1u, 0x923f82a4u, 0xab1c5ed5u,
    0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u,
    0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u,
    0xe49b69c1u, 0xefbe4786u, 0x0fc19dc6u, 0x240ca1ccu,
    0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
    0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u,
    0xc6e00bf3u, 0xd5a79147u, 0x06ca6351u, 0x14292967u,
    0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u,
    0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u,
    0xa2bfe8a1u, 0xa81a664bu, 0xc24b8b70u, 0xc76c51a3u,
    0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
    0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u,
    0x391c0cb3u, 0x4ed8aa4au, 0x5b9cca4fu, 0x682e6ff3u,
    0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u,
    0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u,
};

class Sha256 {
public:
    void update(std::span<const std::byte> input) {
        for (const auto value : input) {
            buffer_[buffer_size_++] = static_cast<std::uint8_t>(value);
            ++total_bytes_;
            if (buffer_size_ == buffer_.size()) {
                transform(buffer_);
                buffer_size_ = 0;
            }
        }
    }

    std::array<std::uint8_t, 32> finish() {
        const std::uint64_t total_bits = total_bytes_ * 8u;
        buffer_[buffer_size_++] = 0x80;
        if (buffer_size_ > 56) {
            while (buffer_size_ < 64) buffer_[buffer_size_++] = 0;
            transform(buffer_);
            buffer_size_ = 0;
        }
        while (buffer_size_ < 56) buffer_[buffer_size_++] = 0;
        for (int shift = 56; shift >= 0; shift -= 8)
            buffer_[buffer_size_++] = static_cast<std::uint8_t>(total_bits >> shift);
        transform(buffer_);

        std::array<std::uint8_t, 32> digest{};
        for (std::size_t i = 0; i < state_.size(); ++i) {
            digest[i * 4] = static_cast<std::uint8_t>(state_[i] >> 24);
            digest[i * 4 + 1] = static_cast<std::uint8_t>(state_[i] >> 16);
            digest[i * 4 + 2] = static_cast<std::uint8_t>(state_[i] >> 8);
            digest[i * 4 + 3] = static_cast<std::uint8_t>(state_[i]);
        }
        return digest;
    }

private:
    static std::uint32_t choose(std::uint32_t x, std::uint32_t y, std::uint32_t z) {
        return (x & y) ^ (~x & z);
    }
    static std::uint32_t majority(std::uint32_t x, std::uint32_t y, std::uint32_t z) {
        return (x & y) ^ (x & z) ^ (y & z);
    }
    static std::uint32_t bigSigma0(std::uint32_t x) {
        return std::rotr(x, 2) ^ std::rotr(x, 13) ^ std::rotr(x, 22);
    }
    static std::uint32_t bigSigma1(std::uint32_t x) {
        return std::rotr(x, 6) ^ std::rotr(x, 11) ^ std::rotr(x, 25);
    }
    static std::uint32_t smallSigma0(std::uint32_t x) {
        return std::rotr(x, 7) ^ std::rotr(x, 18) ^ (x >> 3);
    }
    static std::uint32_t smallSigma1(std::uint32_t x) {
        return std::rotr(x, 17) ^ std::rotr(x, 19) ^ (x >> 10);
    }

    void transform(const std::array<std::uint8_t, 64> &block) {
        std::array<std::uint32_t, 64> words{};
        for (std::size_t i = 0; i < 16; ++i) {
            words[i] = (static_cast<std::uint32_t>(block[i * 4]) << 24) |
                       (static_cast<std::uint32_t>(block[i * 4 + 1]) << 16) |
                       (static_cast<std::uint32_t>(block[i * 4 + 2]) << 8) |
                       static_cast<std::uint32_t>(block[i * 4 + 3]);
        }
        for (std::size_t i = 16; i < words.size(); ++i) {
            words[i] = smallSigma1(words[i - 2]) + words[i - 7] +
                       smallSigma0(words[i - 15]) + words[i - 16];
        }

        auto a = state_[0];
        auto b = state_[1];
        auto c = state_[2];
        auto d = state_[3];
        auto e = state_[4];
        auto f = state_[5];
        auto g = state_[6];
        auto h = state_[7];
        for (std::size_t i = 0; i < words.size(); ++i) {
            const auto t1 = h + bigSigma1(e) + choose(e, f, g) + K[i] + words[i];
            const auto t2 = bigSigma0(a) + majority(a, b, c);
            h = g;
            g = f;
            f = e;
            e = d + t1;
            d = c;
            c = b;
            b = a;
            a = t1 + t2;
        }
        state_[0] += a;
        state_[1] += b;
        state_[2] += c;
        state_[3] += d;
        state_[4] += e;
        state_[5] += f;
        state_[6] += g;
        state_[7] += h;
    }

    std::array<std::uint32_t, 8> state_{
        0x6a09e667u,
        0xbb67ae85u,
        0x3c6ef372u,
        0xa54ff53au,
        0x510e527fu,
        0x9b05688cu,
        0x1f83d9abu,
        0x5be0cd19u,
    };
    std::array<std::uint8_t, 64> buffer_{};
    std::size_t buffer_size_{};
    std::uint64_t total_bytes_{};
};

std::string toHex(const std::array<std::uint8_t, 32> &digest) {
    std::ostringstream stream;
    stream << std::hex << std::setfill('0');
    for (const auto value : digest) stream << std::setw(2) << static_cast<unsigned>(value);
    return stream.str();
}

std::filesystem::path currentExecutablePath(std::string &error) {
#ifdef _WIN32
    std::vector<wchar_t> buffer(1024);
    while (true) {
        const auto length = GetModuleFileNameW(nullptr, buffer.data(), static_cast<DWORD>(buffer.size()));
        if (length == 0) {
            error = "GetModuleFileNameW failed";
            return {};
        }
        if (length < buffer.size() - 1) return std::filesystem::path(buffer.data(), buffer.data() + length);
        if (buffer.size() > 32768) {
            error = "executable path exceeds Windows path limit";
            return {};
        }
        buffer.resize(buffer.size() * 2);
    }
#else
    std::vector<char> buffer(1024);
    while (true) {
        const auto length = readlink("/proc/self/exe", buffer.data(), buffer.size());
        if (length < 0) {
            error = "readlink(/proc/self/exe) failed";
            return {};
        }
        if (static_cast<std::size_t>(length) < buffer.size())
            return std::filesystem::path(std::string(buffer.data(), static_cast<std::size_t>(length)));
        if (buffer.size() > 1u << 20) {
            error = "executable path is unexpectedly long";
            return {};
        }
        buffer.resize(buffer.size() * 2);
    }
#endif
}

} // namespace

std::string sha256Bytes(std::span<const std::byte> bytes) {
    Sha256 hash;
    hash.update(bytes);
    return toHex(hash.finish());
}

std::string sha256File(const std::filesystem::path &path, std::string *error) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) {
        if (error) *error = "could not open file for SHA-256";
        return {};
    }
    Sha256 hash;
    std::array<char, 65536> buffer{};
    while (stream) {
        stream.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
        const auto count = stream.gcount();
        if (count > 0) {
            hash.update(std::span<const std::byte>(
                reinterpret_cast<const std::byte *>(buffer.data()),
                static_cast<std::size_t>(count)));
        }
    }
    if (!stream.eof()) {
        if (error) *error = "failed while reading file for SHA-256";
        return {};
    }
    return toHex(hash.finish());
}

RuntimeExecutableIdentity inspectCurrentProcessExecutable() {
    RuntimeExecutableIdentity identity;
    identity.path = currentExecutablePath(identity.error);
    if (!identity.error.empty()) return identity;
    std::error_code ec;
    identity.size = std::filesystem::file_size(identity.path, ec);
    if (ec || identity.size == 0) {
        identity.error = ec ? ec.message() : "executable file size is zero";
        return identity;
    }
    identity.sha256 = sha256File(identity.path, &identity.error);
    return identity;
}

} // namespace endstone_dynamic_properties
