from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile

import pytest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (
    ROOT
    / "examples"
    / "python"
    / "dynamic_properties_tester_plugin"
    / "src"
    / "endstone_dynamic_properties_tester"
    / "report.py"
)
SPEC = importlib.util.spec_from_file_location(
    "_dynamic_properties_tester_report_tests", SOURCE
)
assert SPEC is not None and SPEC.loader is not None
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)


def test_atomic_report_checkpoint_round_trip_and_integrity() -> None:
    report = REPORT.new_report(mode="acceptance", operator="operator", scopes=["world"])
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        path = REPORT.save_report(folder, report, checkpoint=True)
        assert path.is_file()
        assert REPORT.latest_report_path(folder).is_file()
        assert REPORT.checkpoint_path(folder).is_file()
        assert not list(folder.rglob("*.tmp"))
        assert REPORT.load_report(path) == report
        assert len(report["integrity"]["digest"]) == 64


def test_integrity_check_rejects_tampering() -> None:
    report = REPORT.new_report(mode="acceptance", operator="operator", scopes=["world"])
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        path = REPORT.save_report(folder, report, checkpoint=False)
        document = json.loads(path.read_text(encoding="utf-8"))
        document["outcome"] = "passed"
        path.write_text(json.dumps(document), encoding="utf-8")
        with pytest.raises(ValueError, match="integrity check failed"):
            REPORT.load_report(path)


def test_interruption_recovery_claims_only_unresolved_fixed_set_intent() -> None:
    report = REPORT.new_report(mode="acceptance", operator="operator", scopes=["world"])
    target = {"kind": "world", "world_id": "test"}
    report["operations"] = [
        {
            "name": "set_value",
            "status": "intent",
            "target": target,
            "collection": REPORT.COLLECTION,
            "key": "dptest.unique",
            "value": "owned-token",
        },
        {"name": "clear_collection", "status": "intent", "target": target},
    ]
    recovered = REPORT.recover_interrupted(report)
    assert report["state"] == "interrupted"
    assert len(recovered) == 1
    assert recovered[0]["key"] == "dptest.unique"
    assert recovered[0]["value"] == "owned-token"
    assert recovered[0]["collection"] == REPORT.COLLECTION
