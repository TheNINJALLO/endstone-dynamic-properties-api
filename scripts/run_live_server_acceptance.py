#!/usr/bin/env python3
"""Drive the operator tester through a disposable two-boot Endstone server."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
import hashlib
import hmac
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from typing import Any


class AcceptanceFailure(RuntimeError):
    """Raised when the disposable server does not satisfy the live contract."""


class ServerSession:
    def __init__(self, executable: str, server_dir: Path, log_path: Path) -> None:
        self._condition = threading.Condition()
        self._lines: list[str] = []
        self._log = log_path.open("w", encoding="utf-8", newline="\n")
        self._process = subprocess.Popen(
            [
                executable,
                "--server-folder",
                str(server_dir),
                "--yes",
                "--no-interactive",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self._reader = threading.Thread(target=self._read_output, daemon=True)
        self._reader.start()

    def _read_output(self) -> None:
        assert self._process.stdout is not None
        for line in self._process.stdout:
            print(line, end="", flush=True)
            self._log.write(line)
            self._log.flush()
            with self._condition:
                self._lines.append(line)
                self._condition.notify_all()
        with self._condition:
            self._condition.notify_all()

    def wait_for(self, marker: str, timeout: float = 180.0) -> None:
        deadline = time.monotonic() + timeout
        with self._condition:
            while True:
                if any(marker in line for line in self._lines):
                    return
                return_code = self._process.poll()
                if return_code is not None:
                    tail = "".join(self._lines[-40:])
                    raise AcceptanceFailure(
                        f"server exited with {return_code} before {marker!r}\n{tail}"
                    )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    tail = "".join(self._lines[-40:])
                    raise AcceptanceFailure(
                        f"timed out waiting for {marker!r}\n{tail}"
                    )
                self._condition.wait(min(remaining, 1.0))

    def command(self, command: str, marker: str, timeout: float = 90.0) -> None:
        if self._process.stdin is None or self._process.poll() is not None:
            raise AcceptanceFailure(f"cannot send command to stopped server: {command}")
        self._process.stdin.write(command + "\n")
        self._process.stdin.flush()
        self.wait_for(marker, timeout)

    def stop(self) -> None:
        try:
            if self._process.poll() is None and self._process.stdin is not None:
                self._process.stdin.write("stop\n")
                self._process.stdin.flush()
                self._process.wait(timeout=90)
        except subprocess.TimeoutExpired:
            self._process.terminate()
            try:
                self._process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=15)
            raise AcceptanceFailure("server did not stop cleanly")
        finally:
            if self._process.stdin is not None:
                self._process.stdin.close()
            self._reader.join(timeout=5)
            self._log.close()
        if self._process.returncode != 0:
            raise AcceptanceFailure(
                f"server returned non-zero exit code {self._process.returncode}"
            )

    def abort(self) -> None:
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=15)
        if self._process.stdin is not None:
            self._process.stdin.close()
        self._reader.join(timeout=5)
        self._log.close()


def _unsigned(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key != "integrity"}


def _report_digest(report: dict[str, Any]) -> str:
    encoded = json.dumps(
        _unsigned(report), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_reports(server_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    loaded: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(server_dir.glob("plugins/**/reports/*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise AcceptanceFailure(f"tester report is not an object: {path}")
        integrity = report.get("integrity")
        expected = integrity.get("digest") if isinstance(integrity, dict) else None
        if not isinstance(expected, str) or not hmac.compare_digest(
            expected, _report_digest(report)
        ):
            raise AcceptanceFailure(f"tester report integrity failed: {path}")
        loaded.append((path, report))
    if not loaded:
        raise AcceptanceFailure("the live tester produced no reports")
    return loaded


def _require_report(
    reports: Iterable[tuple[Path, dict[str, Any]]], mode: str, outcome: str
) -> dict[str, Any]:
    for unused_path, report in reports:
        if report.get("mode") == mode and report.get("outcome") == outcome:
            return report
    raise AcceptanceFailure(f"no {mode!r} report has outcome {outcome!r}")


def validate_reports(server_dir: Path) -> dict[str, Any]:
    reports = _load_reports(server_dir)
    failures = [
        str(path)
        for path, report in reports
        if report.get("state") == "failed" or report.get("outcome") == "failed"
    ]
    if failures:
        raise AcceptanceFailure("failed tester report(s): " + ", ".join(failures))

    inventory = _require_report(reports, "inventory", "inventory_captured")
    acceptance = _require_report(reports, "acceptance", "passed")
    hook_probe = _require_report(
        reports, "external_watch", "external_hook_probe_passed"
    )
    persistence = _require_report(reports, "persistence", "persistence_passed")
    checks = acceptance.get("checks")
    if not isinstance(checks, list) or not checks:
        raise AcceptanceFailure("acceptance report contains no checks")
    failed_checks = [
        str(check.get("name", "unnamed"))
        for check in checks
        if not isinstance(check, dict) or check.get("passed") is not True
    ]
    if failed_checks:
        raise AcceptanceFailure(
            "acceptance report contains failed checks: " + ", ".join(failed_checks)
        )

    service_status = acceptance.get("service_status")
    if not isinstance(service_status, dict):
        raise AcceptanceFailure("acceptance report has no service status")
    if service_status.get("available") is not True:
        raise AcceptanceFailure("native service was unavailable during acceptance")
    if service_status.get("operational_live") is not True:
        raise AcceptanceFailure("native service did not report operational live mode")
    capabilities = service_status.get("capabilities")
    required_capabilities = {
        "world",
        "read",
        "write",
        "remove",
        "clear",
        "list_ids",
        "list_collections",
        "byte_count",
        "persistence_flush",
        "external_change_observation",
        "external_change_cancellation",
        "exact_build_match",
        "exact_binary_hash_match",
        "symbols_validated",
    }
    if not isinstance(capabilities, dict):
        raise AcceptanceFailure("native service returned no capability map")
    missing = sorted(
        name for name in required_capabilities if capabilities.get(name) is not True
    )
    if missing:
        raise AcceptanceFailure("missing live capabilities: " + ", ".join(missing))

    return {
        "schema": 1,
        "result": "passed",
        "report_count": len(reports),
        "acceptance_checks": len(checks),
        "adapter": service_status.get("adapter"),
        "inventory_run_id": inventory.get("run_id"),
        "acceptance_run_id": acceptance.get("run_id"),
        "hook_probe_run_id": hook_probe.get("run_id"),
        "persistence_run_id": persistence.get("run_id"),
    }


def _install_plugins(stage_dir: Path, server_dir: Path) -> None:
    plugin_dir = server_dir / "plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    native = stage_dir / "plugins" / "endstone_dynamic_properties_api.so"
    wheels = sorted((stage_dir / "plugins").glob("*.whl"))
    if not native.is_file() or len(wheels) != 1:
        raise AcceptanceFailure("stage must contain one native plugin and one tester wheel")
    shutil.copy2(native, plugin_dir / native.name)
    shutil.copy2(wheels[0], plugin_dir / wheels[0].name)


def _run(args: argparse.Namespace) -> None:
    stage_dir = args.stage_dir.resolve()
    server_dir = args.server_dir.resolve()
    evidence_dir = args.evidence_dir.resolve()
    if server_dir.exists() and any(server_dir.iterdir()):
        raise AcceptanceFailure(f"refusing to reuse non-empty server directory: {server_dir}")
    server_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    _install_plugins(stage_dir, server_dir)

    first = ServerSession(args.endstone, server_dir, evidence_dir / "server-first.log")
    try:
        first.wait_for("registered experimental live world/player/entity service", 300)
        first.wait_for("Dynamic Properties tester enabled with its exact live bridge", 90)
        first.command("dptest status", "Native Dynamic Properties status:")
        first.command(
            "dptest inventory world", "Dynamic Properties inventory captured"
        )
        first.command(
            "dptest run world confirm", "Dynamic Properties live world suite PASSED", 180
        )
        first.command(
            "dptest watch probe", "Dynamic Properties external hook probe PASSED", 120
        )
        first.command(
            "dptest persistence prepare", "Restart the server cleanly", 120
        )
        first.stop()
    except BaseException:
        first.abort()
        raise

    second = ServerSession(args.endstone, server_dir, evidence_dir / "server-second.log")
    try:
        second.wait_for("registered experimental live world/player/entity service", 180)
        second.wait_for("Dynamic Properties tester enabled with its exact live bridge", 90)
        second.command(
            "dptest persistence verify",
            "Dynamic Properties restart persistence PASSED",
            180,
        )
        second.stop()
    except BaseException:
        second.abort()
        raise

    summary = validate_reports(server_dir)
    (evidence_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-dir", type=Path, required=True)
    parser.add_argument("--server-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--endstone", default="endstone")
    return parser


def main() -> int:
    try:
        _run(_parser().parse_args())
    except (AcceptanceFailure, OSError, ValueError) as error:
        print(f"live acceptance failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
