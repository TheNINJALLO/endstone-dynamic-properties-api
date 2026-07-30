#pragma once

#include <cstdint>
#include <span>
#include <string>
#include <string_view>

namespace endstone_dynamic_properties {

enum class NativeDynamicPropertySymbol : std::uint8_t {
    DynamicPropertiesGet,
    DynamicPropertiesGetIds,
    DynamicPropertiesGetTotalBytes,
    DynamicPropertiesSet,
    DynamicPropertiesRemove,
    DynamicPropertiesClearCollection,
    DynamicPropertiesUpdateCollectionName,
    DynamicPropertiesValidate,
    PropertyCollectionToVariantMap,
    PropertyCollectionFromVariantMap,
    ServerLevelGetOrAddDynamicProperties,
    ServerLevelGetDynamicPropertiesManager,
    DynamicPropertiesManagerWriteLevelStorage,
    ActorGetOrAddDynamicProperties,
    ItemDynamicPropertiesGetAll,
    ItemDynamicPropertiesGet,
    ItemDynamicPropertiesSet,
    ItemDynamicPropertiesRemove,
    ItemDynamicPropertiesClear,
    OfflinePlayerStorageRead,
    OfflinePlayerStorageWrite,
    StoredEntityRead,
    StoredEntityWrite,
    BlockDynamicPropertiesGetComponent,
    BlockDynamicPropertiesMarkDirty,
    HookDynamicPropertiesSet,
    HookDynamicPropertiesRemove,
    HookDynamicPropertiesClear,
};

[[nodiscard]] std::string_view nativeDynamicPropertySymbolName(
    NativeDynamicPropertySymbol symbol) noexcept;
[[nodiscard]] std::span<const NativeDynamicPropertySymbol>
requiredNativeDynamicPropertySymbols() noexcept;

struct NativeGateStatus {
    bool manifest_activated{};
    bool exact_build_match{};
    bool exact_binary_hash_match{};
    bool symbols_validated{};
    bool storage_contracts_validated{};
    bool external_hooks_validated{};
    bool stage_probe_passed{};
    std::string bds_package_version;
    std::string runtime_bds;
    std::string endstone_version;

    [[nodiscard]] bool complete() const noexcept;
    [[nodiscard]] std::string failureReason() const;
};

[[nodiscard]] NativeGateStatus compiledNativeGateStatus();
[[nodiscard]] bool nativeServiceCanRegister() noexcept;

} // namespace endstone_dynamic_properties
