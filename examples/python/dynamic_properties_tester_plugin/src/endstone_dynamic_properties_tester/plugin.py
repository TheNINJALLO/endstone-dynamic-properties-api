"""Operator-only live acceptance commands for Dynamic Properties API."""

from __future__ import annotations

from copy import deepcopy
import json
import math
import os
from pathlib import Path
import sys
from threading import Lock
from typing import Any, Callable
from uuid import uuid4

from endstone.command import Command, CommandSender
from endstone.plugin import Plugin

from ._bridge_loader import import_live_bridge
from .report import (
    COLLECTION,
    checkpoint_path,
    load_checkpoint,
    load_latest,
    latest_report_path,
    new_report,
    recover_interrupted,
    remove_checkpoint,
    report_path,
    save_report,
    TESTER_VERSION,
    utc_now,
)
from .targets import (
    ensure_target_template,
    load_configured_targets,
    targets_path,
    validate_target,
)


class TestFailure(RuntimeError):
    """A live assertion failed; the report remains available for cleanup."""


_PROCESS_INCARNATION_STATE = (
    "_endstone_dynamic_properties_tester_process_incarnation_state"
)


def _current_process_incarnation() -> str:
    """Return a reload-stable token unique to this interpreter process."""

    process_id = os.getpid()
    state = getattr(sys, _PROCESS_INCARNATION_STATE, None)
    if (
        isinstance(state, tuple)
        and len(state) == 2
        and state[0] == process_id
        and isinstance(state[1], str)
        and len(state[1]) == 32
    ):
        return state[1]
    token = uuid4().hex
    setattr(sys, _PROCESS_INCARNATION_STATE, (process_id, token))
    return token


