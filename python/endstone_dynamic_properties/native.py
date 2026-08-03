from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any


EXPECTED_ARCHIVES = {
    "linux-x64": "68c52ababde987741029de091c09cd736fe894bc1fe99cf20f9ed5c659f0c180",
    "windows-x64": "fc6c0ad6f82cfb11c65c6756a1a8e49b21ffa8cc203da587df59df365d82a2ad",
}
EXPECTED_EXECUTABLES = {
    "linux-x64": "bedrock_server",
    "windows-x64": "bedrock_server.exe",
}
EXPECTED_EXECUTABLE_SHA256 = {
    "linux-x64": "61995841f21baf9bfab96e0d9b0cb798501dcc9789dab68e496f3b8e3bc83375",
    "windows-x64": "4a0b867eee6c24310f405410b17e9794441b81ed8f2976cdd4cef54d0c441829",
}
EXPECTED_EXECUTABLE_SIZES = {
    "linux-x64": 232842872,
    "windows-x64": 207171408,
}
REQUIRED_SYMBOLS = (
    "dynamic_properties_get",
    "dynamic_properties_get_ids",
    "dynamic_properties_get_total_bytes",
    "dynamic_properties_set",
    "dynamic_properties_remove",
    "dynamic_properties_clear_collection",
    "dynamic_properties_update_collection_name",
    "dynamic_properties_validate",
    "property_collection_to_variant_map",
    "property_collection_from_variant_map",
    "server_level_get_or_add_dynamic_properties",
    "server_level_get_dynamic_properties_manager",
    "dynamic_properties_manager_write_level_storage",
    "actor_get_or_add_dynamic_properties",
    "item_dynamic_properties_get_all",
    "item_dynamic_properties_get",
    "item_dynamic_properties_set",
    "item_dynamic_properties_remove",
    "item_dynamic_properties_clear",
    "offline_player_storage_read",
    "offline_player_storage_write",
    "stored_entity_read",
    "stored_entity_write",
    "block_dynamic_properties_get_component",
    "block_dynamic_properties_mark_dirty",
    "hook_dynamic_properties_set",
    "hook_dynamic_properties_remove",
    "hook_dynamic_properties_clear",
)
REQUIRED_STAGE_PROBES = (
    "world_get_set_remove_clear",
    "world_list_ids_and_byte_count",
    "world_bulk_set",
    "world_collection_rename",
    "world_restart_persistence",
    "online_player_get_set_remove_clear",
    "online_player_disconnect_reconnect",
    "offline_player_read_while_offline",
    "offline_player_write_while_offline",
    "offline_player_join_after_write",
    "offline_player_restart_persistence",
    "loaded_entity_get_set_remove_clear",
    "stored_entity_read_while_unloaded",
    "stored_entity_write_while_unloaded",
    "stored_entity_chunk_reload",
    "stored_entity_restart_persistence",
    "main_inventory_item_properties",
    "armor_item_properties",
    "offhand_item_properties",
    "ender_chest_item_properties",
    "block_container_item_properties",
    "dropped_item_properties",
    "item_slot_client_refresh",
    "item_stackability_guard",
    "item_slot_stale_revision_guard",
    "block_dynamic_property_read_write",
    "block_dynamic_property_remove_clear",
    "block_dynamic_property_chunk_reload",
    "block_dynamic_property_restart_persistence",
    "block_replacement_cleanup",
    "property_copy",
    "property_move",
    "collection_copy",
    "collection_move",
    "behavior_pack_uuid_migration",
    "export_import_round_trip",
    "plugin_collection_isolation",
    "raw_admin_collection_access",
    "cross_target_atomic_transaction",
    "transaction_rollback",
    "stale_revision_conflict",
    "persistence_flush",
    "external_script_set_observed",
    "external_script_remove_observed",
    "external_script_clear_observed",
    "external_script_set_cancelled",
    "external_script_remove_cancelled",
    "external_script_clear_cancelled",
    "hook_recursion_guard",
    "world_load_event_suppression",
    "rollback_event_suppression",
    "audit_records_complete",
    "no_live_leveldb_editing",
    "server_shutdown_flush",
    "crash_recovery_no_partial_commit",
)

