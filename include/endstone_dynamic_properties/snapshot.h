#pragma once

#include "endstone_dynamic_properties/value.h"

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace endstone_dynamic_properties {

struct CollectionSnapshot {
    CollectionRef ref;
    DynamicPropertyMap properties;
    std::uint64_t byte_count{};
    std::uint64_t revision{};
    bool exists{};
    bool loaded{};
    bool persistent{};
    bool writable{};
};

struct CaptureResult {
    DynamicPropertyStatus status{DynamicPropertyStatus::AdapterError};
    std::string message;
    std::optional<CollectionSnapshot> snapshot;
    [[nodiscard]] bool ok() const noexcept {
        return status == DynamicPropertyStatus::Captured;
    }
};

struct ListCollectionsResult {
    DynamicPropertyStatus status{DynamicPropertyStatus::AdapterError};
    std::string message;
    std::vector<std::string> collections;
    [[nodiscard]] bool ok() const noexcept {
        return status == DynamicPropertyStatus::Captured;
    }
};

[[nodiscard]] std::uint64_t calculateRevision(const CollectionSnapshot &snapshot) noexcept;
[[nodiscard]] CollectionSnapshot makeSnapshot(
    CollectionRef ref,
    DynamicPropertyMap properties,
    bool exists = true,
    bool loaded = true,
    bool persistent = true,
    bool writable = true);

} // namespace endstone_dynamic_properties