class DynamicPropertiesTesterPlugin(Plugin):
    """Fail-closed live test harness; this class never constructs a fallback API."""

    api_version = "0.11"
    version = TESTER_VERSION
    description = "Live Dynamic Properties API acceptance and persistence tests"
    depend = ["dynamic_properties_api"]

    commands = {
        "dptest": {
            "description": "Run live Dynamic Properties API acceptance tests",
            "usages": [
                "/dptest (help)<action: DpTestHelpAction>",
                "/dptest (status)<action: DpTestStatusAction>",
                (
                    "/dptest (run)<action: DpTestRunAction> "
                    "(world|player|configured|all)<scope: DpTestRunScope> "
                    "(confirm)<confirmation: DpTestRunConfirm>"
                ),
                (
                    "/dptest (persistence)<action: DpTestPersistenceAction> "
                    "(prepare|verify)<phase: DpTestPersistencePhase>"
                ),
                "/dptest (report)<action: DpTestReportAction>",
                (
                    "/dptest (cleanup)<action: DpTestCleanupAction> "
                    "(confirm)<confirmation: DpTestCleanupConfirm>"
                ),
                (
                    "/dptest (inventory)<action: DpTestInventoryAction> "
                    "(world|player|configured|all)<scope: DpTestInventoryScope>"
                ),
                (
                    "/dptest (watch)<action: DpTestWatchAction> "
                    "(start|drain|status|stop)<phase: DpTestWatchPhase>"
                ),
            ],
            "permissions": ["dptest.admin"],
        }
    }
    permissions = {
        "dptest.admin": {
            "description": "Allows live Dynamic Properties API tests",
            "default": "op",
        }
    }

    def on_enable(self) -> None:
        self._mutation_lock = Lock()
        configured_targets = ensure_target_template(Path(self.data_folder))
        self.live_bridge: Any | None = None
        self.bridge_error = "bridge was not initialized"
        try:
            bridge = import_live_bridge(self.version)
            if bridge.available(self.server):
                self.live_bridge = bridge
                self.bridge_error = ""
            else:
                self.bridge_error = "endstone:dynamic-properties:v1 is not registered"
        except Exception as error:
            self.bridge_error = str(error)

        if self.live_bridge is None:
            self.logger.error(
                f"Dynamic Properties tester live service unavailable: {self.bridge_error}"
            )
        else:
            self.logger.info(
                "Dynamic Properties tester enabled with its exact live bridge. "
                "Mutating tests still require an operator and explicit confirmation."
            )
        self.logger.info(f"Configured target file: {configured_targets}")
        self._recover_checkpoint()

    def on_disable(self) -> None:
        bridge = getattr(self, "live_bridge", None)
        if bridge is None:
            return
        try:
            bridge.stop_external_watch(self.server)
        except Exception as error:
            self.logger.warning(
                f"Could not stop Dynamic Properties external watch: {error}"
            )

    def _recover_checkpoint(self) -> None:
        data_folder = Path(self.data_folder)
        path = checkpoint_path(data_folder)
        if not path.is_file():
            return
        try:
            report = load_checkpoint(data_folder)
            if report.get("state") in {"running", "cleanup_running"}:
                recovered = recover_interrupted(report)
                save_report(data_folder, report, checkpoint=True)
                self.logger.warning(
                    "An interrupted Dynamic Properties test was recovered without "
                    f"replaying a mutation ({len(recovered)} unresolved set intent(s)). "
                    "Review /dptest report, then use /dptest cleanup confirm."
                )
        except Exception as error:
            self.logger.error(f"Could not recover tester checkpoint: {error}")

    @staticmethod
    def _sender_name(sender: CommandSender) -> str:
        return str(getattr(sender, "name", "console") or "console")

    @staticmethod
    def _process_incarnation() -> str:
        return _current_process_incarnation()

    def _bridge(self, sender: CommandSender) -> Any | None:
        if self.live_bridge is not None:
            return self.live_bridge
        try:
            bridge = import_live_bridge(self.version)
            if bridge.available(self.server):
                self.live_bridge = bridge
                self.bridge_error = ""
                return bridge
            self.bridge_error = "endstone:dynamic-properties:v1 is not registered"
        except Exception as error:
            self.bridge_error = str(error)
        sender.send_message(
            "Native Dynamic Properties service unavailable; no test was run: "
            f"{self.bridge_error}"
        )
        return None

    def _may_start_new_run(self, sender: CommandSender) -> bool:
        """Never overwrite the only checkpoint that proves resource ownership."""

        data_folder = Path(self.data_folder)
        path = checkpoint_path(data_folder)
        if not path.is_file():
            return True
        try:
            active = load_checkpoint(data_folder)
        except Exception as error:
            sender.send_message(
                "A tester checkpoint exists but failed validation. It was preserved; "
                f"review {path} before starting another run: {error}"
            )
            return False
        owned = [
            item for item in active.get("resources", []) if item.get("owned") is True
        ]
        if not owned and active.get("state") in {
            "completed",
            "cleanup_completed",
            "failed",
        }:
            remove_checkpoint(data_folder)
            return True
        sender.send_message(
            f"Run {active.get('run_id')} still has an active checkpoint "
            f"(state={active.get('state')}, owned_values={len(owned)})."
        )
        if active.get("state") == "awaiting_restart":
            sender.send_message(
                "Run /dptest persistence verify after restart, or review the report "
                "and use /dptest cleanup confirm."
            )
        else:
            sender.send_message(
                "Review /dptest report, then use /dptest cleanup confirm."
            )
        return False

    def _world_target(self) -> dict[str, Any]:
        level = getattr(self.server, "level", None)
        world_id = str(getattr(level, "name", "default") or "default")
        return {"kind": "world", "world_id": world_id}

    @staticmethod
    def _player_target(sender: CommandSender) -> dict[str, Any]:
        xuid = str(getattr(sender, "xuid", "") or "").strip()
        if not xuid:
            raise TestFailure(
                "player tests require an authenticated online player sender with an XUID"
            )
        return {"kind": "online_player", "xuid": xuid}

    def _targets(
        self, scope: str, sender: CommandSender
    ) -> list[tuple[str, dict[str, Any]]]:
        targets: list[tuple[str, dict[str, Any]]] = []
        if scope in {"world", "all"}:
            targets.append(("world", self._world_target()))
        if scope in {"player", "all"}:
            targets.append(("player", self._player_target(sender)))
        if scope in {"configured", "all"}:
            try:
                configured = load_configured_targets(Path(self.data_folder))
            except ValueError as error:
                raise TestFailure(str(error)) from error
            if scope == "configured" and not configured:
                raise TestFailure(
                    f"no targets are enabled in {targets_path(Path(self.data_folder))}"
                )
            targets.extend(
                (f"configured:{label}", target) for label, target in configured
            )

        identities: set[str] = set()
        for label, target in targets:
            identity = json.dumps(target, sort_keys=True, separators=(",", ":"))
            if identity in identities:
                raise TestFailure(
                    f"target {label!r} duplicates another selected target; disable the duplicate"
                )
            identities.add(identity)
        return targets

    @staticmethod
    def _json_safe(value: Any) -> Any:
        return json.loads(json.dumps(value, default=str, ensure_ascii=False))

    @staticmethod
    def _send_json(sender: CommandSender, label: str, value: Any) -> None:
        rendered = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
        if len(rendered) > 900:
            rendered = rendered[:897] + "..."
        sender.send_message(f"{label}: {rendered}")

    @staticmethod
    def _snapshot(response: dict[str, Any]) -> dict[str, Any] | None:
        snapshot = response.get("snapshot")
        return dict(snapshot) if isinstance(snapshot, dict) else None

    @staticmethod
    def _properties(snapshot: dict[str, Any] | None) -> dict[str, Any]:
        if snapshot is None:
            return {}
        properties = snapshot.get("properties", {})
        if not isinstance(properties, dict):
            raise TestFailure("live capture returned a non-object properties field")
        return dict(properties)

    @staticmethod
    def _revision(snapshot: dict[str, Any] | None, response: dict[str, Any]) -> int:
        value = (snapshot or {}).get("revision", response.get("revision", 0))
        try:
            revision = int(value or 0)
        except (TypeError, ValueError) as error:
            raise TestFailure("live response returned an invalid revision") from error
        if revision < 0:
            raise TestFailure("live response returned a negative revision")
        return revision

    @staticmethod
    def _values_equal(actual: Any, expected: Any) -> bool:
        if isinstance(expected, bool):
            return isinstance(actual, bool) and actual is expected
        if isinstance(expected, (int, float)) and not isinstance(expected, bool):
            return (
                isinstance(actual, (int, float))
                and not isinstance(actual, bool)
                and math.isfinite(float(actual))
                and float(actual) == float(expected)
            )
        if isinstance(expected, dict) and set(expected) == {"x", "y", "z"}:
            if not isinstance(actual, dict) or not {"x", "y", "z"}.issubset(actual):
                return False
            return all(
                DynamicPropertiesTesterPlugin._values_equal(
                    actual[name], expected[name]
                )
                for name in ("x", "y", "z")
            )
        return actual == expected

    def _save(self, report: dict[str, Any], *, checkpoint: bool = True) -> Path:
        return save_report(Path(self.data_folder), report, checkpoint=checkpoint)

    def _journal_call(
        self,
        report: dict[str, Any],
        *,
        name: str,
        target: dict[str, Any],
        request: dict[str, Any],
        call: Callable[[], Any],
        mutation: bool,
        on_success: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        operation = {
            "id": len(report["operations"]) + 1,
            "at_utc": utc_now(),
            "name": name,
            "target": deepcopy(target),
            "collection": COLLECTION if name != "flush" else None,
            "status": "intent" if mutation else "calling",
            **self._json_safe(request),
        }
        report["operations"].append(operation)
        self._save(report)
        try:
            response = dict(call())
        except Exception as error:
            response = {
                "ok": False,
                "status": "exception",
                "message": str(error),
                "revision": 0,
                "snapshot": None,
            }
        if response.get("ok") is True and on_success is not None:
            on_success(response)
        operation["status"] = "completed"
        operation["response"] = self._json_safe(response)
        self._save(report)
        return response

    @staticmethod
    def _record_check(
        report: dict[str, Any], name: str, passed: bool, detail: str
    ) -> None:
        report["checks"].append(
            {
                "at_utc": utc_now(),
                "name": name,
                "passed": bool(passed),
                "detail": detail,
            }
        )
        if not passed:
            raise TestFailure(detail)

    def _capture(
        self,
        bridge: Any,
        report: dict[str, Any],
        target: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        response = self._journal_call(
            report,
            name="capture",
            target=target,
            request={},
            call=lambda: bridge.capture(self.server, target, COLLECTION),
            mutation=False,
        )
        snapshot = self._snapshot(response)
        status = str(response.get("status", ""))
        if response.get("ok") is not True and status not in {"not_found", "captured"}:
            raise TestFailure(
                "live capture failed: "
                + str(response.get("message") or status or "unknown error")
            )
        return response, snapshot

    @staticmethod
    def _resource_index(
        report: dict[str, Any], target: dict[str, Any], key: str
    ) -> int | None:
        for index, resource in enumerate(report["resources"]):
            if resource.get("target") == target and resource.get("key") == key:
                return index
        return None

    def _record_resource(
        self,
        report: dict[str, Any],
        target: dict[str, Any],
        key: str,
        value: Any,
    ) -> None:
        resource = {
            "target": deepcopy(target),
            "collection": COLLECTION,
            "key": key,
            "value": self._json_safe(value),
            "owned": True,
            "certainty": "set_value_applied",
        }
        index = self._resource_index(report, target, key)
        if index is None:
            report["resources"].append(resource)
        else:
            report["resources"][index] = resource

    def _set_value(
        self,
        bridge: Any,
        report: dict[str, Any],
        target: dict[str, Any],
        key: str,
        value: Any,
        expected_revision: int | None,
    ) -> dict[str, Any]:
        response = self._journal_call(
            report,
            name="set_value",
            target=target,
            request={
                "key": key,
                "value": value,
                "expected_revision": expected_revision,
            },
            call=lambda: bridge.set_value(
                self.server, target, COLLECTION, key, value, expected_revision
            ),
            mutation=True,
            on_success=lambda unused: self._record_resource(report, target, key, value),
        )
        return response

    def _remove_value(
        self,
        bridge: Any,
        report: dict[str, Any],
        target: dict[str, Any],
        key: str,
        expected_revision: int | None,
    ) -> dict[str, Any]:
        return self._journal_call(
            report,
            name="remove_value",
            target=target,
            request={"key": key, "expected_revision": expected_revision},
            call=lambda: bridge.remove_value(
                self.server, target, COLLECTION, key, expected_revision
            ),
            mutation=True,
        )

    def _clear_collection(
        self,
        bridge: Any,
        report: dict[str, Any],
        target: dict[str, Any],
        expected_revision: int | None,
    ) -> dict[str, Any]:
        return self._journal_call(
            report,
            name="clear_collection",
            target=target,
            request={"expected_revision": expected_revision},
            call=lambda: bridge.clear_collection(
                self.server, target, COLLECTION, expected_revision
            ),
            mutation=True,
        )

    def _flush(
        self, bridge: Any, report: dict[str, Any], target: dict[str, Any]
    ) -> dict[str, Any]:
        return self._journal_call(
            report,
            name="flush",
            target=target,
            request={},
            call=lambda: bridge.flush(self.server, target),
            mutation=True,
        )

    def _require_complete_service(
        self,
        bridge: Any,
        targets: list[tuple[str, dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        status = dict(bridge.status(self.server))
        if status.get("available") is not True:
            raise TestFailure(
                "native service is unavailable; no mutation was attempted: "
                + str(status.get("message") or status.get("adapter") or "unavailable")
            )
        if status.get("complete_control") is True:
            return status
        if status.get("operational_live") is not True:
            raise TestFailure(
                "native service is not live-test ready; no mutation was attempted: "
                + str(status.get("message") or status.get("adapter") or "unavailable")
            )

        capabilities = status.get("capabilities")
        if not isinstance(capabilities, dict):
            raise TestFailure("native service returned no capability map")
        required_operations = {
            "read",
            "write",
            "remove",
            "clear",
            "list_ids",
            "list_collections",
            "byte_count",
            "persistence_flush",
            "exact_build_match",
            "exact_binary_hash_match",
            "symbols_validated",
        }
        missing = sorted(
            name for name in required_operations if capabilities.get(name) is not True
        )
        target_capability = {
            "world": "world",
            "online_player": "online_players",
            "offline_player": "offline_players",
            "loaded_entity": "loaded_entities",
            "stored_entity": "stored_entities",
            "player_inventory_slot": "player_inventory_items",
            "player_armor_slot": "player_armor_items",
            "player_offhand_slot": "player_offhand_items",
            "player_ender_chest_slot": "player_ender_chest_items",
            "block_container_slot": "block_container_items",
            "dropped_item": "dropped_items",
            "block_entity": "block_entities",
        }
        for label, target in targets or []:
            capability = target_capability.get(str(target.get("kind", "")))
            if capability is None or capabilities.get(capability) is not True:
                missing.append(f"{label}:{capability or 'unknown_target'}")
        if missing:
            raise TestFailure(
                "selected live test requires unavailable capabilities: "
                + ", ".join(missing)
            )
        return status

    def _run_target(
        self,
        bridge: Any,
        report: dict[str, Any],
        label: str,
        target: dict[str, Any],
    ) -> None:
        baseline_response, baseline = self._capture(bridge, report, target)
        baseline_properties = self._properties(baseline)
        self._record_check(
            report,
            f"{label}.preflight_empty",
            not baseline_properties,
            (
                "fixed tester collection is empty"
                if not baseline_properties
                else "fixed tester collection contains data; run cleanup and review conflicts first"
            ),
        )

        prefix = f"dptest.{report['run_id'][:12]}"
        values: list[tuple[str, Any]] = [
            (f"{prefix}.bool", True),
            (f"{prefix}.double", 42.125),
            (f"{prefix}.string", f"live-round-trip:{report['run_id']}:§aUTF-8"),
            (f"{prefix}.vector", {"x": 1.25, "y": 64.5, "z": -3.75}),
        ]
        revision: int | None = self._revision(baseline, baseline_response)
        stale_revision: int | None = None
        expected: dict[str, Any] = {}

        for index, (key, value) in enumerate(values):
            response = self._set_value(bridge, report, target, key, value, revision)
            self._record_check(
                report,
                f"{label}.set.{index}",
                response.get("ok") is True,
                str(response.get("message") or f"set {key}"),
            )
            expected[key] = value
            capture_response, snapshot = self._capture(bridge, report, target)
            revision = self._revision(snapshot, capture_response)
            if index == 0:
                stale_revision = revision
            actual = self._properties(snapshot).get(key)
            self._record_check(
                report,
                f"{label}.round_trip.{index}",
                self._values_equal(actual, value),
                f"readback for {key} {'matched' if self._values_equal(actual, value) else 'did not match'}",
            )

        edit_key = values[0][0]
        _, before_edit = self._capture(bridge, report, target)
        revision = self._revision(before_edit, {})
        edited = self._set_value(bridge, report, target, edit_key, False, revision)
        self._record_check(
            report,
            f"{label}.edit",
            edited.get("ok") is True,
            str(edited.get("message") or "existing-value edit failed"),
        )
        expected[edit_key] = False
        _, after_edit = self._capture(bridge, report, target)
        self._record_check(
            report,
            f"{label}.edit_readback",
            self._values_equal(self._properties(after_edit).get(edit_key), False),
            "edited value read back with its replacement value",
        )

        conflict_key, conflict_original = edit_key, False
        conflict_response = self._set_value(
            bridge, report, target, conflict_key, True, stale_revision
        )
        if conflict_response.get("ok") is True:
            expected[conflict_key] = True
        self._record_check(
            report,
            f"{label}.stale_revision_conflict",
            conflict_response.get("ok") is not True
            and str(conflict_response.get("status", "")) == "conflict",
            "stale expected revision was rejected as conflict",
        )
        # A rejected set does not own the attempted value; retain the proven one.
        self._record_resource(report, target, conflict_key, conflict_original)

        remove_key = values[1][0]
        _, before_remove = self._capture(bridge, report, target)
        revision = self._revision(before_remove, {})
        removed = self._remove_value(bridge, report, target, remove_key, revision)
        self._record_check(
            report,
            f"{label}.remove",
            removed.get("ok") is True,
            str(removed.get("message") or "remove failed"),
        )
        expected.pop(remove_key)
        _, after_remove = self._capture(bridge, report, target)
        self._record_check(
            report,
            f"{label}.remove_readback",
            remove_key not in self._properties(after_remove),
            "removed key is absent from capture",
        )
        flushed = self._flush(bridge, report, target)
        self._record_check(
            report,
            f"{label}.flush",
            flushed.get("ok") is True,
            str(flushed.get("message") or "flush failed"),
        )
        # Absence is not durable until its flush succeeds.  Keep cleanup
        # ownership across a false success or failed flush so restart cannot
        # resurrect an orphaned tester value.
        resource_index = self._resource_index(report, target, remove_key)
        if resource_index is not None:
            report["resources"][resource_index]["owned"] = False

        _, before_clear = self._capture(bridge, report, target)
        current = self._properties(before_clear)
        exact_owned_set = set(current) == set(expected) and all(
            self._values_equal(current.get(key), value)
            for key, value in expected.items()
        )
        self._record_check(
            report,
            f"{label}.clear_preflight",
            exact_owned_set,
            "collection contains exactly the runner-owned values before clear",
        )
        revision = self._revision(before_clear, {})
        cleared = self._clear_collection(bridge, report, target, revision)
        self._record_check(
            report,
            f"{label}.clear",
            cleared.get("ok") is True,
            str(cleared.get("message") or "clear failed"),
        )
        _, after_clear = self._capture(bridge, report, target)
        self._record_check(
            report,
            f"{label}.clear_readback",
            not self._properties(after_clear),
            "collection is empty after clear",
        )
        clear_flushed = self._flush(bridge, report, target)
        self._record_check(
            report,
            f"{label}.clear_flush",
            clear_flushed.get("ok") is True,
            str(clear_flushed.get("message") or "clear flush failed"),
        )
        for resource in report["resources"]:
            if resource.get("target") == target:
                resource["owned"] = False

    def _finish_failure(
        self, sender: CommandSender, report: dict[str, Any], error: Exception
    ) -> bool:
        report["state"] = "failed"
        report["outcome"] = "failed"
        report["completed_at_utc"] = utc_now()
        report["errors"].append(str(error))
        path = self._save(report)
        sender.send_message(f"Dynamic Properties test FAILED: {error}")
        sender.send_message(f"Report: {path}")
        if any(resource.get("owned") for resource in report["resources"]):
            sender.send_message(
                "Owned values remain; review the report and run /dptest cleanup confirm."
            )
        return True

    def _handle_run(self, sender: CommandSender, args: list[str]) -> bool:
        if (
            len(args) != 2
            or args[0].casefold() not in {"world", "player", "configured", "all"}
            or args[1].casefold() != "confirm"
        ):
            sender.send_message(
                "Usage: /dptest run <world|player|configured|all> confirm"
            )
            return True
        bridge = self._bridge(sender)
        if bridge is None:
            return True
        if not self._may_start_new_run(sender):
            return True
        scope = args[0].casefold()
        try:
            targets = self._targets(scope, sender)
        except TestFailure as error:
            sender.send_message(str(error))
            return True
        report = new_report(
            mode="acceptance",
            operator=self._sender_name(sender),
            scopes=[label for label, _ in targets],
        )
        self._save(report)
        try:
            service_status = self._require_complete_service(bridge, targets)
            report["service_status"] = self._json_safe(service_status)
            # Preflight every selected target before the first mutation.
            for label, target in targets:
                _, snapshot = self._capture(bridge, report, target)
                if self._properties(snapshot):
                    raise TestFailure(
                        f"{label} fixed tester collection is not empty; cleanup is required"
                    )
            for label, target in targets:
                self._run_target(bridge, report, label, target)
            report["state"] = "completed"
            report["outcome"] = "passed"
            report["completed_at_utc"] = utc_now()
            path = self._save(report)
            remove_checkpoint(Path(self.data_folder))
            sender.send_message(
                f"Dynamic Properties live {scope} suite PASSED ({len(report['checks'])} checks)."
            )
            sender.send_message(f"Report: {path}")
            return True
        except Exception as error:
            return self._finish_failure(sender, report, error)

    def _handle_persistence_prepare(self, sender: CommandSender, bridge: Any) -> bool:
        if not self._may_start_new_run(sender):
            return True
        target = self._world_target()
        report = new_report(
            mode="persistence", operator=self._sender_name(sender), scopes=["world"]
        )
        report["prepare_process_incarnation"] = self._process_incarnation()
        self._save(report)
        try:
            report["service_status"] = self._json_safe(
                self._require_complete_service(
                    bridge, [("world", self._world_target())]
                )
            )
            capture_response, snapshot = self._capture(bridge, report, target)
            if self._properties(snapshot):
                raise TestFailure(
                    "fixed tester collection is not empty; cleanup is required"
                )
            key = "dptest.persistence"
            value = f"restart-proof:{report['run_id']}"
            revision = self._revision(snapshot, capture_response)
            response = self._set_value(bridge, report, target, key, value, revision)
            self._record_check(
                report,
                "persistence.prepare_set",
                response.get("ok") is True,
                str(response.get("message") or "persistence set failed"),
            )
            _, readback = self._capture(bridge, report, target)
            self._record_check(
                report,
                "persistence.prepare_readback",
                self._values_equal(self._properties(readback).get(key), value),
                "persistence token read back before restart",
            )
            flushed = self._flush(bridge, report, target)
            self._record_check(
                report,
                "persistence.prepare_flush",
                flushed.get("ok") is True,
                str(flushed.get("message") or "persistence flush failed"),
            )
            report["state"] = "awaiting_restart"
            report["outcome"] = "pending_restart_verification"
            path = self._save(report)
            sender.send_message("Persistence token prepared and flushed.")
            sender.send_message(
                "Restart the server cleanly, then run /dptest persistence verify."
            )
            sender.send_message(f"Checkpoint/report: {path}")
            return True
        except Exception as error:
            return self._finish_failure(sender, report, error)

    def _handle_persistence_verify(self, sender: CommandSender, bridge: Any) -> bool:
        data_folder = Path(self.data_folder)
        try:
            report = load_checkpoint(data_folder)
        except Exception as error:
            sender.send_message(
                f"No valid persistence checkpoint is available: {error}"
            )
            return True
        if (
            report.get("mode") != "persistence"
            or report.get("state") != "awaiting_restart"
        ):
            sender.send_message(
                "The active checkpoint is not awaiting persistence verification."
            )
            return True
        prepare_process_incarnation = report.get("prepare_process_incarnation")
        if (
            not isinstance(prepare_process_incarnation, str)
            or len(prepare_process_incarnation) != 32
            or any(
                character not in "0123456789abcdef"
                for character in prepare_process_incarnation
            )
        ):
            sender.send_message(
                "The persistence checkpoint has no valid prepare process incarnation; "
                "it was preserved for cleanup."
            )
            return True
        if prepare_process_incarnation == self._process_incarnation():
            sender.send_message(
                "Persistence verification requires a clean server restart; "
                "the prepare process is still running."
            )
            return True
        try:
            self._require_complete_service(
                bridge, [("world", self._world_target())]
            )
            resources = report.get("resources")
            if not isinstance(resources, list):
                raise TestFailure("persistence checkpoint resources are malformed")
            owned = [
                item
                for item in resources
                if isinstance(item, dict) and item.get("owned") is True
            ]
            if len(owned) != 1:
                raise TestFailure(
                    "persistence checkpoint must contain exactly one owned token; "
                    f"found {len(owned)}"
                )
            resource = owned[0]
            target = dict(resource["target"])
            expected_key = "dptest.persistence"
            expected_value = f"restart-proof:{report['run_id']}"
            if (
                target != self._world_target()
                or resource.get("collection") != COLLECTION
                or resource.get("key") != expected_key
                or resource.get("value") != expected_value
            ):
                raise TestFailure(
                    "persistence checkpoint does not belong to this world/collection"
                )
            key = expected_key
            expected = expected_value
            _, snapshot = self._capture(bridge, report, target)
            properties = self._properties(snapshot)
            self._record_check(
                report,
                "persistence.after_restart_readback",
                key in properties and self._values_equal(properties[key], expected),
                "exact persistence token survived the server restart",
            )
            revision = self._revision(snapshot, {})
            removed = self._remove_value(bridge, report, target, key, revision)
            self._record_check(
                report,
                "persistence.cleanup_remove",
                removed.get("ok") is True,
                str(removed.get("message") or "persistence cleanup failed"),
            )
            _, after = self._capture(bridge, report, target)
            self._record_check(
                report,
                "persistence.cleanup_readback",
                key not in self._properties(after),
                "persistence token was removed after verification",
            )
            flushed = self._flush(bridge, report, target)
            self._record_check(
                report,
                "persistence.cleanup_flush",
                flushed.get("ok") is True,
                str(flushed.get("message") or "cleanup flush failed"),
            )
            resource["owned"] = False
            report["state"] = "completed"
            report["outcome"] = "persistence_passed"
            report["completed_at_utc"] = utc_now()
            path = self._save(report)
            if any(
                isinstance(item, dict) and item.get("owned") is True
                for item in resources
            ):
                raise TestFailure(
                    "persistence verification finished with unresolved ownership records"
                )
            remove_checkpoint(data_folder)
            sender.send_message("Dynamic Properties restart persistence PASSED.")
            sender.send_message(f"Report: {path}")
            return True
        except Exception as error:
            return self._finish_failure(sender, report, error)

    def _handle_persistence(self, sender: CommandSender, args: list[str]) -> bool:
        if len(args) != 1 or args[0].casefold() not in {"prepare", "verify"}:
            sender.send_message("Usage: /dptest persistence <prepare|verify>")
            return True
        bridge = self._bridge(sender)
        if bridge is None:
            return True
        if args[0].casefold() == "prepare":
            return self._handle_persistence_prepare(sender, bridge)
        return self._handle_persistence_verify(sender, bridge)

    @staticmethod
    def _allowed_cleanup_target(target: Any) -> bool:
        try:
            validate_target(target)
        except ValueError:
            return False
        return True

    def _cleanup_resource(
        self,
        bridge: Any,
        report: dict[str, Any],
        resource: dict[str, Any],
    ) -> tuple[str | None, bool]:
        target = resource.get("target")
        key = resource.get("key")
        if (
            resource.get("collection") != COLLECTION
            or not self._allowed_cleanup_target(target)
            or not isinstance(key, str)
            or not key.startswith("dptest.")
        ):
            return "resource is outside the fixed tester ownership boundary", False
        _, snapshot = self._capture(bridge, report, target)
        properties = self._properties(snapshot)
        if key not in properties:
            resource["cleanup_result"] = "already_absent_pending_flush"
            return None, True
        if not self._values_equal(properties[key], resource.get("value")):
            return "value changed after the tester recorded ownership; preserved", False
        revision = self._revision(snapshot, {})
        removed = self._remove_value(bridge, report, target, key, revision)
        if removed.get("ok") is not True:
            return (
                "revision-guarded remove failed: "
                + str(
                    removed.get("message") or removed.get("status") or "unknown error"
                ),
                False,
            )
        _, after = self._capture(bridge, report, target)
        if key in self._properties(after):
            return "remove returned success but the owned key remains", False
        resource["cleanup_result"] = "removed_pending_flush"
        return None, True

    def _handle_cleanup(self, sender: CommandSender, args: list[str]) -> bool:
        if len(args) != 1 or args[0].casefold() != "confirm":
            sender.send_message(
                "Cleanup is mutation-capable. Use /dptest cleanup confirm"
            )
            return True
        bridge = self._bridge(sender)
        if bridge is None:
            return True
        data_folder = Path(self.data_folder)
        try:
            report = (
                load_checkpoint(data_folder)
                if checkpoint_path(data_folder).is_file()
                else load_latest(data_folder)
            )
        except Exception as error:
            sender.send_message(
                f"No valid tester report is available for cleanup: {error}"
            )
            return True
        if report.get("state") in {"running", "cleanup_running"}:
            sender.send_message(
                "Cleanup refused because a mutation journal is still active. "
                "Wait for it to finish; after a restart, checkpoint recovery will "
                "mark an interrupted journal safe to inspect."
            )
            return True
        report["state"] = "cleanup_running"
        report["cleanup"] = {"state": "running", "conflicts": []}
        self._save(report)
        pending: list[tuple[dict[str, Any], dict[str, Any]]] = []
        pending_targets: list[dict[str, Any]] = []
        for resource in report.get("resources", []):
            if resource.get("owned") is not True:
                continue
            try:
                reason, pending_flush = self._cleanup_resource(bridge, report, resource)
            except Exception as error:
                reason = f"cleanup could not safely inspect/remove the value: {error}"
                pending_flush = False
            target = resource.get("target")
            if pending_flush and isinstance(target, dict):
                pending.append((target, resource))
                if target not in pending_targets:
                    pending_targets.append(target)
            if reason:
                report["cleanup"]["conflicts"].append(
                    {
                        "target": deepcopy(target),
                        "key": resource.get("key"),
                        "reason": reason,
                    }
                )
            self._save(report)
        for target in pending_targets:
            flushed = self._flush(bridge, report, target)
            if flushed.get("ok") is not True:
                report["cleanup"]["conflicts"].append(
                    {
                        "target": deepcopy(target),
                        "key": None,
                        "reason": "cleanup flush failed: "
                        + str(flushed.get("message") or flushed.get("status")),
                    }
                )
                continue
            for pending_target, resource in pending:
                if pending_target != target:
                    continue
                result = str(resource.get("cleanup_result", ""))
                resource["cleanup_result"] = result.removesuffix("_pending_flush")
                resource["owned"] = False
            self._save(report)
        conflicts = report["cleanup"]["conflicts"]
        report["cleanup"]["state"] = "conflicts" if conflicts else "completed"
        report["cleanup"]["completed_at_utc"] = utc_now()
        report["state"] = "cleanup_conflicts" if conflicts else "cleanup_completed"
        report["outcome"] = "cleanup_conflicts" if conflicts else "cleanup_completed"
        report["completed_at_utc"] = utc_now()
        path = self._save(report)
        if not conflicts:
            remove_checkpoint(data_folder)
        sender.send_message(
            f"Cleanup finished with {len(conflicts)} conflict(s). Report: {path}"
        )
        if conflicts:
            sender.send_message(
                "Conflicting values were preserved; inspect /dptest report."
            )
        return True

    def _handle_inventory(self, sender: CommandSender, args: list[str]) -> bool:
        if len(args) != 1 or args[0].casefold() not in {
            "world",
            "player",
            "configured",
            "all",
        }:
            sender.send_message(
                "Usage: /dptest inventory <world|player|configured|all>"
            )
            return True
        bridge = self._bridge(sender)
        if bridge is None:
            return True
        scope = args[0].casefold()
        try:
            targets = self._targets(scope, sender)
            service_status = self._require_complete_service(bridge, targets)
            report = new_report(
                mode="inventory",
                operator=self._sender_name(sender),
                scopes=[label for label, _ in targets],
            )
            report["service_status"] = self._json_safe(service_status)
            report["inventory"] = []
            collection_count = 0
            property_count = 0
            for label, target in targets:
                listing = dict(bridge.list_collections(self.server, target))
                if listing.get("ok") is not True:
                    raise TestFailure(
                        f"{label} collection inventory failed: "
                        + str(
                            listing.get("message")
                            or listing.get("status")
                            or "unknown error"
                        )
                    )
                collections = listing.get("collections")
                if not isinstance(collections, list) or not all(
                    isinstance(item, str) for item in collections
                ):
                    raise TestFailure(
                        f"{label} collection inventory returned a malformed collection list"
                    )
                snapshots: list[dict[str, Any]] = []
                for collection in collections:
                    response = dict(bridge.capture(self.server, target, collection))
                    if response.get("ok") is not True:
                        raise TestFailure(
                            f"{label}/{collection} capture failed: "
                            + str(
                                response.get("message")
                                or response.get("status")
                                or "unknown error"
                            )
                        )
                    snapshot = self._snapshot(response)
                    if snapshot is None:
                        raise TestFailure(
                            f"{label}/{collection} capture returned no snapshot"
                        )
                    snapshots.append(self._json_safe(snapshot))
                    collection_count += 1
                    property_count += len(self._properties(snapshot))
                report["inventory"].append(
                    {
                        "label": label,
                        "target": self._json_safe(target),
                        "collections": snapshots,
                    }
                )
            report["state"] = "completed"
            report["outcome"] = "inventory_captured"
            report["completed_at_utc"] = utc_now()
            path = save_report(Path(self.data_folder), report, checkpoint=False)
            sender.send_message(
                "Dynamic Properties inventory captured "
                f"{collection_count} collection(s) and {property_count} property value(s)."
            )
            sender.send_message(f"Report: {path}")
        except Exception as error:
            sender.send_message(f"Dynamic Properties inventory failed: {error}")
        return True

    def _handle_watch(self, sender: CommandSender, args: list[str]) -> bool:
        if len(args) != 1 or args[0].casefold() not in {
            "start",
            "drain",
            "status",
            "stop",
        }:
            sender.send_message("Usage: /dptest watch <start|drain|status|stop>")
            return True
        bridge = self._bridge(sender)
        if bridge is None:
            return True
        phase = args[0].casefold()
        try:
            if phase == "start":
                response = dict(bridge.start_external_watch(self.server))
            elif phase == "stop":
                response = dict(bridge.stop_external_watch(self.server))
            elif phase == "status":
                response = dict(bridge.external_watch_status(self.server))
            else:
                response = dict(bridge.drain_external_events(self.server))
                events = response.get("events")
                if not isinstance(events, list):
                    raise TestFailure("external watch returned a malformed event list")
                report = new_report(
                    mode="external_watch",
                    operator=self._sender_name(sender),
                    scopes=["external_mutations"],
                )
                report["external_events"] = self._json_safe(events)
                report["dropped_events"] = int(response.get("dropped", 0) or 0)
                report["watch_status"] = self._json_safe(response)
                report["state"] = "completed"
                report["outcome"] = "external_events_drained"
                report["completed_at_utc"] = utc_now()
                path = save_report(Path(self.data_folder), report, checkpoint=False)
                sender.send_message(
                    f"Captured {len(events)} external mutation event(s); "
                    f"dropped={report['dropped_events']}. Report: {path}"
                )
                return True
            self._send_json(sender, f"External watch {phase}", response)
        except Exception as error:
            sender.send_message(f"Dynamic Properties external watch failed: {error}")
        return True

    def _handle_status(self, sender: CommandSender, args: list[str]) -> bool:
        if args:
            sender.send_message("Usage: /dptest status")
            return True
        # Status must remain available when the service gate is closed; that
        # is precisely when its activation failures are most useful.
        bridge = self.live_bridge
        if bridge is None:
            try:
                bridge = import_live_bridge(self.version)
            except Exception as error:
                sender.send_message(f"Native Dynamic Properties status failed: {error}")
                return True
        try:
            status = dict(bridge.status(self.server))
        except Exception as error:
            sender.send_message(f"Native Dynamic Properties status failed: {error}")
            return True
        self._send_json(sender, "Native Dynamic Properties status", status)
        return True

    def _handle_report(self, sender: CommandSender, args: list[str]) -> bool:
        if args:
            sender.send_message("Usage: /dptest report")
            return True
        data_folder = Path(self.data_folder)
        try:
            report = load_latest(data_folder)
        except Exception as error:
            sender.send_message(f"No valid tester report is available: {error}")
            return True
        digest = str(dict(report.get("integrity") or {}).get("digest", ""))
        path = report_path(data_folder, str(report["run_id"]))
        sender.send_message(
            f"Latest report {report['run_id']}: state={report['state']} "
            f"outcome={report['outcome']} checks={len(report.get('checks', []))} "
            f"integrity={digest[:12]}..."
        )
        sender.send_message(f"Report: {path}")
        sender.send_message(f"Latest pointer: {latest_report_path(data_folder)}")
        if checkpoint_path(data_folder).is_file():
            sender.send_message(f"Active checkpoint: {checkpoint_path(data_folder)}")
        return True

    @staticmethod
    def _handle_help(sender: CommandSender, args: list[str]) -> bool:
        if args:
            sender.send_message("Usage: /dptest help")
            return True
        sender.send_message("/dptest status - show exact live-service readiness")
        sender.send_message(
            "/dptest run <world|player|configured|all> confirm - run the live suite"
        )
        sender.send_message(
            "/dptest inventory <world|player|configured|all> - capture existing tester-visible properties"
        )
        sender.send_message(
            "/dptest watch <start|drain|status|stop> - observe native external mutations"
        )
        sender.send_message(
            "/dptest persistence prepare - write and flush a restart token"
        )
        sender.send_message("/dptest persistence verify - verify after a clean restart")
        sender.send_message(
            "/dptest report - show the latest tamper-evident report path"
        )
        sender.send_message(
            "/dptest cleanup confirm - remove only matching owned values"
        )
        return True

    def on_command(
        self, sender: CommandSender, command: Command, args: list[str]
    ) -> bool:
        del command
        action = args[0].casefold() if args else "help"
        handlers = {
            "help": self._handle_help,
            "status": self._handle_status,
            "run": self._handle_run,
            "persistence": self._handle_persistence,
            "report": self._handle_report,
            "cleanup": self._handle_cleanup,
            "inventory": self._handle_inventory,
            "watch": self._handle_watch,
        }
        handler = handlers.get(action)
        if handler is None:
            sender.send_message("Unknown action. Use /dptest help")
            return True
        if action not in {"run", "persistence", "cleanup"}:
            return bool(handler(sender, args[1:]))

        mutation_lock = getattr(self, "_mutation_lock", None)
        if mutation_lock is None:
            # Production initializes this during on_enable. Keep direct test
            # construction and unusual lifecycle ordering fail-safe as well.
            mutation_lock = Lock()
            self._mutation_lock = mutation_lock
        if not mutation_lock.acquire(blocking=False):
            sender.send_message(
                "Another Dynamic Properties tester mutation is still active; "
                "this command made no changes."
            )
            return True
        try:
            return bool(handler(sender, args[1:]))
        finally:
            mutation_lock.release()
