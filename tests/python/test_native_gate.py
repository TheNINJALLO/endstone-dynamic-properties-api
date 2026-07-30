from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from endstone_dynamic_properties import REQUIRED_SYMBOLS, verify_native_manifest


ROOT = Path(__file__).resolve().parents[2]
VERIFY_TOOL = ROOT / "tools" / "verify_native_manifest.py"


def _run_tool(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VERIFY_TOOL), str(path), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_blocked_manifest_is_rejected(tmp_path: Path):
    manifest = {
        "status": "blocked",
        "platform": "linux-x64",
        "bds_package_version": "1.26.33.1",
        "symbols": [
            {"id": symbol, "resolved": False, "unique": False,
             "signature_verified": False, "behavior_verified": False}
            for symbol in REQUIRED_SYMBOLS
        ],
        "stage_probe": {"passed": False},
        "bridge": {"reviewed": False},
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    result = verify_native_manifest(path)
    assert not result.valid
    assert "not verified" in result.message


def test_missing_symbol_is_rejected(tmp_path: Path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"status": "verified", "symbols": []}), encoding="utf-8")
    result = verify_native_manifest(path)
    assert not result.valid
    assert "exact required symbol set" in result.message


def test_forged_verified_manifest_cannot_omit_proof_sections(tmp_path: Path):
    manifest = {
        "status": "verified",
        "symbols": [
            {
                "id": symbol,
                "resolved": True,
                "unique": True,
                "signature_verified": True,
                "behavior_verified": True,
                "rva": 1,
                "fingerprint_hex": "aa",
                "verification_notes": "forged",
            }
            for symbol in REQUIRED_SYMBOLS
        ],
        "stage_probe": {"passed": True},
        "bridge": {"reviewed": True},
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    result = verify_native_manifest(path)
    assert not result.valid
    assert "executable.sha256" in result.errors
    assert "storage.offline_player_read_write_verified" in result.errors
    assert "external_hooks.installed" in result.errors


def test_duplicate_symbol_ids_are_rejected(tmp_path: Path):
    symbols = [
        {"id": symbol, "resolved": True, "unique": True,
         "signature_verified": True, "behavior_verified": True}
        for symbol in REQUIRED_SYMBOLS
    ]
    symbols.append(dict(symbols[0]))
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"status": "verified", "symbols": symbols}), encoding="utf-8")
    result = verify_native_manifest(path)
    assert not result.valid
    assert "exact required symbol set" in result.errors


def test_allow_incomplete_accepts_only_declared_blocked_manifest(tmp_path: Path):
    blocked = tmp_path / "blocked.json"
    blocked.write_text(json.dumps({"status": "blocked"}), encoding="utf-8")
    assert _run_tool(blocked, "--allow-incomplete").returncode == 0

    verified = tmp_path / "verified.json"
    verified.write_text(json.dumps({"status": "verified"}), encoding="utf-8")
    assert _run_tool(verified, "--allow-incomplete").returncode != 0


def test_allow_incomplete_rejects_missing_or_malformed_manifest(tmp_path: Path):
    assert _run_tool(tmp_path / "missing.json", "--allow-incomplete").returncode != 0

    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    assert _run_tool(malformed, "--allow-incomplete").returncode != 0
