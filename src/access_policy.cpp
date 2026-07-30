#include "endstone_dynamic_properties/access_policy.h"

#include <cctype>

namespace endstone_dynamic_properties {

DynamicPropertyAccessPolicy::DynamicPropertyAccessPolicy(std::string prefix)
    : prefix_(normalize(prefix)) {
    if (prefix_.empty()) prefix_ = "endstone-plugin";
}

std::string DynamicPropertyAccessPolicy::normalize(std::string_view value) {
    std::string out;
    out.reserve(value.size());
    for (const unsigned char c : value) {
        if ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.') {
            out.push_back(static_cast<char>(c));
        } else if (c >= 'A' && c <= 'Z') {
            out.push_back(static_cast<char>(c - 'A' + 'a'));
        } else {
            out.push_back('_');
        }
    }
    while (!out.empty() && out.front() == '_') out.erase(out.begin());
    while (!out.empty() && out.back() == '_') out.pop_back();
    return out;
}

std::string DynamicPropertyAccessPolicy::pluginPrefix(std::string_view plugin_id) const {
    const auto normalized = normalize(plugin_id);
    if (normalized.empty()) return {};
    return prefix_ + ':' + normalized + ':';
}

std::string DynamicPropertyAccessPolicy::pluginCollection(
    std::string_view plugin_id,
    std::string_view logical_collection) const {
    const auto prefix = pluginPrefix(plugin_id);
    const auto logical = normalize(logical_collection);
    if (prefix.empty() || logical.empty()) return {};
    return prefix + logical;
}

bool DynamicPropertyAccessPolicy::canAccess(
    const AccessContext &context,
    const CollectionRef &ref) const {
    if (context.raw_admin) return true;
    const auto prefix = pluginPrefix(context.plugin_id);
    return !prefix.empty() && ref.collection.starts_with(prefix);
}

bool DynamicPropertyAccessPolicy::canListRawCollections(const AccessContext &context) const noexcept {
    return context.raw_admin;
}

std::optional<std::string> validateTarget(const DynamicPropertyTarget &target) {
    if (target.world_id.empty()) return "world id must not be empty";
    switch (target.kind) {
    case TargetKind::World:
        return std::nullopt;
    case TargetKind::OnlinePlayer:
    case TargetKind::OfflinePlayer:
        if (target.xuid.empty()) return "player target requires an XUID";
        return std::nullopt;
    case TargetKind::LoadedEntity:
    case TargetKind::StoredEntity:
        if (target.entity_id.empty()) return "entity target requires an entity identifier";
        return std::nullopt;
    case TargetKind::PlayerInventorySlot:
        if (target.xuid.empty()) return "inventory target requires an XUID";
        if (target.section != InventorySection::Main || target.slot < 0)
            return "main inventory target requires a non-negative main slot";
        return std::nullopt;
    case TargetKind::PlayerArmorSlot:
        if (target.xuid.empty()) return "armor target requires an XUID";
        if (target.section != InventorySection::Armor || target.slot < 0)
            return "armor target requires a non-negative armor slot";
        return std::nullopt;
    case TargetKind::PlayerOffhandSlot:
        if (target.xuid.empty()) return "offhand target requires an XUID";
        if (target.section != InventorySection::Offhand || target.slot < 0)
            return "offhand target requires a non-negative offhand slot";
        return std::nullopt;
    case TargetKind::PlayerEnderChestSlot:
        if (target.xuid.empty()) return "Ender Chest target requires an XUID";
        if (target.section != InventorySection::EnderChest || target.slot < 0)
            return "Ender Chest target requires a non-negative slot";
        return std::nullopt;
    case TargetKind::BlockContainerSlot:
        if (!target.block) return "block-container target requires a block location";
        if (target.section != InventorySection::BlockContainer || target.slot < 0)
            return "block-container target requires a non-negative slot";
        return std::nullopt;
    case TargetKind::DroppedItem:
        if (target.item_entity_id.empty()) return "dropped-item target requires an entity identifier";
        return std::nullopt;
    case TargetKind::BlockEntity:
        if (!target.block) return "block-entity target requires a block location";
        return std::nullopt;
    }
    return "unknown target kind";
}

} // namespace endstone_dynamic_properties
