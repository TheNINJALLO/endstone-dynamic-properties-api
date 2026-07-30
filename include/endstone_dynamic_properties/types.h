#pragma once

#include <compare>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

namespace endstone_dynamic_properties {

struct Vector3 {
    double x{};
    double y{};
    double z{};
    auto operator<=>(const Vector3 &) const = default;
};

enum class TargetKind {
    World,
    OnlinePlayer,
    OfflinePlayer,
    LoadedEntity,
    StoredEntity,
    PlayerInventorySlot,
    PlayerArmorSlot,
    PlayerOffhandSlot,
    PlayerEnderChestSlot,
    BlockContainerSlot,
    DroppedItem,
    BlockEntity,
};

enum class InventorySection {
    None,
    Main,
    Armor,
    Offhand,
    EnderChest,
    BlockContainer,
};

struct BlockLocation {
    std::string dimension{"overworld"};
    std::int32_t x{};
    std::int32_t y{};
    std::int32_t z{};
    auto operator<=>(const BlockLocation &) const = default;
};

struct DynamicPropertyTarget {
    TargetKind kind{TargetKind::World};
    std::string world_id{"default"};
    std::string xuid;
    std::string entity_id;
    std::optional<BlockLocation> block;
    InventorySection section{InventorySection::None};
    std::int32_t slot{-1};
    std::string item_entity_id;

    static DynamicPropertyTarget world(std::string world_id = "default");
    static DynamicPropertyTarget onlinePlayer(std::string xuid, std::string world_id = "default");
    static DynamicPropertyTarget offlinePlayer(std::string xuid, std::string world_id = "default");
    static DynamicPropertyTarget loadedEntity(std::string entity_id, std::string world_id = "default");
    static DynamicPropertyTarget storedEntity(std::string entity_id, std::string world_id = "default");
    static DynamicPropertyTarget playerItem(
        std::string xuid,
        InventorySection section,
        std::int32_t slot,
        std::string world_id = "default");
    static DynamicPropertyTarget blockContainerItem(
        BlockLocation location,
        std::int32_t slot,
        std::string world_id = "default");
    static DynamicPropertyTarget droppedItem(std::string entity_id, std::string world_id = "default");
    static DynamicPropertyTarget blockEntity(BlockLocation location, std::string world_id = "default");

    auto operator<=>(const DynamicPropertyTarget &) const = default;
};

struct CollectionRef {
    DynamicPropertyTarget target;
    std::string collection;
    auto operator<=>(const CollectionRef &) const = default;
};

enum class MutationOrigin {
    Api,
    Command,
    ScriptApi,
    Player,
    WorldLoad,
    StorageLoad,
    Migration,
    Rollback,
    NativeHook,
    Unknown,
};

enum class DynamicPropertyStatus {
    Applied,
    Captured,
    NotFound,
    Conflict,
    Cancelled,
    TargetUnavailable,
    CollectionUnavailable,
    InvalidTarget,
    InvalidCollection,
    InvalidKey,
    InvalidValue,
    PermissionDenied,
    Unsupported,
    RuntimeMismatch,
    BinaryIdentityMismatch,
    SymbolValidationFailed,
    StorageUnavailable,
    PersistenceFailed,
    TransactionFailed,
    RollbackFailed,
    AdapterUnavailable,
    AdapterError,
};

enum class ImportPolicy {
    FailIfDestinationExists,
    Merge,
    Replace,
};

enum class ExternalMutationDecision {
    Allow,
    Cancel,
    ObserveOnly,
};

struct AccessContext {
    std::string plugin_id;
    std::string actor_id;
    bool raw_admin{};
    MutationOrigin origin{MutationOrigin::Api};
    std::string reason;
};

struct ValidationLimits {
    std::size_t max_collection_bytes{256};
    std::size_t max_key_bytes{256};
    std::size_t max_string_bytes{32767};
    std::size_t max_properties_per_collection{16384};
    std::size_t max_transaction_operations{4096};
    std::size_t max_import_bytes{16U * 1024U * 1024U};
};

struct DynamicPropertyCapabilities {
    bool world{};
    bool online_players{};
    bool offline_players{};
    bool loaded_entities{};
    bool stored_entities{};
    bool player_inventory_items{};
    bool player_armor_items{};
    bool player_offhand_items{};
    bool player_ender_chest_items{};
    bool block_container_items{};
    bool dropped_items{};
    bool block_entities{};
    bool block_dynamic_properties{};
    bool read{};
    bool write{};
    bool remove{};
    bool clear{};
    bool list_ids{};
    bool list_collections{};
    bool byte_count{};
    bool bulk_set{};
    bool collection_rename{};
    bool property_copy_move{};
    bool collection_copy_move{};
    bool collection_migration{};
    bool export_import{};
    bool atomic_transactions{};
    bool rollback{};
    bool audit{};
    bool watches{};
    bool external_change_observation{};
    bool external_change_cancellation{};
    bool persistence_flush{};
    bool exact_build_match{};
    bool exact_binary_hash_match{};
    bool symbols_validated{};
    bool stage_probe_passed{};

    [[nodiscard]] bool completeControl() const noexcept;
};

[[nodiscard]] std::string_view targetKindName(TargetKind kind) noexcept;
[[nodiscard]] std::string_view statusName(DynamicPropertyStatus status) noexcept;
[[nodiscard]] std::string describeTarget(const DynamicPropertyTarget &target);

} // namespace endstone_dynamic_properties
