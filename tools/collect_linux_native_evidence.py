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
import re
import shutil
import subprocess
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "native/manifests/linux-x64-1.26.33.1.json"
ELF_MAGIC = b"\x7fELF"
HEX_VALUE = re.compile(r"^[0-9a-fA-F]+$")
BUILD_ID = re.compile(r"Build ID:\s*([0-9a-fA-F]+)")

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


def find_tool(names: Iterable[str]) -> str:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    raise NativeEvidenceError(f"required tool not found: {' or '.join(names)}")


def parse_nm_line(line: str) -> dict[str, Any] | None:
    # GNU and LLVM nm portable output: name type value [size].
    parts = line.strip().split()
    if len(parts) < 3 or len(parts[1]) != 1 or not HEX_VALUE.fullmatch(parts[2]):
        return None
    size = 0
    if len(parts) >= 4 and HEX_VALUE.fullmatch(parts[3]):
        size = int(parts[3], 16)
    return {
        "mangled_name": parts[0],
        "type": parts[1],
        "rva": int(parts[2], 16),
        "size": size,
    }


def is_relevant_symbol(name: str) -> bool:
    folded = name.casefold()
    return any(term in folded for term in SYMBOL_TERMS)


def scan_symbols(nm: str, executable: Path, *, dynamic: bool) -> list[dict[str, Any]]:
    command = [nm]
    if dynamic:
        command.append("-D")
    command.extend(["--defined-only", "-P", str(executable)])
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise NativeEvidenceError(f"failed to start {Path(nm).name}: {exc}") from exc

    assert process.stdout is not None
    selected: list[dict[str, Any]] = []
    for line in process.stdout:
        parsed = parse_nm_line(line)
        if parsed and is_relevant_symbol(parsed["mangled_name"]):
            selected.append(parsed)
    stderr = process.stderr.read() if process.stderr is not None else ""
    return_code = process.wait()
    if return_code != 0:
        mode = "dynamic" if dynamic else "full"
        message = stderr.strip().splitlines()[-1] if stderr.strip() else "unknown error"
        raise NativeEvidenceError(f"{Path(nm).name} {mode} scan failed: {message}")
    return selected


def demangle_symbols(cxxfilt: str, symbols: list[dict[str, Any]]) -> None:
    if not symbols:
        return
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
        raise NativeEvidenceError(f"{Path(cxxfilt).name} could not demangle candidates")
    for symbol, name in zip(symbols, demangled, strict=True):
        symbol["demangled_name"] = name
        symbol["rva_hex"] = f"0x{symbol['rva']:x}"


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


def read_elf_metadata(readelf: str, executable: Path) -> dict[str, str]:
    header = command_output([readelf, "-h", str(executable)])
    notes = command_output([readelf, "-n", str(executable)])
    fields: dict[str, str] = {}
    for line in header.splitlines():
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        if key in {"Class", "Data", "Type", "Machine", "Entry point address"}:
            fields[key.casefold().replace(" ", "_")] = value
    match = BUILD_ID.search(notes)
    if match:
        fields["build_id"] = match.group(1).lower()
    return fields


def tool_version(tool: str) -> str:
    output = command_output([tool, "--version"])
    return output.splitlines()[0].strip() if output.splitlines() else "unknown"


def collect(executable: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    actual = executable_identity(executable)
    verify_identity(actual, manifest)

    nm = find_tool(("nm", "llvm-nm"))
    cxxfilt = find_tool(("c++filt", "llvm-cxxfilt"))
    readelf = find_tool(("readelf", "llvm-readelf"))

    symbols = scan_symbols(nm, executable, dynamic=True)
    symbol_table = "dynamic"
    if not symbols:
        symbols = scan_symbols(nm, executable, dynamic=False)
        symbol_table = "full"
    demangle_symbols(cxxfilt, symbols)
    symbols.sort(key=lambda symbol: (symbol["rva"], symbol["mangled_name"]))

    warnings = [
        "Candidate discovery is not signature, ABI, uniqueness, or behavior proof.",
        "Storage-only and caller-derived paths require private exact-binary analysis.",
    ]
    if not symbols:
        warnings.append("No matching symbols were found; the executable may be stripped.")

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
        "elf": read_elf_metadata(readelf, executable),
        "tools": {
            "nm": tool_version(nm),
            "cxxfilt": tool_version(cxxfilt),
            "readelf": tool_version(readelf),
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
