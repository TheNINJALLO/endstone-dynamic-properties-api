from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from collect_linux_native_evidence import (  # noqa: E402
    NativeEvidenceError,
    executable_identity,
    is_relevant_symbol,
    load_manifest,
    read_elf,
    scan_symbols,
    verify_identity,
)


ELF_HEADER = struct.Struct("<16sHHIQQQIHHHHHH")
SECTION_HEADER = struct.Struct("<IIQQQQIIQQ")
SYMBOL_ENTRY = struct.Struct("<IBBHQQ")


def _write_test_elf(path: Path) -> None:
    relevant = b"_ZN17DynamicProperties18getDynamicPropertyEv"
    unrelated = b"_ZN5Actor7getNameEv"
    strings = b"\0" + relevant + b"\0" + unrelated + b"\0"
    relevant_offset = 1
    unrelated_offset = relevant_offset + len(relevant) + 1
    symbols = b"".join(
        [
            SYMBOL_ENTRY.pack(0, 0, 0, 0, 0, 0),
            SYMBOL_ENTRY.pack(relevant_offset, 0x12, 0, 2, 0x1A20, 0x4F),
            SYMBOL_ENTRY.pack(unrelated_offset, 0x12, 0, 2, 0x1B00, 0x20),
        ]
    )
    strings_offset = ELF_HEADER.size
    symbols_offset = (strings_offset + len(strings) + 7) & ~7
    sections_offset = (symbols_offset + len(symbols) + 7) & ~7
    ident = b"\x7fELF" + bytes([2, 1, 1]) + b"\0" * 9
    header = ELF_HEADER.pack(
        ident,
        3,
        62,
        1,
        0x1000,
        0,
        sections_offset,
        0,
        ELF_HEADER.size,
        0,
        0,
        SECTION_HEADER.size,
        3,
        0,
    )
    section_headers = b"".join(
        [
            SECTION_HEADER.pack(0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            SECTION_HEADER.pack(
                0, 3, 0, 0, strings_offset, len(strings), 0, 0, 1, 0
            ),
            SECTION_HEADER.pack(
                0,
                11,
                0,
                0,
                symbols_offset,
                len(symbols),
                1,
                1,
                8,
                SYMBOL_ENTRY.size,
            ),
        ]
    )
    contents = bytearray(sections_offset + len(section_headers))
    contents[: len(header)] = header
    contents[strings_offset : strings_offset + len(strings)] = strings
    contents[symbols_offset : symbols_offset + len(symbols)] = symbols
    contents[sections_offset:] = section_headers
    path.write_bytes(contents)


def test_builtin_elf_scanner_selects_only_relevant_defined_symbols(
    tmp_path: Path,
) -> None:
    binary = tmp_path / "bedrock_server"
    _write_test_elf(binary)

    _, sections = read_elf(binary)
    symbols, symbol_table = scan_symbols(binary, sections)

    assert symbol_table == "dynamic"
    assert symbols == [
        {
            "mangled_name": "_ZN17DynamicProperties18getDynamicPropertyEv",
            "binding": "global",
            "symbol_type": "function",
            "rva": 0x1A20,
            "rva_hex": "0x1a20",
            "size": 0x4F,
        }
    ]


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
