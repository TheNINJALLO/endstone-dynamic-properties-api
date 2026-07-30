#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def python_version(release: str) -> str:
    match = re.fullmatch(r"(\d+\.\d+\.\d+)(?:-(alpha|beta|rc)\.(\d+))?", release)
    if not match:
        raise ValueError(f"unsupported release version: {release}")
    base, phase, serial = match.groups()
    if phase is None:
        return base
    suffix = {"alpha": "a", "beta": "b", "rc": "rc"}[phase]
    return f"{base}{suffix}{serial}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()

    source = json.loads((ROOT / "SOURCE_RELEASE.json").read_text(encoding="utf-8"))
    release = str(source["version"])
    expected_tag = f"v{release}"
    if args.tag != expected_tag:
        raise SystemExit(f"release tag mismatch: expected {expected_tag!r}, got {args.tag!r}")

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    expected_python = python_version(release)
    if not re.search(rf'^version\s*=\s*"{re.escape(expected_python)}"\s*$', pyproject, re.MULTILINE):
        raise SystemExit(f"pyproject version does not match {expected_python}")
    print(f"Verified release tag {expected_tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
