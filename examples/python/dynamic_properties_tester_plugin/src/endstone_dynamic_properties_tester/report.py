"""Tamper-evident, atomic reports and interruption checkpoints."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
from typing import Any
from uuid import uuid4


SCHEMA = 1
TESTER_VERSION = "0.1.0a4"
COLLECTION = "endstone-plugin:dynamic-properties-tester:acceptance"
RUN_ID = re.compile(r"^[0-9a-f]{32}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_report(*, mode: str, operator: str, scopes: list[str]) -> dict[str, Any]:
    if mode not in {"acceptance", "persistence", "inventory", "external_watch"}:
        raise ValueError(f"unsupported tester mode {mode!r}")
    return {
        "schema": SCHEMA,
        "tester_version": TESTER_VERSION,
        "run_id": uuid4().hex,
        "mode": mode,
        "state": "running",
        "outcome": "pending",
        "operator": operator,
        "scopes": list(scopes),
        "collection": COLLECTION,
        "started_at_utc": utc_now(),
        "completed_at_utc": "",
        "operations": [],
        "resources": [],
        "checks": [],
        "errors": [],
        "cleanup": {"state": "not_started", "conflicts": []},
    }


def _unsigned(report: dict[str, Any]) -> dict[str, Any]:
    document = deepcopy(report)
    document.pop("integrity", None)
    return document


def report_digest(report: dict[str, Any]) -> str:
    encoded = json.dumps(
        _unsigned(report), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def seal_report(report: dict[str, Any]) -> None:
    report["integrity"] = {"algorithm": "sha256", "digest": report_digest(report)}


def validate_report(report: dict[str, Any]) -> None:
    if report.get("schema") != SCHEMA:
        raise ValueError("tester report schema is incompatible")
    if report.get("tester_version") != TESTER_VERSION:
        raise ValueError("tester report version does not match this wheel")
    if report.get("collection") != COLLECTION:
        raise ValueError("tester report collection is not the fixed tester collection")
    if not RUN_ID.fullmatch(str(report.get("run_id", ""))):
        raise ValueError("tester report run_id is invalid")
    integrity = report.get("integrity")
    if not isinstance(integrity, dict) or integrity.get("algorithm") != "sha256":
        raise ValueError("tester report has no supported integrity seal")
    expected = str(integrity.get("digest", ""))
    actual = report_digest(report)
    if len(expected) != 64 or not hmac.compare_digest(expected, actual):
        raise ValueError("tester report integrity check failed")


def _atomic_write(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    seal_report(report)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, indent=2, sort_keys=True, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def report_path(data_folder: Path, run_id: str) -> Path:
    if not RUN_ID.fullmatch(run_id):
        raise ValueError("tester report run_id is invalid")
    return data_folder / "reports" / f"{run_id}.json"


def latest_report_path(data_folder: Path) -> Path:
    return data_folder / "latest-report.json"


def checkpoint_path(data_folder: Path) -> Path:
    return data_folder / "active-checkpoint.json"


def save_report(data_folder: Path, report: dict[str, Any], *, checkpoint: bool) -> Path:
    path = report_path(data_folder, str(report["run_id"]))
    _atomic_write(path, report)
    _atomic_write(latest_report_path(data_folder), report)
    if checkpoint:
        _atomic_write(checkpoint_path(data_folder), report)
    return path


def load_report(path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError("tester report root must be an object")
    validate_report(report)
    return report


def load_latest(data_folder: Path) -> dict[str, Any]:
    return load_report(latest_report_path(data_folder))


def load_checkpoint(data_folder: Path) -> dict[str, Any]:
    return load_report(checkpoint_path(data_folder))


def remove_checkpoint(data_folder: Path) -> None:
    checkpoint_path(data_folder).unlink(missing_ok=True)


def recover_interrupted(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Mark an active run interrupted and recover unresolved set intents."""

    recovered: list[dict[str, Any]] = []
    known = {
        (json.dumps(item.get("target"), sort_keys=True), item.get("key"))
        for item in report.get("resources", [])
    }
    for operation in report.get("operations", []):
        if (
            operation.get("status") != "intent"
            or operation.get("name") != "set_value"
            or operation.get("collection") != COLLECTION
        ):
            continue
        signature = (
            json.dumps(operation.get("target"), sort_keys=True),
            operation.get("key"),
        )
        if signature in known:
            continue
        resource = {
            "target": deepcopy(operation.get("target")),
            "collection": COLLECTION,
            "key": operation.get("key"),
            "value": deepcopy(operation.get("value")),
            "owned": True,
            "certainty": "unresolved_set_intent",
        }
        report.setdefault("resources", []).append(resource)
        recovered.append(resource)
    report["state"] = "interrupted"
    report["outcome"] = "interrupted"
    report["completed_at_utc"] = utc_now()
    report.setdefault("errors", []).append(
        "The server or tester stopped during an active operation. No mutation was replayed."
    )
    return recovered
