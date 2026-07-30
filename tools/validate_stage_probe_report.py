#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from endstone_dynamic_properties.native import REQUIRED_STAGE_PROBES  # noqa: E402


HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
SUPPORTED_PLATFORMS = {"linux-x64", "windows-x64"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp(value: object, field: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be an ISO-8601 timestamp")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{field} must be an ISO-8601 timestamp")
        return None
    if parsed.tzinfo is None:
        errors.append(f"{field} must include a timezone")
        return None
    return parsed


def validate(data: object) -> list[str]:
    if not isinstance(data, dict):
        return ["report root must be an object"]

    errors: list[str] = []
    if data.get("schema") != 1:
        errors.append("schema must be 1")
    if data.get("platform") not in SUPPORTED_PLATFORMS:
        errors.append("platform must be linux-x64 or windows-x64")
    if data.get("bds_package_version") != "1.26.33.1":
        errors.append("wrong BDS package version")
    if data.get("runtime_bds") != "26.33":
        errors.append("wrong BDS runtime")
    if data.get("endstone_version") != "0.11.6":
        errors.append("wrong Endstone version")
    for field in ("executable_sha256", "bridge_sha256"):
        if not HEX64.fullmatch(str(data.get(field, ""))):
            errors.append(f"{field} must be a 64-digit hexadecimal SHA-256")

    started = _timestamp(data.get("started_at"), "started_at", errors)
    completed = _timestamp(data.get("completed_at"), "completed_at", errors)
    if started is not None and completed is not None and completed < started:
        errors.append("completed_at precedes started_at")
    if data.get("passed") is not True:
        errors.append("report is not marked passed")

    results: dict[str, Any]
    if isinstance(data.get("results"), dict):
        results = data["results"]
    else:
        results = {}
        errors.append("results must be an object")
    required = set(REQUIRED_STAGE_PROBES)
    if set(results) != required:
        missing = sorted(required - set(results))
        unexpected = sorted(set(results) - required)
        if missing:
            errors.append("missing probes: " + ", ".join(missing))
        if unexpected:
            errors.append("unexpected probes: " + ", ".join(unexpected))
    for name in REQUIRED_STAGE_PROBES:
        result = results.get(name)
        if not isinstance(result, dict):
            errors.append(f"probe {name} must be an object")
            continue
        if result.get("passed") is not True:
            errors.append(f"probe {name} did not pass")
        if not isinstance(result.get("notes"), str) or not result["notes"].strip():
            errors.append(f"probe {name} has no notes")
        if not HEX64.fullmatch(str(result.get("evidence_sha256", ""))):
            errors.append(f"probe {name} has an invalid evidence hash")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        data = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(exc, file=sys.stderr)
        return 1
    errors = validate(data)
    if errors:
        print("Stage probe validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Stage probe valid: {args.report} ({sha256(args.report)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
