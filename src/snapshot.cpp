#include "endstone_dynamic_properties/snapshot.h"

namespace endstone_dynamic_properties {
namespace {
constexpr std::uint64_t FnvOffset = 1469598103934665603ULL;
constexpr std::uint64_t FnvPrime = 1099511628211ULL;

void mixBytes(std::uint64_t &hash, std::string_view data) noexcept {
    for (const unsigned char c : data) {
        hash ^= c;
        hash *= FnvPrime;
    }
}

void mixNumber(std::uint64_t &hash, std::uint64_t value) noexcept {
    for (int i = 0; i < 8; ++i) {
        hash ^= static_cast<unsigned char>((value >> (i * 8)) & 0xFFU);
        hash *= FnvPrime;
    }
}
} // namespace

std::uint64_t calculateRevision(const CollectionSnapshot &snapshot) noexcept {
    std::uint64_t hash = FnvOffset;
    mixBytes(hash, describeTarget(snapshot.ref.target));
    mixBytes(hash, snapshot.ref.collection);
    mixNumber(hash, snapshot.exists ? 1U : 0U);
    for (const auto &[key, value] : snapshot.properties) {
        mixBytes(hash, key);
        mixNumber(hash, hashValue(value));
    }
    return hash;
}

CollectionSnapshot makeSnapshot(
    CollectionRef ref,
    DynamicPropertyMap properties,
    bool exists,
    bool loaded,
    bool persistent,
    bool writable) {
    CollectionSnapshot out;
    out.ref = std::move(ref);
    out.properties = std::move(properties);
    out.exists = exists;
    out.loaded = loaded;
    out.persistent = persistent;
    out.writable = writable;
    for (const auto &[key, value] : out.properties) out.byte_count += estimateStoredBytes(key, value);
    out.revision = calculateRevision(out);
    return out;
}

} // namespace endstone_dynamic_properties
