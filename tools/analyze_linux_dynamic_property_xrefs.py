#!/usr/bin/env python3
"""Resolve DynamicProperties string xrefs in the exact stripped Linux BDS.

This is private review tooling.  Its output contains focused instruction bytes
and must not be committed.  The scanner verifies the executable identity and
uses `.eh_frame_hdr` for function boundaries; it never executes BDS.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import deque
import hashlib
import json
from pathlib import Path
import struct
from typing import Any

from collect_linux_native_evidence import (
    NativeEvidenceError,
    executable_identity,
    load_manifest,
    read_elf,
    verify_identity,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "native/manifests/linux-x64-1.26.33.1.json"
RIP_RELATIVE_OPCODES = {
    0x01: "add-store",
    0x03: "add-load",
    0x29: "sub-store",
    0x2B: "sub-load",
    0x39: "cmp-store",
    0x3B: "cmp-load",
    0x8B: "mov-load",
    0x8D: "lea",
    0x89: "mov-store",
    0xFF: "indirect",
}
SHT_RELA = 4
R_X86_64_64 = 1
R_X86_64_RELATIVE = 8
RELA_ENTRY = struct.Struct("<QQq")


def parse_eh_frame_header(
    data: bytes,
    section_rva: int,
) -> list[int]:
    if len(data) < 12:
        raise NativeEvidenceError("truncated .eh_frame_hdr")
    version, pointer_encoding, count_encoding, table_encoding = data[:4]
    if (version, pointer_encoding, count_encoding, table_encoding) != (
        1,
        0x1B,
        0x03,
        0x3B,
    ):
        raise NativeEvidenceError(
            "unsupported .eh_frame_hdr encoding "
            f"{version:02x}/{pointer_encoding:02x}/{count_encoding:02x}/{table_encoding:02x}"
        )
    count = struct.unpack_from("<I", data, 8)[0]
    expected_size = 12 + count * 8
    if len(data) < expected_size:
        raise NativeEvidenceError("truncated .eh_frame_hdr search table")
    starts = [
        section_rva + struct.unpack_from("<i", data, 12 + index * 8)[0]
        for index in range(count)
    ]
    if starts != sorted(starts) or len(starts) != len(set(starts)):
        raise NativeEvidenceError(".eh_frame_hdr function table is not uniquely sorted")
    return starts


def find_rip_relative_references(
    code: bytes,
    code_rva: int,
    targets: set[int],
) -> list[dict[str, int | str]]:
    references: dict[tuple[int, int], dict[str, int | str]] = {}
    for opcode, kind in RIP_RELATIVE_OPCODES.items():
        needle = bytes([opcode])
        search_from = 0
        while True:
            position = code.find(needle, search_from)
            if position < 0:
                break
            search_from = position + 1
            if position + 6 > len(code):
                continue
            modrm = code[position + 1]
            if modrm & 0xC7 != 0x05:
                continue
            displacement = struct.unpack_from("<i", code, position + 2)[0]
            target = code_rva + position + 6 + displacement
            if target not in targets:
                continue
            instruction_offset = position
            if position and 0x40 <= code[position - 1] <= 0x4F:
                instruction_offset -= 1
            instruction_rva = code_rva + instruction_offset
            references[(instruction_rva, target)] = {
                "instruction_rva": instruction_rva,
                "opcode_rva": code_rva + position,
                "target_rva": target,
                "kind": kind,
            }
    return [references[key] for key in sorted(references)]


def find_anchor_relocations(
    executable: Path,
    sections: list[dict[str, Any]],
    targets: set[int],
) -> list[dict[str, Any]]:
    """Find ELF data pointers whose relocation addend names an anchor."""

    references: dict[tuple[int, int], dict[str, Any]] = {}
    for section in sections:
        if section["type"] != SHT_RELA:
            continue
        entry_size = section["entry_size"]
        if entry_size < RELA_ENTRY.size or section["size"] % entry_size:
            raise NativeEvidenceError(
                f"unsupported RELA entry size in {section.get('name', '')}"
            )
        data = _read_section(executable, section)
        for offset in range(0, len(data), entry_size):
            relocation_rva, info, addend = RELA_ENTRY.unpack_from(data, offset)
            relocation_type = info & 0xFFFFFFFF
            if relocation_type not in (R_X86_64_64, R_X86_64_RELATIVE):
                continue
            if addend not in targets:
                continue
            owner = next(
                (
                    candidate
                    for candidate in sections
                    if candidate["address"]
                    <= relocation_rva
                    < candidate["address"] + candidate["size"]
                ),
                None,
            )
            references[(relocation_rva, addend)] = {
                "rva": relocation_rva,
                "rva_hex": f"0x{relocation_rva:x}",
                "target_rva": addend,
                "target_rva_hex": f"0x{addend:x}",
                "relocation_type": relocation_type,
                "section": "" if owner is None else str(owner.get("name", "")),
            }
    return [references[key] for key in sorted(references)]


def _read_section(executable: Path, section: dict[str, Any]) -> bytes:
    with executable.open("rb") as stream:
        stream.seek(section["offset"])
        data = stream.read(section["size"])
    if len(data) != section["size"]:
        raise NativeEvidenceError(f"truncated ELF section {section.get('name', '')}")
    return data


def _section(sections: list[dict[str, Any]], name: str) -> dict[str, Any]:
    matches = [section for section in sections if section.get("name") == name]
    if len(matches) != 1:
        raise NativeEvidenceError(f"expected exactly one {name} section")
    return matches[0]


def _load_anchors(evidence_path: Path, identity: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NativeEvidenceError(f"cannot read evidence {evidence_path}: {exc}") from exc
    if evidence.get("executable") != identity or not evidence.get("identity_verified"):
        raise NativeEvidenceError("string evidence is not bound to this executable")
    anchors = evidence.get("string_anchors")
    if not isinstance(anchors, list) or not anchors:
        raise NativeEvidenceError("evidence contains no string anchors")
    return anchors


def _function_range(rva: int, starts: list[int], text_end: int) -> tuple[int, int]:
    index = bisect_right(starts, rva) - 1
    if index < 0:
        raise NativeEvidenceError(f"no unwind function contains RVA 0x{rva:x}")
    start = starts[index]
    end = starts[index + 1] if index + 1 < len(starts) else text_end
    if not start <= rva < end:
        raise NativeEvidenceError(f"invalid unwind range for RVA 0x{rva:x}")
    return start, end


def _capstone_context(
    code: bytes,
    code_rva: int,
    function_start: int,
    function_end: int,
    instruction_rva: int,
    expected_target_rva: int,
) -> tuple[bool, list[dict[str, Any]]]:
    try:
        from capstone import CS_ARCH_X86, CS_MODE_64, Cs
        from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
    except ImportError:
        return False, []

    start_offset = function_start - code_rva
    stop_offset = min(function_end, instruction_rva + 96) - code_rva
    if start_offset < 0 or stop_offset > len(code):
        return False, []
    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    decoder.detail = True
    previous: deque[Any] = deque(maxlen=8)
    following = 12
    selected: list[Any] = []
    found = False
    valid_reference = False
    for instruction in decoder.disasm(
        code[start_offset:stop_offset],
        function_start,
    ):
        if instruction.address == instruction_rva:
            found = True
            valid_reference = expected_target_rva in {
                instruction.address + instruction.size + operand.mem.disp
                for operand in instruction.operands
                if operand.type == X86_OP_MEM and operand.mem.base == X86_REG_RIP
            }
            selected.extend(previous)
            selected.append(instruction)
            continue
        if not found:
            previous.append(instruction)
            continue
        if following == 0:
            break
        selected.append(instruction)
        following -= 1
    context = []
    for instruction in selected:
        rip_targets = [
            instruction.address + instruction.size + operand.mem.disp
            for operand in instruction.operands
            if operand.type == X86_OP_MEM and operand.mem.base == X86_REG_RIP
        ]
        immediate_targets = [
            operand.imm
            for operand in instruction.operands
            if operand.type == X86_OP_IMM
        ]
        item = {
            "rva": instruction.address,
            "rva_hex": f"0x{instruction.address:x}",
            "bytes_hex": instruction.bytes.hex(),
            "mnemonic": instruction.mnemonic,
            "operands": instruction.op_str,
        }
        if rip_targets:
            item["rip_targets"] = rip_targets
            item["rip_target_hex"] = [f"0x{target:x}" for target in rip_targets]
        if immediate_targets:
            item["immediate_targets"] = immediate_targets
            item["immediate_target_hex"] = [
                f"0x{target:x}" for target in immediate_targets
            ]
        context.append(item)
    return valid_reference, context


def analyze(
    executable: Path,
    manifest_path: Path,
    evidence_path: Path,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    identity = executable_identity(executable)
    verify_identity(identity, manifest)
    anchors = _load_anchors(evidence_path, identity)
    _, sections = read_elf(executable)
    text_section = _section(sections, ".text")
    unwind_section = _section(sections, ".eh_frame_hdr")
    code = _read_section(executable, text_section)
    unwind = _read_section(executable, unwind_section)
    starts = parse_eh_frame_header(unwind, unwind_section["address"])

    anchor_by_rva = {anchor["rva"]: anchor for anchor in anchors}
    data_references = find_anchor_relocations(
        executable,
        sections,
        set(anchor_by_rva),
    )
    data_reference_by_rva = {
        reference["rva"]: reference for reference in data_references
    }
    raw_references = find_rip_relative_references(
        code,
        text_section["address"],
        set(anchor_by_rva) | set(data_reference_by_rva),
    )
    references: list[dict[str, Any]] = []
    functions: dict[int, dict[str, Any]] = {}
    text_end = text_section["address"] + text_section["size"]
    for reference in raw_references:
        function_start, function_end = _function_range(
            int(reference["instruction_rva"]), starts, text_end
        )
        valid, context = _capstone_context(
            code,
            text_section["address"],
            function_start,
            function_end,
            int(reference["instruction_rva"]),
            int(reference["target_rva"]),
        )
        if context and not valid:
            continue
        function_offset = function_start - text_section["address"]
        fingerprint = code[function_offset : function_offset + 32]
        function = functions.setdefault(
            function_start,
            {
                "rva": function_start,
                "rva_hex": f"0x{function_start:x}",
                "size": function_end - function_start,
                "fingerprint_hex": fingerprint.hex(),
                "fingerprint_sha256": hashlib.sha256(fingerprint).hexdigest(),
                "anchor_texts": [],
            },
        )
        direct_target = int(reference["target_rva"])
        data_reference = data_reference_by_rva.get(direct_target)
        anchor_target = (
            direct_target
            if data_reference is None
            else int(data_reference["target_rva"])
        )
        anchor = anchor_by_rva[anchor_target]
        if anchor["text"] not in function["anchor_texts"]:
            function["anchor_texts"].append(anchor["text"])
        references.append(
            {
                **reference,
                "instruction_rva_hex": f"0x{int(reference['instruction_rva']):x}",
                "target_rva_hex": f"0x{int(reference['target_rva']):x}",
                "target_kind": "string" if data_reference is None else "data-pointer",
                "anchor_text": anchor["text"],
                "function_rva": function_start,
                "function_rva_hex": f"0x{function_start:x}",
                "capstone_validated": valid,
                "context": context,
            }
        )

    for function in functions.values():
        function["anchor_texts"].sort()
    return {
        "schema": 1,
        "kind": "linux-bds-dynamic-property-code-xrefs",
        "executable": identity,
        "identity_verified": True,
        "text": {
            "rva": text_section["address"],
            "size": text_section["size"],
        },
        "unwind_function_count": len(starts),
        "anchor_count": len(anchors),
        "data_reference_count": len(data_references),
        "data_references": [
            {
                **reference,
                "anchor_text": anchor_by_rva[int(reference["target_rva"])]["text"],
            }
            for reference in data_references
        ],
        "reference_count": len(references),
        "function_count": len(functions),
        "functions": [functions[rva] for rva in sorted(functions)],
        "references": references,
        "warnings": [
            "Focused xrefs and instruction bytes are private review evidence.",
            "A code xref identifies a caller, not a verified public ABI entry point.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--json-out", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = analyze(
            args.executable.resolve(),
            args.manifest.resolve(),
            args.evidence.resolve(),
        )
    except NativeEvidenceError as exc:
        parser.exit(1, f"error: {exc}\n")
    args.json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"verified {report['unwind_function_count']} unwind functions; "
        f"resolved {report['reference_count']} xrefs in {report['function_count']} functions"
    )
    if not any(reference["capstone_validated"] for reference in report["references"]):
        print("warning: install capstone to validate and render instruction context")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
