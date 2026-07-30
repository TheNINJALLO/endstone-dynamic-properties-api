#!/usr/bin/env python3
"""Generate the open C++ gate after every unified native proof passes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_native_manifest import validate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SYMBOL_ENUM = {
    "dynamic_properties_get": "DynamicPropertiesGet",
    "dynamic_properties_get_ids": "DynamicPropertiesGetIds",
    "dynamic_properties_get_total_bytes": "DynamicPropertiesGetTotalBytes",
    "dynamic_properties_set": "DynamicPropertiesSet",
    "dynamic_properties_remove": "DynamicPropertiesRemove",
    "dynamic_properties_clear_collection": "DynamicPropertiesClearCollection",
    "dynamic_properties_update_collection_name": "DynamicPropertiesUpdateCollectionName",
    "dynamic_properties_validate": "DynamicPropertiesValidate",
    "property_collection_to_variant_map": "PropertyCollectionToVariantMap",
    "property_collection_from_variant_map": "PropertyCollectionFromVariantMap",
    "server_level_get_or_add_dynamic_properties": "ServerLevelGetOrAddDynamicProperties",
    "server_level_get_dynamic_properties_manager": "ServerLevelGetDynamicPropertiesManager",
    "dynamic_properties_manager_write_level_storage": "DynamicPropertiesManagerWriteLevelStorage",
    "actor_get_or_add_dynamic_properties": "ActorGetOrAddDynamicProperties",
    "item_dynamic_properties_get_all": "ItemDynamicPropertiesGetAll",
    "item_dynamic_properties_get": "ItemDynamicPropertiesGet",
    "item_dynamic_properties_set": "ItemDynamicPropertiesSet",
    "item_dynamic_properties_remove": "ItemDynamicPropertiesRemove",
    "item_dynamic_properties_clear": "ItemDynamicPropertiesClear",
    "offline_player_storage_read": "OfflinePlayerStorageRead",
    "offline_player_storage_write": "OfflinePlayerStorageWrite",
    "stored_entity_read": "StoredEntityRead",
    "stored_entity_write": "StoredEntityWrite",
    "block_dynamic_properties_get_component": "BlockDynamicPropertiesGetComponent",
    "block_dynamic_properties_mark_dirty": "BlockDynamicPropertiesMarkDirty",
    "hook_dynamic_properties_set": "HookDynamicPropertiesSet",
    "hook_dynamic_properties_remove": "HookDynamicPropertiesRemove",
    "hook_dynamic_properties_clear": "HookDynamicPropertiesClear",
}


def bytes_array(hex_value: str) -> tuple[str, int]:
    raw = bytes.fromhex(hex_value)
    if len(raw) > 24:
        raise SystemExit("fingerprints must be at most 24 bytes")
    padded = raw + b"\x00" * (24 - len(raw))
    return ", ".join(f"0x{value:02X}" for value in padded), len(raw)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("include/endstone_dynamic_properties/generated/native_manifest_data.h"),
    )
    args = parser.parse_args()
    missing = validate(args.manifest, args.root)
    if missing:
        raise SystemExit("activation refused:\n- " + "\n- ".join(missing))
    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    entries: list[str] = []
    for symbol in data["symbols"]:
        fingerprint, size = bytes_array(symbol["fingerprint_hex"])
        entries.append(
            "    {NativeDynamicPropertySymbol::%s, 0x%XULL, {%s}, %d},"
            % (SYMBOL_ENUM[symbol["id"]], symbol["rva"], fingerprint, size)
        )
    lines = [
        "#pragma once", "",
        '#include "endstone_dynamic_properties/native_manifest.h"', "",
        "#include <array>", "#include <cstdint>", "#include <string_view>", "",
        "namespace endstone_dynamic_properties::generated {", "",
        "struct GeneratedSymbolEntry {",
        "    NativeDynamicPropertySymbol symbol{};",
        "    std::uint64_t rva{};",
        "    std::array<std::uint8_t, 24> fingerprint{};",
        "    std::uint8_t fingerprint_size{};",
        "};", "",
        f'inline constexpr std::string_view BdsPackageVersion = "{data["bds_package_version"]}";',
        f'inline constexpr std::string_view RuntimeBds = "{data["runtime_bds"]}";',
        f'inline constexpr std::string_view EndstoneVersion = "{data["endstone_version"]}";',
        f'inline constexpr std::string_view Platform = "{data["platform"]}";',
        f'inline constexpr std::string_view ArchiveSha256 = "{data["archive_sha256"]}";',
        f'inline constexpr std::string_view ExecutableSha256 = "{data["executable"]["sha256"]}";',
        f'inline constexpr std::uint64_t ExecutableSize = {data["executable"]["size"]}ULL;',
        "inline constexpr bool NativeManifestActivated = true;",
        "inline constexpr bool ExactBuildMatch = true;",
        "inline constexpr bool ExactBinaryHashMatch = true;",
        "inline constexpr bool SymbolsValidated = true;",
        "inline constexpr bool StorageContractsValidated = true;",
        "inline constexpr bool ExternalHooksValidated = true;",
        "inline constexpr bool StageProbePassed = true;",
        f"inline constexpr std::array<GeneratedSymbolEntry, {len(entries)}> Symbols{{{{",
        *entries,
        "}};", "", "} // namespace endstone_dynamic_properties::generated", "",
    ]
    output = args.output if args.output.is_absolute() else args.root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
