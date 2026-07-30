#include "endstone_dynamic_properties/native_manifest.h"
#include "endstone_dynamic_properties/generated/native_manifest_data.h"

#include <array>

namespace endstone_dynamic_properties {
namespace {
constexpr std::array RequiredSymbols{
    NativeDynamicPropertySymbol::DynamicPropertiesGet,
    NativeDynamicPropertySymbol::DynamicPropertiesGetIds,
    NativeDynamicPropertySymbol::DynamicPropertiesGetTotalBytes,
    NativeDynamicPropertySymbol::DynamicPropertiesSet,
    NativeDynamicPropertySymbol::DynamicPropertiesRemove,
    NativeDynamicPropertySymbol::DynamicPropertiesClearCollection,
    NativeDynamicPropertySymbol::DynamicPropertiesUpdateCollectionName,
    NativeDynamicPropertySymbol::DynamicPropertiesValidate,
    NativeDynamicPropertySymbol::PropertyCollectionToVariantMap,
    NativeDynamicPropertySymbol::PropertyCollectionFromVariantMap,
    NativeDynamicPropertySymbol::ServerLevelGetOrAddDynamicProperties,
    NativeDynamicPropertySymbol::ServerLevelGetDynamicPropertiesManager,
    NativeDynamicPropertySymbol::DynamicPropertiesManagerWriteLevelStorage,
    NativeDynamicPropertySymbol::ActorGetOrAddDynamicProperties,
    NativeDynamicPropertySymbol::ItemDynamicPropertiesGetAll,
    NativeDynamicPropertySymbol::ItemDynamicPropertiesGet,
    NativeDynamicPropertySymbol::ItemDynamicPropertiesSet,
    NativeDynamicPropertySymbol::ItemDynamicPropertiesRemove,
    NativeDynamicPropertySymbol::ItemDynamicPropertiesClear,
    NativeDynamicPropertySymbol::OfflinePlayerStorageRead,
    NativeDynamicPropertySymbol::OfflinePlayerStorageWrite,
    NativeDynamicPropertySymbol::StoredEntityRead,
    NativeDynamicPropertySymbol::StoredEntityWrite,
    NativeDynamicPropertySymbol::BlockDynamicPropertiesGetComponent,
    NativeDynamicPropertySymbol::BlockDynamicPropertiesMarkDirty,
    NativeDynamicPropertySymbol::HookDynamicPropertiesSet,
    NativeDynamicPropertySymbol::HookDynamicPropertiesRemove,
    NativeDynamicPropertySymbol::HookDynamicPropertiesClear,
};
} // namespace

std::string_view nativeDynamicPropertySymbolName(
    NativeDynamicPropertySymbol symbol) noexcept {
    switch (symbol) {
    case NativeDynamicPropertySymbol::DynamicPropertiesGet:
        return "dynamic_properties_get";
    case NativeDynamicPropertySymbol::DynamicPropertiesGetIds:
        return "dynamic_properties_get_ids";
    case NativeDynamicPropertySymbol::DynamicPropertiesGetTotalBytes:
        return "dynamic_properties_get_total_bytes";
    case NativeDynamicPropertySymbol::DynamicPropertiesSet:
        return "dynamic_properties_set";
    case NativeDynamicPropertySymbol::DynamicPropertiesRemove:
        return "dynamic_properties_remove";
    case NativeDynamicPropertySymbol::DynamicPropertiesClearCollection:
        return "dynamic_properties_clear_collection";
    case NativeDynamicPropertySymbol::DynamicPropertiesUpdateCollectionName:
        return "dynamic_properties_update_collection_name";
    case NativeDynamicPropertySymbol::DynamicPropertiesValidate:
        return "dynamic_properties_validate";
    case NativeDynamicPropertySymbol::PropertyCollectionToVariantMap:
        return "property_collection_to_variant_map";
    case NativeDynamicPropertySymbol::PropertyCollectionFromVariantMap:
        return "property_collection_from_variant_map";
    case NativeDynamicPropertySymbol::ServerLevelGetOrAddDynamicProperties:
        return "server_level_get_or_add_dynamic_properties";
    case NativeDynamicPropertySymbol::ServerLevelGetDynamicPropertiesManager:
        return "server_level_get_dynamic_properties_manager";
    case NativeDynamicPropertySymbol::DynamicPropertiesManagerWriteLevelStorage:
        return "dynamic_properties_manager_write_level_storage";
    case NativeDynamicPropertySymbol::ActorGetOrAddDynamicProperties:
        return "actor_get_or_add_dynamic_properties";
    case NativeDynamicPropertySymbol::ItemDynamicPropertiesGetAll:
        return "item_dynamic_properties_get_all";
    case NativeDynamicPropertySymbol::ItemDynamicPropertiesGet:
        return "item_dynamic_properties_get";
    case NativeDynamicPropertySymbol::ItemDynamicPropertiesSet:
        return "item_dynamic_properties_set";
    case NativeDynamicPropertySymbol::ItemDynamicPropertiesRemove:
        return "item_dynamic_properties_remove";
    case NativeDynamicPropertySymbol::ItemDynamicPropertiesClear:
        return "item_dynamic_properties_clear";
    case NativeDynamicPropertySymbol::OfflinePlayerStorageRead:
        return "offline_player_storage_read";
    case NativeDynamicPropertySymbol::OfflinePlayerStorageWrite:
        return "offline_player_storage_write";
    case NativeDynamicPropertySymbol::StoredEntityRead:
        return "stored_entity_read";
    case NativeDynamicPropertySymbol::StoredEntityWrite:
        return "stored_entity_write";
    case NativeDynamicPropertySymbol::BlockDynamicPropertiesGetComponent:
        return "block_dynamic_properties_get_component";
    case NativeDynamicPropertySymbol::BlockDynamicPropertiesMarkDirty:
        return "block_dynamic_properties_mark_dirty";
    case NativeDynamicPropertySymbol::HookDynamicPropertiesSet:
        return "hook_dynamic_properties_set";
    case NativeDynamicPropertySymbol::HookDynamicPropertiesRemove:
        return "hook_dynamic_properties_remove";
    case NativeDynamicPropertySymbol::HookDynamicPropertiesClear:
        return "hook_dynamic_properties_clear";
    }
    return "unknown";
}

std::span<const NativeDynamicPropertySymbol>
requiredNativeDynamicPropertySymbols() noexcept {
    return RequiredSymbols;
}

bool NativeGateStatus::complete() const noexcept {
    return manifest_activated && exact_build_match && exact_binary_hash_match &&
           symbols_validated && storage_contracts_validated &&
           external_hooks_validated && stage_probe_passed;
}

std::string NativeGateStatus::failureReason() const {
    if (!manifest_activated) return "native manifest is not activated";
    if (!exact_build_match) return "runtime BDS/Endstone build does not match";
    if (!exact_binary_hash_match) return "BDS executable identity was not verified";
    if (!symbols_validated) return "required symbols are not fully verified";
    if (!storage_contracts_validated)
        return "offline-player and stored-entity contracts are not verified";
    if (!external_hooks_validated)
        return "external mutation hooks are not verified";
    if (!stage_probe_passed)
        return "complete-control stage probe has not passed";
    return {};
}

NativeGateStatus compiledNativeGateStatus() {
    return {
        generated::NativeManifestActivated,
        generated::ExactBuildMatch,
        generated::ExactBinaryHashMatch,
        generated::SymbolsValidated,
        generated::StorageContractsValidated,
        generated::ExternalHooksValidated,
        generated::StageProbePassed,
        std::string(generated::BdsPackageVersion),
        std::string(generated::RuntimeBds),
        std::string(generated::EndstoneVersion),
    };
}

bool nativeServiceCanRegister() noexcept {
    return compiledNativeGateStatus().complete();
}

} // namespace endstone_dynamic_properties
