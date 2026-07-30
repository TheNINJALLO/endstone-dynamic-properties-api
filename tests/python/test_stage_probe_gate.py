from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "tools" / "validate_stage_probe_report.py"


def _run_validator(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), str(path)],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )


def test_empty_stage_probe_result_set_is_rejected(tmp_path: Path):
    report = {
        "schema": 1,
        "platform": "linux-x64",
        "bds_package_version": "1.26.33.1",
        "runtime_bds": "26.33",
        "endstone_version": "0.11.6",
        "executable_sha256": "a" * 64,
        "bridge_sha256": "b" * 64,
        "started_at": "2026-07-29T20:00:00Z",
        "completed_at": "2026-07-29T20:01:00Z",
        "passed": True,
        "results": {},
    }
    path = tmp_path / "empty.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    result = _run_validator(path)
    assert result.returncode != 0
    assert "missing probes" in result.stderr


def test_stage_probe_evidence_hash_must_be_hexadecimal(tmp_path: Path):
    report = json.loads((ROOT / "native" / "probes" / "STAGE_PROBE_TEMPLATE.json").read_text())
    report.update({
        "platform": "windows-x64",
        "executable_sha256": "a" * 64,
        "bridge_sha256": "b" * 64,
        "started_at": "2026-07-29T20:00:00+00:00",
        "completed_at": "2026-07-29T20:01:00+00:00",
        "passed": True,
    })
    for result in report["results"].values():
        result.update({"passed": True, "notes": "verified", "evidence_sha256": "z" * 64})
    path = tmp_path / "non-hex.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    result = _run_validator(path)
    assert result.returncode != 0
    assert "invalid evidence hash" in result.stderr
