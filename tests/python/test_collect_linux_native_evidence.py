from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from collect_linux_native_evidence import (  # noqa: E402
    NativeEvidenceError,
    executable_identity,
    is_relevant_symbol,
    load_manifest,
    parse_nm_line,
    verify_identity,
)


def test_parse_nm_portable_output() -> None:
    parsed = parse_nm_line("_ZN17DynamicProperties18getDynamicPropertyEv T 1a20 4f")

    assert parsed == {
        "mangled_name": "_ZN17DynamicProperties18getDynamicPropertyEv",
        "type": "T",
        "rva": 0x1A20,
        "size": 0x4F,
    }
    assert parse_nm_line("not portable nm output") is None


@pytest.mark.parametrize(
    "name",
    [
        "_ZN17DynamicProperties18getDynamicPropertyEv",
        "_ZN11ServerLevel29getDynamicPropertiesManagerEv",
        "_ZN24DynamicPropertiesManager19writeToLevelStorageEv",
        "ItemDynamicPropertiesHelper",
    ],
)
def test_relevant_symbol_terms_survive_mangling(name: str) -> None:
    assert is_relevant_symbol(name)


def test_unrelated_symbol_is_excluded() -> None:
    assert not is_relevant_symbol("_ZN5Actor7getNameEv")


def test_executable_identity_requires_elf_and_matches_manifest(tmp_path: Path) -> None:
    binary = tmp_path / "bedrock_server"
    contents = b"\x7fELF" + b"exact-test-binary"
    binary.write_bytes(contents)
    identity = executable_identity(binary)

    assert identity == {
        "filename": "bedrock_server",
        "sha256": hashlib.sha256(contents).hexdigest(),
        "size": len(contents),
    }
    verify_identity(identity, {"executable": identity})


def test_identity_mismatch_fails_before_symbol_collection(tmp_path: Path) -> None:
    binary = tmp_path / "bedrock_server"
    binary.write_bytes(b"\x7fELFdifferent")
    identity = executable_identity(binary)

    with pytest.raises(NativeEvidenceError, match="sha256"):
        verify_identity(
            identity,
            {"executable": {**identity, "sha256": "0" * 64}},
        )


def test_non_elf_is_rejected(tmp_path: Path) -> None:
    binary = tmp_path / "bedrock_server"
    binary.write_bytes(b"not an ELF")

    with pytest.raises(NativeEvidenceError, match="not an ELF"):
        executable_identity(binary)


def test_manifest_must_be_linux_x64(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"platform": "windows-x64", "executable": {}}),
        encoding="utf-8",
    )

    with pytest.raises(NativeEvidenceError, match="linux-x64"):
        load_manifest(manifest)
