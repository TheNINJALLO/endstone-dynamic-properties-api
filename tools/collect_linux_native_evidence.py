#!/usr/bin/env python3
"""Collect a narrow, identity-bound symbol report from the pinned Linux BDS.

The report is discovery evidence, not proof that a symbol signature or behavior
is correct.  It intentionally excludes the executable, disassembly, full symbol
table, world data, and player records.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
from typing import Any, BinaryIO


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "native/manifests/linux-x64-1.26.33.1.json"
ELF_MAGIC = b"\x7fELF"
ELF_HEADER = struct.Struct("<16sHHIQQQIHHHHHH")
SECTION_HEADER = struct.Struct("<IIQQQQIIQQ")
SYMBOL_ENTRY = struct.Struct("<IBBHQQ")
NOTE_HEADER = struct.Struct("<III")
SHT_SYMTAB = 2
SHT_NOTE = 7
SHT_DYNSYM = 11
SHN_UNDEF = 0
EM_X86_64 = 62

ELF_TYPES = {1: "REL", 2: "EXEC", 3: "DYN", 4: "CORE"}
SYMBOL_BINDINGS = {0: "local", 1: "global", 2: "weak"}
SYMBOL_TYPES = {
    0: "notype",
    1: "object",
    2: "function",
    3: "section",
    4: "file",
    5: "common",
    6: "tls",
    10: "gnu-ifunc",
}

# These identifiers survive Itanium C++ mangling, so the full symbol table does
# not need to leave the operator's server.  Storage-only candidates still need
# caller analysis against the exact executable in the private review workspace.
SYMBOL_TERMS = (
    "dynamicpropert",
    "propertycollection",
    "getoradddynamicproperties",
    "getdynamicpropertiesmanager",
    "writetolevelstorage",
)


class NativeEvidenceError(RuntimeError):
    """Raised when evidence cannot be safely bound to the pinned executable."""


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NativeEvidenceError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("executable"), dict):
        raise NativeEvidenceError(f"manifest {path} has no executable identity")
    if data.get("platform") != "linux-x64":
        raise NativeEvidenceError("the evidence collector requires a linux-x64 manifest")
    return data


def executable_identity(path: Path) -> dict[str, Any]:
    try:
        size = path.stat().st_size
        with path.open("rb") as stream:
            magic = stream.read(4)
    except OSError as exc:
        raise NativeEvidenceError(f"cannot read executable {path}: {exc}") from exc
    if magic != ELF_MAGIC:
        raise NativeEvidenceError(f"{path} is not an ELF executable")
    return {"filename": path.name, "sha256": hash_file(path), "size": size}


def verify_identity(actual: dict[str, Any], manifest: dict[str, Any]) -> None:
    expected = manifest["executable"]
    differences = [
        field
        for field in ("filename", "sha256", "size")
        if actual.get(field) != expected.get(field)
    ]
    if differences:
        details = ", ".join(
            f"{field}: expected {expected.get(field)!r}, got {actual.get(field)!r}"
            for field in differences
        )
        raise NativeEvidenceError(f"executable identity mismatch ({details})")


def find_optional_tool(*names: str) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def is_relevant_symbol(name: str) -> bool:
    folded = name.casefold()
    return any(term in folded for term in SYMBOL_TERMS)


def _read_exact(stream: BinaryIO, offset: int, size: int, label: str) -> bytes:
    stream.seek(offset)
    data = stream.read(size)
    if len(data) != size:
        raise NativeEvidenceError(f"truncated ELF {label}")
    return data


def read_elf(executable: Path) -> tuple[dict[str, int], list[dict[str, int]]]:
    with executable.open("rb") as stream:
        values = ELF_HEADER.unpack(_read_exact(stream, 0, ELF_HEADER.size, "header"))
        ident = values[0]
        if ident[:4] != ELF_MAGIC or ident[4] != 2 or ident[5] != 1:
            raise NativeEvidenceError("bedrock_server must be a little-endian ELF64 file")
        header = {
            "type": values[1],
            "machine": values[2],
            "entry": values[4],
            "section_offset": values[6],
            "section_entry_size": values[11],
            "section_count": values[12],
        }
        if header["machine"] != EM_X86_64:
            raise NativeEvidenceError("bedrock_server must target Linux x86-64")
        if header["section_entry_size"] < SECTION_HEADER.size:
            raise NativeEvidenceError("ELF section headers are missing or unsupported")
        if header["section_count"] == 0:
            raise NativeEvidenceError("extended ELF section counts are unsupported")

        sections: list[dict[str, int]] = []
        for index in range(header["section_count"]):
            offset = header["section_offset"] + index * header["section_entry_size"]
            fields = SECTION_HEADER.unpack(
                _read_exact(stream, offset, SECTION_HEADER.size, "section header")
            )
            sections.append(
                {
                    "type": fields[1],
                    "address": fields[3],
                    "offset": fields[4],
                    "size": fields[5],
                    "link": fields[6],
                    "entry_size": fields[9],
                }
            )
    return header, sections


def _string_at(table: bytes, offset: int) -> str:
    if offset <= 0 or offset >= len(table):
        return ""
    end = table.find(b"\0", offset)
    if end == -1:
        return ""
    return table[offset:end].decode("utf-8", errors="replace")


def scan_symbol_section(
    stream: BinaryIO,
    section: dict[str, int],
    sections: list[dict[str, int]],
) -> list[dict[str, Any]]:
    if section["link"] >= len(sections):
        raise NativeEvidenceError("ELF symbol table has an invalid string-table link")
    entry_size = section["entry_size"]
    if entry_size < SYMBOL_ENTRY.size or section["size"] % entry_size:
        raise NativeEvidenceError("ELF symbol table has an unsupported entry size")
    strings_section = sections[section["link"]]
    strings = _read_exact(
        stream,
        strings_section["offset"],
        strings_section["size"],
        "symbol strings",
    )

    selected: list[dict[str, Any]] = []
    count = section["size"] // entry_size
    for index in range(count):
        offset = section["offset"] + index * entry_size
        name_offset, info, _, section_index, value, size = SYMBOL_ENTRY.unpack(
            _read_exact(stream, offset, SYMBOL_ENTRY.size, "symbol entry")
        )
        if section_index == SHN_UNDEF:
            continue
        name = _string_at(strings, name_offset)
        if not is_relevant_symbol(name):
            continue
        selected.append(
            {
                "mangled_name": name,
                "binding": SYMBOL_BINDINGS.get(info >> 4, f"unknown-{info >> 4}"),
                "symbol_type": SYMBOL_TYPES.get(info & 0xF, f"unknown-{info & 0xF}"),
                "rva": value,
                "rva_hex": f"0x{value:x}",
                "size": size,
            }
        )
    return selected


def scan_symbols(
    executable: Path,
    sections: list[dict[str, int]],
) -> tuple[list[dict[str, Any]], str]:
    dynamic = [section for section in sections if section["type"] == SHT_DYNSYM]
    full = [section for section in sections if section["type"] == SHT_SYMTAB]
    with executable.open("rb") as stream:
        for symbol_table, candidates in (("dynamic", dynamic), ("full", full)):
            selected = [
                symbol
                for section in candidates
                for symbol in scan_symbol_section(stream, section, sections)
            ]
            if selected:
                return selected, symbol_table
    return [], "none"


def demangle_symbols(cxxfilt: str | None, symbols: list[dict[str, Any]]) -> bool:
    if cxxfilt is None:
        return False
    if not symbols:
        return True
    names = [symbol["mangled_name"].split("@", 1)[0] for symbol in symbols]
    result = subprocess.run(
        [cxxfilt],
        input="\n".join(names) + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    demangled = result.stdout.splitlines()
    if result.returncode != 0 or len(demangled) != len(symbols):
        return False
    for symbol, name in zip(symbols, demangled, strict=True):
        symbol["demangled_name"] = name
    return True


def command_output(command: list[str]) -> str:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def build_id(executable: Path, sections: list[dict[str, int]]) -> str:
    with executable.open("rb") as stream:
        for section in sections:
            if section["type"] != SHT_NOTE:
                continue
            notes = _read_exact(stream, section["offset"], section["size"], "notes")
            offset = 0
            while offset + NOTE_HEADER.size <= len(notes):
                name_size, description_size, note_type = NOTE_HEADER.unpack_from(notes, offset)
                offset += NOTE_HEADER.size
                name = notes[offset : offset + name_size].rstrip(b"\0")
                offset += (name_size + 3) & ~3
                description = notes[offset : offset + description_size]
                offset += (description_size + 3) & ~3
                if name == b"GNU" and note_type == 3:
                    return description.hex()
    return ""


def elf_metadata(
    executable: Path,
    header: dict[str, int],
    sections: list[dict[str, int]],
) -> dict[str, str]:
    metadata = {
        "class": "ELF64",
        "data": "little-endian",
        "type": ELF_TYPES.get(header["type"], f"unknown-{header['type']}"),
        "machine": "Advanced Micro Devices X86-64",
        "entry_point": f"0x{header['entry']:x}",
    }
    identifier = build_id(executable, sections)
    if identifier:
        metadata["build_id"] = identifier
    return metadata


def tool_version(tool: str) -> str:
    output = command_output([tool, "--version"])
    return output.splitlines()[0].strip() if output.splitlines() else "unknown"


def collect(executable: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    actual = executable_identity(executable)
    verify_identity(actual, manifest)

    header, sections = read_elf(executable)
    symbols, symbol_table = scan_symbols(executable, sections)
    cxxfilt = find_optional_tool("c++filt", "llvm-cxxfilt")
    demangled = demangle_symbols(cxxfilt, symbols)
    symbols.sort(key=lambda symbol: (symbol["rva"], symbol["mangled_name"]))

    warnings = [
        "Candidate discovery is not signature, ABI, uniqueness, or behavior proof.",
        "Storage-only and caller-derived paths require private exact-binary analysis.",
    ]
    if not symbols:
        warnings.append("No matching symbols were found; the executable may be stripped.")
    if not demangled:
        warnings.append(
            "c++filt was unavailable or failed; candidates retain exact mangled names."
        )

    return {
        "schema": 1,
        "kind": "linux-bds-native-symbol-candidates",
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "manifest": {
            "platform": manifest.get("platform"),
            "bds_package_version": manifest.get("bds_package_version"),
            "runtime_bds": manifest.get("runtime_bds"),
            "endstone_version": manifest.get("endstone_version"),
            "archive_sha256": manifest.get("archive_sha256"),
        },
        "executable": actual,
        "identity_verified": True,
        "host": {
            "machine": platform.machine(),
            "glibc": " ".join(platform.libc_ver()).strip(),
        },
        "elf": elf_metadata(executable, header, sections),
        "tools": {
            "python": sys.version.splitlines()[0],
            "cxxfilt": tool_version(cxxfilt) if cxxfilt else "not installed (optional)",
        },
        "symbol_table": symbol_table,
        "candidate_count": len(symbols),
        "candidates": symbols,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path, help="path to the exact bedrock_server")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    try:
        report = collect(args.executable.resolve(), args.manifest.resolve())
    except NativeEvidenceError as exc:
        parser.exit(1, f"error: {exc}\n")

    rendered = json.dumps(report, indent=2) + "\n"
    if args.json_out:
        args.json_out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
