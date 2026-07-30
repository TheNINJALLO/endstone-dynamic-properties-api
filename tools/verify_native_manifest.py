#!/usr/bin/env python3
"""Validate the exact-binary complete-control manifest.

Without --allow-incomplete, every proof gate is mandatory and a blocked source
manifest exits non-zero. The public Python API and activation tool use this same
validator so none of the entry points can drift into a fail-open state.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from endstone_dynamic_properties.native import (  # noqa: E402
    EXPECTED_ARCHIVES,
    REQUIRED_STAGE_PROBES,
    REQUIRED_SYMBOLS,
    native_manifest_errors,
)


def validate(path: Path, root: Path) -> list[str]:
    """Compatibility wrapper used by the activation generator."""
    return list(native_manifest_errors(path, root=root))


def is_declared_blocked_manifest(path: Path) -> bool:
    """Return true only for a readable manifest explicitly marked blocked.

    ``--allow-incomplete`` is intended for inspecting the checked-in blocked
    manifests.  Missing files, malformed JSON, non-object roots, and forged
    ``verified`` manifests must still fail the command.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and data.get("status") == "blocked"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    missing = validate(args.manifest, args.root)
    if missing:
        print(f"{args.manifest}: native complete-control gate CLOSED")
        for item in missing:
            print(f"- {item}")
        if args.allow_incomplete and is_declared_blocked_manifest(args.manifest):
            return 0
        return 1
    print(f"{args.manifest}: native complete-control gate OPEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