_ABI_TEXT_FIELDS = (
    "reviewer",
    "property_variant_contract",
    "vector3_argument_contract",
    "reflection_context_contract",
    "actor_component_contract",
    "item_stack_mutation_contract",
    "offline_player_storage_contract",
    "stored_entity_storage_contract",
    "block_component_contract",
    "hook_calling_convention_notes",
)
_EXTERNAL_HOOK_FIELDS = (
    "installed",
    "set_before_mutation",
    "remove_before_mutation",
    "clear_before_mutation",
    "cancellable",
    "original_call_preserved",
    "recursion_guard_verified",
    "load_suppression_verified",
    "rollback_suppression_verified",
)
_STORAGE_FIELDS = (
    "offline_player_read_write_verified",
    "stored_entity_read_write_verified",
    "main_thread_coordination_verified",
    "no_direct_live_leveldb_writes",
    "crash_safe_commit_verified",
)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX64_ANY_CASE = re.compile(r"^[0-9a-fA-F]{64}$")
_HEX_BYTES = re.compile(r"^[0-9a-fA-F]+$")
_COMMIT_HASH = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


@dataclass(frozen=True, slots=True)
class NativeManifestStatus:
    valid: bool
    message: str
    platform: str = ""
    bds_package_version: str = ""
    errors: tuple[str, ...] = ()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repository_root(path: Path) -> Path:
    resolved = path.resolve()
    for parent in resolved.parents:
        if (parent / "native/probes/STAGE_PROBE_TEMPLATE.json").is_file():
            return parent
    return resolved.parent


