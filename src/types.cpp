#include "endstone_dynamic_properties/types.h"

#include <sstream>

namespace endstone_dynamic_properties {

DynamicPropertyTarget DynamicPropertyTarget::world(std::string world_id) {
    DynamicPropertyTarget out;
    out.kind = TargetKind::World;
    out.world_id = std::move(world_id);
    return out;
}

DynamicPropertyTarget DynamicPropertyTarget::onlinePlayer(std::string xuid, std::string world_id) {
    DynamicPropertyTarget out;
    out.kind = TargetKind::OnlinePlayer;
    out.world_id = std::move(world_id);
    out.xuid = std::move(xuid);
    return out;
}

DynamicPropertyTarget DynamicPropertyTarget::offlinePlayer(std::string xuid, std::string world_id) {
    auto out = onlinePlayer(std::move(xuid), std::move(world_id));
    out.kind = TargetKind::OfflinePlayer;
    return out;
}

DynamicPropertyTarget DynamicPropertyTarget::loadedEntity(std::string entity_id, std::string world_id) {
    DynamicPropertyTarget out;
    out.kind = TargetKind::LoadedEntity;
    out.world_id = std::move(world_id);
    out.entity_id = std::move(entity_id);
    return out;
}

DynamicPropertyTarget DynamicPropertyTarget::storedEntity(std::string entity_id, std::string world_id) {
    auto out = loadedEntity(std::move(entity_id), std::move(world_id));
    out.kind = TargetKind::StoredEntity;
    return out;
}

DynamicPropertyTarget DynamicPropertyTarget::playerItem(
    std::string xuid,
    InventorySection section,
    std::int32_t slot,
    std::string world_id) {
    DynamicPropertyTarget out;
    out.world_id = std::move(world_id);
    out.xuid = std::move(xuid);
    out.section = section;
    out.slot = slot;
    switch (section) {
    case InventorySection::Main: out.kind = TargetKind::PlayerInventorySlot; break;
    case InventorySection::Armor: out.kind = TargetKind::PlayerArmorSlot; break;
    case InventorySection::Offhand: out.kind = TargetKind::PlayerOffhandSlot; break;
    case InventorySection::EnderChest: out.kind = TargetKind::PlayerEnderChestSlot; break;
    default: out.kind = TargetKind::PlayerInventorySlot; break;
    }
    return out;
}

DynamicPropertyTarget DynamicPropertyTarget::blockContainerItem(
    BlockLocation location,
    std::int32_t slot,
    std::string world_id) {
    DynamicPropertyTarget out;
    out.kind = TargetKind::BlockContainerSlot;
    out.world_id = std::move(world_id);
    out.block = std::move(location);
    out.section = InventorySection::BlockContainer;
    out.slot = slot;
    return out;
}

DynamicPropertyTarget DynamicPropertyTarget::droppedItem(std::string entity_id, std::string world_id) {
    DynamicPropertyTarget out;
    out.kind = TargetKind::DroppedItem;
    out.world_id = std::move(world_id);
    out.item_entity_id = std::move(entity_id);
    return out;
}

DynamicPropertyTarget DynamicPropertyTarget::blockEntity(BlockLocation location, std::string world_id) {
    DynamicPropertyTarget out;
    out.kind = TargetKind::BlockEntity;
    out.world_id = std::move(world_id);
    out.block = std::move(location);
    return out;
}

bool DynamicPropertyCapabilities::completeControl() const noexcept {
    return world && online_players && offline_players && loaded_entities && stored_entities &&
           player_inventory_items && player_armor_items && player_offhand_items &&
           player_ender_chest_items && block_container_items && dropped_items && block_entities &&
           block_dynamic_properties && read && write && remove && clear && list_ids &&
           list_collections && byte_count && bulk_set && collection_rename && property_copy_move &&
           collection_copy_move && collection_migration && export_import && atomic_transactions &&
           rollback && audit && watches && external_change_observation &&
           external_change_cancellation && persistence_flush && exact_build_match &&
           exact_binary_hash_match && symbols_validated && stage_probe_passed;
}

std::string_view targetKindName(TargetKind kind) noexcept {
    switch (kind) {
    case TargetKind::World: return "world";
    case TargetKind::OnlinePlayer: return "online_player";
    case TargetKind::OfflinePlayer: return "offline_player";
    case TargetKind::LoadedEntity: return "loaded_entity";
    case TargetKind::StoredEntity: return "stored_entity";
    case TargetKind::PlayerInventorySlot: return "player_inventory_slot";
    case TargetKind::PlayerArmorSlot: return "player_armor_slot";
    case TargetKind::PlayerOffhandSlot: return "player_offhand_slot";
    case TargetKind::PlayerEnderChestSlot: return "player_ender_chest_slot";
    case TargetKind::BlockContainerSlot: return "block_container_slot";
    case TargetKind::DroppedItem: return "dropped_item";
    case TargetKind::BlockEntity: return "block_entity";
    }
    return "unknown";
}

std::string_view statusName(DynamicPropertyStatus status) noexcept {
    switch (status) {
    case DynamicPropertyStatus::Applied: return "applied";
    case DynamicPropertyStatus::Captured: return "captured";
    case DynamicPropertyStatus::NotFound: return "not_found";
    case DynamicPropertyStatus::Conflict: return "conflict";
    case DynamicPropertyStatus::Cancelled: return "cancelled";
    case DynamicPropertyStatus::TargetUnavailable: return "target_unavailable";
    case DynamicPropertyStatus::CollectionUnavailable: return "collection_unavailable";
    case DynamicPropertyStatus::InvalidTarget: return "invalid_target";
    case DynamicPropertyStatus::InvalidCollection: return "invalid_collection";
    case DynamicPropertyStatus::InvalidKey: return "invalid_key";
    case DynamicPropertyStatus::InvalidValue: return "invalid_value";
    case DynamicPropertyStatus::PermissionDenied: return "permission_denied";
    case DynamicPropertyStatus::Unsupported: return "unsupported";
    case DynamicPropertyStatus::RuntimeMismatch: return "runtime_mismatch";
    case DynamicPropertyStatus::BinaryIdentityMismatch: return "binary_identity_mismatch";
    case DynamicPropertyStatus::SymbolValidationFailed: return "symbol_validation_failed";
    case DynamicPropertyStatus::StorageUnavailable: return "storage_unavailable";
    case DynamicPropertyStatus::PersistenceFailed: return "persistence_failed";
    case DynamicPropertyStatus::TransactionFailed: return "transaction_failed";
    case DynamicPropertyStatus::RollbackFailed: return "rollback_failed";
    case DynamicPropertyStatus::AdapterUnavailable: return "adapter_unavailable";
    case DynamicPropertyStatus::AdapterError: return "adapter_error";
    }
    return "adapter_error";
}

std::string describeTarget(const DynamicPropertyTarget &target) {
    std::ostringstream out;
    out << targetKindName(target.kind) << ':' << target.world_id;
    if (!target.xuid.empty()) out << ":xuid=" << target.xuid;
    if (!target.entity_id.empty()) out << ":entity=" << target.entity_id;
    if (!target.item_entity_id.empty()) out << ":item=" << target.item_entity_id;
    if (target.block) {
        out << ':' << target.block->dimension << '@' << target.block->x << ','
            << target.block->y << ',' << target.block->z;
    }
    if (target.slot >= 0) out << ":slot=" << target.slot;
    return out.str();
}

} // namespace endstone_dynamic_properties
