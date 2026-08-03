from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import pytest

from endstone_dynamic_properties.native import (
    EXPECTED_ARCHIVES,
    REQUIRED_STAGE_PROBES,
    REQUIRED_SYMBOLS,
    verify_native_manifest,
)


ROOT = Path(__file__).resolve().parents[2]
EXECUTABLE_IDENTITIES = {
    "linux-x64": (
        "bedrock_server",
        "61995841f21baf9bfab96e0d9b0cb798501dcc9789dab68e496f3b8e3bc83375",
        232842872,
    ),
    "windows-x64": (
        "bedrock_server.exe",
        "4a0b867eee6c24310f405410b17e9794441b81ed8f2976cdd4cef54d0c441829",
        207171408,
    ),
}


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")


def _verified_fixture(
    tmp_path: Path,
) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    platform = "linux-x64"
    executable_filename, executable_sha256, executable_size = EXECUTABLE_IDENTITIES[
        platform
    ]

    bridge_path = tmp_path / "bridge.cpp"
    bridge_path.write_text("// reviewed exact-build bridge\n", encoding="utf-8")
    bridge_sha256 = _file_sha256(bridge_path)

    report = {
        "schema": 1,
        "platform": platform,
        "bds_package_version": "1.26.33.1",
        "runtime_bds": "26.33",
        "endstone_version": "0.11.6",
        "executable_sha256": executable_sha256,
        "bridge_sha256": bridge_sha256,
        "started_at": "2026-07-30T12:00:00Z",
        "completed_at": "2026-07-30T12:30:00Z",
        "passed": True,
        "results": {
            probe: {
                "passed": True,
                "notes": f"verified {probe}",
                "evidence_sha256": hashlib.sha256(probe.encode("utf-8")).hexdigest(),
            }
            for probe in REQUIRED_STAGE_PROBES
        },
    }
    report_path = tmp_path / "stage-report.json"
    _write_json(report_path, report)

    manifest = {
        "schema": 1,
        "status": "verified",
        "platform": platform,
        "bds_package_version": "1.26.33.1",
        "runtime_bds": "26.33",
        "endstone_version": "0.11.6",
        "archive_sha256": EXPECTED_ARCHIVES[platform],
        "executable": {
            "filename": executable_filename,
            "sha256": executable_sha256,
            "size": executable_size,
        },
        "abi": {
            "reviewed": True,
            "reviewer": "test reviewer",
            "review_commit": "c" * 40,
            "property_variant_contract": "verified",
            "vector3_argument_contract": "verified",
            "reflection_context_contract": "verified",
            "actor_component_contract": "verified",
            "item_stack_mutation_contract": "verified",
            "offline_player_storage_contract": "verified",
            "stored_entity_storage_contract": "verified",
            "block_component_contract": "verified",
            "hook_calling_convention_notes": "verified",
        },
        "symbols": [
            {
                "id": symbol,
                "resolved": True,
                "unique": True,
                "signature_verified": True,
                "behavior_verified": True,
                "rva": index + 1,
                "fingerprint_hex": "aa",
                "verification_notes": "verified",
            }
            for index, symbol in enumerate(REQUIRED_SYMBOLS)
        ],
        "external_hooks": {
            "installed": True,
            "set_before_mutation": True,
            "remove_before_mutation": True,
            "clear_before_mutation": True,
            "cancellable": True,
            "original_call_preserved": True,
            "recursion_guard_verified": True,
            "load_suppression_verified": True,
            "rollback_suppression_verified": True,
        },
        "storage": {
            "offline_player_read_write_verified": True,
            "stored_entity_read_write_verified": True,
            "main_thread_coordination_verified": True,
            "no_direct_live_leveldb_writes": True,
            "crash_safe_commit_verified": True,
        },
        "stage_probe": {
            "report_path": report_path.name,
            "report_sha256": _file_sha256(report_path),
            "passed": True,
            "results": {probe: True for probe in REQUIRED_STAGE_PROBES},
        },
        "bridge": {
            "source_path": bridge_path.name,
            "source_sha256": bridge_sha256,
            "reviewed": True,
        },
    }
    manifest_path = tmp_path / "manifest.json"
    _write_json(manifest_path, manifest)
    return manifest_path, report_path, manifest, report


def _rewrite_evidence(
    manifest_path: Path,
    report_path: Path,
    manifest: dict[str, Any],
    report: object,
) -> None:
    _write_json(report_path, report)
    manifest["stage_probe"]["report_sha256"] = _file_sha256(report_path)
    _write_json(manifest_path, manifest)


@pytest.mark.parametrize(
    ("platform", "filename", "sha256", "size"),
    [(platform, *identity) for platform, identity in EXECUTABLE_IDENTITIES.items()],
)
def test_blocked_manifests_record_only_verified_executable_identity(
    platform: str,
    filename: str,
    sha256: str,
    size: int,
):
    path = ROOT / "native" / "manifests" / f"{platform}-1.26.33.1.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))

    assert manifest["status"] == "blocked"
    assert manifest["executable"] == {
        "filename": filename,
        "sha256": sha256,
        "size": size,
    }
    assert not verify_native_manifest(path, root=ROOT).valid


