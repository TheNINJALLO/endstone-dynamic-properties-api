#pragma once

#include "endstone_dynamic_properties/operations.h"

#include <string>
#include <string_view>

namespace endstone_dynamic_properties {

class DynamicPropertyAccessPolicy {
public:
    explicit DynamicPropertyAccessPolicy(std::string prefix = "endstone-plugin");

    [[nodiscard]] std::string pluginCollection(
        std::string_view plugin_id,
        std::string_view logical_collection = "default") const;
    [[nodiscard]] bool canAccess(
        const AccessContext &context,
        const CollectionRef &ref) const;
    [[nodiscard]] bool canListRawCollections(const AccessContext &context) const noexcept;
    [[nodiscard]] std::string pluginPrefix(std::string_view plugin_id) const;

private:
    [[nodiscard]] static std::string normalize(std::string_view value);
    std::string prefix_;
};

[[nodiscard]] std::optional<std::string> validateTarget(
    const DynamicPropertyTarget &target);

} // namespace endstone_dynamic_properties