def _evidence_path(root: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    relative = Path(value)
    if relative.is_absolute():
        return None
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _report_timestamp(value: object, field: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be an ISO-8601 timestamp")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{field} must be an ISO-8601 timestamp")
        return None
    if parsed.tzinfo is None:
        errors.append(f"{field} must include a timezone")
        return None
    return parsed


def stage_probe_report_errors(data: object) -> tuple[str, ...]:
    """Return every standalone stage-report validation failure.

    Manifest verification additionally binds a valid report to the exact
    manifest identities. Keeping the standalone checks here lets the command
    line report validator and the activation gate use identical semantics.
    """
    if not isinstance(data, dict):
        return ("report root must be an object",)

    errors: list[str] = []
    if data.get("schema") != 1:
        errors.append("schema must be 1")
    if data.get("platform") not in EXPECTED_ARCHIVES:
        errors.append("platform must be linux-x64 or windows-x64")
    if data.get("bds_package_version") != "1.26.33.1":
        errors.append("wrong BDS package version")
    if data.get("runtime_bds") != "26.33":
        errors.append("wrong BDS runtime")
    if data.get("endstone_version") != "0.11.6":
        errors.append("wrong Endstone version")
    for field in ("executable_sha256", "bridge_sha256"):
        if not _HEX64_ANY_CASE.fullmatch(str(data.get(field, ""))):
            errors.append(f"{field} must be a 64-digit hexadecimal SHA-256")

    started = _report_timestamp(data.get("started_at"), "started_at", errors)
    completed = _report_timestamp(data.get("completed_at"), "completed_at", errors)
    if started is not None and completed is not None and completed < started:
        errors.append("completed_at precedes started_at")
    if data.get("passed") is not True:
        errors.append("report is not marked passed")

    if isinstance(data.get("results"), dict):
        results = data["results"]
    else:
        results = {}
        errors.append("results must be an object")
    required = set(REQUIRED_STAGE_PROBES)
    if set(results) != required:
        missing = sorted(required - set(results))
        unexpected = sorted(set(results) - required)
        if missing:
            errors.append("missing probes: " + ", ".join(missing))
        if unexpected:
            errors.append("unexpected probes: " + ", ".join(unexpected))
    for name in REQUIRED_STAGE_PROBES:
        result = results.get(name)
        if not isinstance(result, dict):
            errors.append(f"probe {name} must be an object")
            continue
        if result.get("passed") is not True:
            errors.append(f"probe {name} did not pass")
        if not isinstance(result.get("notes"), str) or not result["notes"].strip():
            errors.append(f"probe {name} has no notes")
        if not _HEX64_ANY_CASE.fullmatch(str(result.get("evidence_sha256", ""))):
            errors.append(f"probe {name} has an invalid evidence hash")
    return tuple(errors)


def _stage_report_binding_errors(
    report: object,
    manifest: dict[str, Any],
    stage: dict[str, Any],
    executable: dict[str, Any],
    bridge: dict[str, Any],
) -> tuple[str, ...]:
    errors = [f"stage_probe report: {error}" for error in stage_probe_report_errors(report)]
    if not isinstance(report, dict):
        return tuple(errors)

    bindings = (
        ("platform", manifest.get("platform")),
        ("bds_package_version", manifest.get("bds_package_version")),
        ("runtime_bds", manifest.get("runtime_bds")),
        ("endstone_version", manifest.get("endstone_version")),
        ("executable_sha256", executable.get("sha256")),
        ("bridge_sha256", bridge.get("source_sha256")),
    )
    for field, expected in bindings:
        if report.get(field) != expected:
            errors.append(f"stage_probe report {field} must match manifest")

    if report.get("passed") is not stage.get("passed"):
        errors.append("stage_probe report passed must match manifest")

    report_results = _mapping(report.get("results"))
    manifest_results = _mapping(stage.get("results"))
    if set(report_results) != set(manifest_results):
        errors.append("stage_probe report result set must match manifest")
    for name in REQUIRED_STAGE_PROBES:
        report_result = _mapping(report_results.get(name))
        if report_result.get("passed") is not manifest_results.get(name):
            errors.append(f"stage_probe report result {name} must match manifest")
    return tuple(errors)


def _validation_errors(data: object, root: Path) -> tuple[str, ...]:
    if not isinstance(data, dict):
        return ("manifest root must be an object",)

    errors: list[str] = []
    if data.get("schema") != 1:
        errors.append("schema=1")
    platform = data.get("platform")
    if platform not in EXPECTED_ARCHIVES:
        errors.append("supported platform")
    if data.get("bds_package_version") != "1.26.33.1":
        errors.append("bds_package_version=1.26.33.1")
    if data.get("runtime_bds") != "26.33":
        errors.append("runtime_bds=26.33")
    if data.get("endstone_version") != "0.11.6":
        errors.append("endstone_version=0.11.6")
    if platform in EXPECTED_ARCHIVES and data.get("archive_sha256") != EXPECTED_ARCHIVES[platform]:
        errors.append("official archive SHA-256")

    executable = _mapping(data.get("executable"))
    if platform in EXPECTED_EXECUTABLES and executable.get("filename") != EXPECTED_EXECUTABLES[platform]:
        errors.append("executable.filename")
    if not _HEX64.fullmatch(str(executable.get("sha256", ""))):
        errors.append("executable.sha256")
    if (platform in EXPECTED_EXECUTABLE_SHA256
            and executable.get("sha256") != EXPECTED_EXECUTABLE_SHA256[platform]):
        errors.append("exact executable SHA-256")
    executable_size = executable.get("size")
    if isinstance(executable_size, bool) or not isinstance(executable_size, int) or executable_size <= 0:
        errors.append("executable.size")
    if (platform in EXPECTED_EXECUTABLE_SIZES
            and executable_size != EXPECTED_EXECUTABLE_SIZES[platform]):
        errors.append("exact executable size")

    abi = _mapping(data.get("abi"))
    if abi.get("reviewed") is not True:
        errors.append("abi.reviewed")
    for field in _ABI_TEXT_FIELDS:
        if not isinstance(abi.get(field), str) or not abi[field].strip():
            errors.append(f"abi.{field}")
    if not _COMMIT_HASH.fullmatch(str(abi.get("review_commit", ""))):
        errors.append("abi.review_commit")

    symbol_entries = data.get("symbols")
    if not isinstance(symbol_entries, list):
        symbol_entries = []
    symbols = {
        entry.get("id"): entry
        for entry in symbol_entries
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    }
    required_symbols = set(REQUIRED_SYMBOLS)
    if (set(symbols) != required_symbols or len(symbol_entries) != len(required_symbols)
            or len(symbols) != len(symbol_entries)):
        errors.append("exact required symbol set")
    for symbol in REQUIRED_SYMBOLS:
        entry = _mapping(symbols.get(symbol))
        for flag in ("resolved", "unique", "signature_verified", "behavior_verified"):
            if entry.get(flag) is not True:
                errors.append(f"symbols.{symbol}.{flag}")
        rva = entry.get("rva")
        if isinstance(rva, bool) or not isinstance(rva, int) or rva <= 0:
            errors.append(f"symbols.{symbol}.rva")
        fingerprint = str(entry.get("fingerprint_hex", ""))
        if not fingerprint or len(fingerprint) % 2 or not _HEX_BYTES.fullmatch(fingerprint):
            errors.append(f"symbols.{symbol}.fingerprint_hex")
        elif len(bytes.fromhex(fingerprint)) > 24:
            errors.append(f"symbols.{symbol}.fingerprint_hex<=24-bytes")
        if not isinstance(entry.get("verification_notes"), str) or not entry["verification_notes"].strip():
            errors.append(f"symbols.{symbol}.verification_notes")

    hooks = _mapping(data.get("external_hooks"))
    for field in _EXTERNAL_HOOK_FIELDS:
        if hooks.get(field) is not True:
            errors.append(f"external_hooks.{field}")

    storage = _mapping(data.get("storage"))
    for field in _STORAGE_FIELDS:
        if storage.get(field) is not True:
            errors.append(f"storage.{field}")

    bridge = _mapping(data.get("bridge"))
    stage = _mapping(data.get("stage_probe"))
    if stage.get("passed") is not True:
        errors.append("stage_probe.passed")
    report_hash = str(stage.get("report_sha256", ""))
    if not _HEX64.fullmatch(report_hash):
        errors.append("stage_probe.report_sha256")
    results = _mapping(stage.get("results"))
    if set(results) != set(REQUIRED_STAGE_PROBES):
        errors.append("exact required stage-probe set")
    for probe in REQUIRED_STAGE_PROBES:
        if results.get(probe) is not True:
            errors.append(f"stage_probe.results.{probe}")
    report_path = _evidence_path(root, stage.get("report_path"))
    if report_path is None or not report_path.is_file():
        errors.append("stage_probe.report_path")
    else:
        try:
            report_bytes = report_path.read_bytes()
        except OSError:
            errors.append("stage_probe report readable")
        else:
            if (_HEX64.fullmatch(report_hash)
                    and hashlib.sha256(report_bytes).hexdigest() != report_hash):
                errors.append("stage_probe report SHA-256 match")
            try:
                report = json.loads(report_bytes.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                errors.append("stage_probe report must be valid UTF-8 JSON")
            else:
                errors.extend(_stage_report_binding_errors(
                    report, data, stage, executable, bridge,
                ))

    if bridge.get("reviewed") is not True:
        errors.append("bridge.reviewed")
    bridge_hash = str(bridge.get("source_sha256", ""))
    if not _HEX64.fullmatch(bridge_hash):
        errors.append("bridge.source_sha256")
    bridge_path = _evidence_path(root, bridge.get("source_path"))
    if bridge_path is None or not bridge_path.is_file():
        errors.append("bridge.source_path")
    elif _HEX64.fullmatch(bridge_hash) and _sha256(bridge_path) != bridge_hash:
        errors.append("bridge source SHA-256 match")

    if data.get("status") != "verified":
        errors.append("status=verified")
    return tuple(errors)


def verify_native_manifest(
    path: str | Path,
    *,
    root: str | Path | None = None,
) -> NativeManifestStatus:
    manifest_path = Path(path)
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return NativeManifestStatus(False, str(exc), errors=(str(exc),))

    platform = str(data.get("platform", "")) if isinstance(data, dict) else ""
    version = str(data.get("bds_package_version", "")) if isinstance(data, dict) else ""
    repository_root = Path(root).resolve() if root is not None else _repository_root(manifest_path)
    errors = _validation_errors(data, repository_root)
    if errors:
        prefix = "manifest is not verified" if isinstance(data, dict) and data.get("status") != "verified" else "manifest is incomplete"
        return NativeManifestStatus(
            False,
            f"{prefix}: " + ", ".join(errors),
            platform,
            version,
            errors,
        )
    return NativeManifestStatus(
        True,
        "manifest is verified and complete",
        platform,
        version,
    )


def native_manifest_errors(path: str | Path, *, root: str | Path | None = None) -> tuple[str, ...]:
    """Return every closed-gate reason for tooling and activation workflows."""
    return verify_native_manifest(path, root=root).errors
