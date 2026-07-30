#pragma once

#include "endstone_dynamic_properties/types.h"

#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <variant>

namespace endstone_dynamic_properties {

using DynamicPropertyValue = std::variant<bool, double, std::string, Vector3>;
using DynamicPropertyMap = std::map<std::string, DynamicPropertyValue>;

struct ValueValidationResult {
    bool valid{};
    std::string message;
};

[[nodiscard]] std::string_view valueTypeName(const DynamicPropertyValue &value) noexcept;
[[nodiscard]] ValueValidationResult validateValue(
    const DynamicPropertyValue &value,
    const ValidationLimits &limits = {});
[[nodiscard]] ValueValidationResult validateKey(
    std::string_view key,
    const ValidationLimits &limits = {});
[[nodiscard]] ValueValidationResult validateCollectionName(
    std::string_view collection,
    const ValidationLimits &limits = {});
[[nodiscard]] std::uint64_t estimateStoredBytes(
    std::string_view key,
    const DynamicPropertyValue &value) noexcept;
[[nodiscard]] std::uint64_t hashValue(const DynamicPropertyValue &value) noexcept;
[[nodiscard]] std::string debugValue(const DynamicPropertyValue &value);
[[nodiscard]] std::string encodeCollectionJson(
    const CollectionRef &ref,
    const DynamicPropertyMap &properties,
    std::uint64_t revision);
[[nodiscard]] std::optional<DynamicPropertyMap> decodeCollectionJson(
    std::string_view document,
    std::string *error = nullptr);

} // namespace endstone_dynamic_properties
