from __future__ import annotations

from pathlib import Path
import struct
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from analyze_linux_dynamic_property_xrefs import (  # noqa: E402
    NativeEvidenceError,
    find_anchor_relocations,
    find_rip_relative_references,
    parse_eh_frame_header,
)


def test_parse_eh_frame_header_search_table() -> None:
    section_rva = 0x2000
    data = (
        bytes([1, 0x1B, 0x03, 0x3B])
        + struct.pack("<i", 0x300)
        + struct.pack("<I", 2)
        + struct.pack("<ii", 0x1000, 0x4000)
        + struct.pack("<ii", 0x1100, 0x4100)
    )

    assert parse_eh_frame_header(data, section_rva) == [0x3000, 0x3100]


def test_reject_unsupported_unwind_encoding() -> None:
    with pytest.raises(NativeEvidenceError, match="unsupported"):
        parse_eh_frame_header(bytes(12), 0x2000)


def test_find_rip_relative_string_reference() -> None:
    code_rva = 0x1000
    target = 0x2400
    displacement = target - (code_rva + 7)
    code = b"\x48\x8d\x3d" + struct.pack("<i", displacement) + b"\xc3"

    assert find_rip_relative_references(code, code_rva, {target}) == [
        {
            "instruction_rva": 0x1000,
            "opcode_rva": 0x1001,
            "target_rva": target,
            "kind": "lea",
        }
    ]


def test_ignore_unrequested_rip_relative_target() -> None:
    code = b"\x48\x8d\x3d" + struct.pack("<i", 0x100) + b"\xc3"

    assert not find_rip_relative_references(code, 0x1000, {0x9999})


def test_find_relative_relocation_to_anchor(tmp_path: Path) -> None:
    binary = tmp_path / "bedrock_server"
    binary.write_bytes(
        struct.pack("<QQq", 0x5008, 8, 0x2400)
        + struct.pack("<QQq", 0x5010, 8, 0x9999)
    )
    sections = [
        {
            "name": ".rela.dyn",
            "type": 4,
            "address": 0x3000,
            "offset": 0,
            "size": 48,
            "entry_size": 24,
        },
        {
            "name": ".data.rel.ro",
            "type": 1,
            "address": 0x5000,
            "offset": 48,
            "size": 24,
            "entry_size": 0,
        },
    ]

    assert find_anchor_relocations(binary, sections, {0x2400}) == [
        {
            "rva": 0x5008,
            "rva_hex": "0x5008",
            "target_rva": 0x2400,
            "target_rva_hex": "0x2400",
            "relocation_type": 8,
            "section": ".data.rel.ro",
        }
    ]
