from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_live_server_acceptance import (
    AcceptanceFailure,
    _report_digest,
    validate_reports,
)


REQUIRED_CAPABILITIES = {
    "world": True,
    "read": True,
    "write": True,
    "remove": True,
    "clear": True,
    "list_ids": True,
    "list_collections": True,
    "byte_count": True,
    "persistence_flush": True,
    "external_change_observation": True,
    "external_change_cancellation": True,
    "exact_build_match": True,
    "exact_binary_hash_match": True,
    "symbols_validated": True,
}


def _write_report(directory: Path, name: str, report: dict[str, object]) -> None:
    report["integrity"] = {
        "algorithm": "sha256",
        "digest": _report_digest(report),
    }
    (directory / name).write_text(
        json.dumps(report, ensure_ascii=False), encoding="utf-8"
    )


def _reports(tmp_path: Path) -> Path:
    reports = tmp_path / "plugins" / "dynamic_properties_tester" / "reports"
    reports.mkdir(parents=True)
    _write_report(
        reports,
        "inventory.json",
        {
            "run_id": "1" * 32,
            "mode": "inventory",
            "state": "completed",
            "outcome": "inventory_captured",
        },
    )
    _write_report(
        reports,
        "acceptance.json",
        {
            "run_id": "2" * 32,
            "mode": "acceptance",
            "state": "completed",
            "outcome": "passed",
            "checks": [{"name": "world.round_trip", "passed": True}],
            "service_status": {
                "available": True,
                "operational_live": True,
                "adapter": "experimental-live",
                "capabilities": dict(REQUIRED_CAPABILITIES),
            },
        },
    )
    _write_report(
        reports,
        "hook-probe.json",
        {
            "run_id": "3" * 32,
            "mode": "external_watch",
            "state": "completed",
            "outcome": "external_hook_probe_passed",
        },
    )
    _write_report(
        reports,
        "persistence.json",
        {
            "run_id": "4" * 32,
            "mode": "persistence",
            "state": "completed",
            "outcome": "persistence_passed",
        },
    )
    return tmp_path


def test_validate_reports_requires_crud_inventory_hooks_and_restart(tmp_path: Path) -> None:
    summary = validate_reports(_reports(tmp_path))

    assert summary["result"] == "passed"
    assert summary["report_count"] == 4
    assert summary["acceptance_checks"] == 1


def test_validate_reports_rejects_missing_live_capability(tmp_path: Path) -> None:
    server = _reports(tmp_path)
    acceptance_path = next(server.glob("plugins/**/reports/acceptance.json"))
    acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
    acceptance.pop("integrity")
    acceptance["service_status"]["capabilities"]["external_change_cancellation"] = (
        False
    )
    _write_report(acceptance_path.parent, acceptance_path.name, acceptance)

    with pytest.raises(AcceptanceFailure, match="external_change_cancellation"):
        validate_reports(server)