def test_complete_cross_bound_evidence_opens_gate(tmp_path: Path):
    manifest_path, _, _, _ = _verified_fixture(tmp_path)

    result = verify_native_manifest(manifest_path, root=tmp_path)

    assert result.valid, result.message


@pytest.mark.parametrize(
    ("field", "tampered_value"),
    [
        ("platform", "windows-x64"),
        ("bds_package_version", "1.26.33.2"),
        ("runtime_bds", "26.34"),
        ("endstone_version", "0.11.7"),
        ("executable_sha256", "d" * 64),
        ("bridge_sha256", "e" * 64),
    ],
)
def test_report_identity_tampering_is_rejected_even_with_updated_report_hash(
    tmp_path: Path,
    field: str,
    tampered_value: str,
):
    manifest_path, report_path, manifest, report = _verified_fixture(tmp_path)
    report[field] = tampered_value
    _rewrite_evidence(manifest_path, report_path, manifest, report)

    result = verify_native_manifest(manifest_path, root=tmp_path)

    assert not result.valid
    assert f"stage_probe report {field} must match manifest" in result.errors


def test_coordinated_manifest_and_report_executable_tampering_is_rejected(
    tmp_path: Path,
):
    manifest_path, report_path, manifest, report = _verified_fixture(tmp_path)
    tampered_sha256 = "d" * 64
    manifest["executable"]["sha256"] = tampered_sha256
    report["executable_sha256"] = tampered_sha256
    _rewrite_evidence(manifest_path, report_path, manifest, report)

    result = verify_native_manifest(manifest_path, root=tmp_path)

    assert not result.valid
    assert "exact executable SHA-256" in result.errors


def test_manifest_executable_size_tampering_is_rejected(tmp_path: Path):
    manifest_path, _, manifest, _ = _verified_fixture(tmp_path)
    manifest["executable"]["size"] += 1
    _write_json(manifest_path, manifest)

    result = verify_native_manifest(manifest_path, root=tmp_path)

    assert not result.valid
    assert "exact executable size" in result.errors


def test_report_passed_flag_is_cross_bound(tmp_path: Path):
    manifest_path, report_path, manifest, report = _verified_fixture(tmp_path)
    report["passed"] = False
    _rewrite_evidence(manifest_path, report_path, manifest, report)

    result = verify_native_manifest(manifest_path, root=tmp_path)

    assert not result.valid
    assert "stage_probe report passed must match manifest" in result.errors


def test_report_result_set_is_cross_bound(tmp_path: Path):
    manifest_path, report_path, manifest, report = _verified_fixture(tmp_path)
    report["results"].pop(REQUIRED_STAGE_PROBES[0])
    _rewrite_evidence(manifest_path, report_path, manifest, report)

    result = verify_native_manifest(manifest_path, root=tmp_path)

    assert not result.valid
    assert "stage_probe report result set must match manifest" in result.errors


def test_report_probe_passed_flag_is_cross_bound(tmp_path: Path):
    manifest_path, report_path, manifest, report = _verified_fixture(tmp_path)
    probe = REQUIRED_STAGE_PROBES[0]
    report["results"][probe]["passed"] = False
    _rewrite_evidence(manifest_path, report_path, manifest, report)

    result = verify_native_manifest(manifest_path, root=tmp_path)

    assert not result.valid
    assert f"stage_probe report result {probe} must match manifest" in result.errors


@pytest.mark.parametrize(
    ("tamper", "expected_error"),
    [
        (
            lambda result: result.__setitem__("notes", ""),
            "has no notes",
        ),
        (
            lambda result: result.__setitem__("evidence_sha256", "not-a-sha256"),
            "has an invalid evidence hash",
        ),
    ],
)
def test_report_probe_evidence_fields_are_mandatory(
    tmp_path: Path,
    tamper: Callable[[dict[str, Any]], None],
    expected_error: str,
):
    manifest_path, report_path, manifest, report = _verified_fixture(tmp_path)
    probe = REQUIRED_STAGE_PROBES[0]
    tamper(report["results"][probe])
    _rewrite_evidence(manifest_path, report_path, manifest, report)

    result = verify_native_manifest(manifest_path, root=tmp_path)

    assert not result.valid
    assert any(expected_error in error for error in result.errors)


def test_report_must_be_parsed_not_only_hash_matched(tmp_path: Path):
    manifest_path, report_path, manifest, _ = _verified_fixture(tmp_path)
    report_path.write_text("{", encoding="utf-8")
    manifest["stage_probe"]["report_sha256"] = _file_sha256(report_path)
    _write_json(manifest_path, manifest)

    result = verify_native_manifest(manifest_path, root=tmp_path)

    assert not result.valid
    assert "stage_probe report must be valid UTF-8 JSON" in result.errors
