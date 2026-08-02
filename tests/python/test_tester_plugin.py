from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from threading import Lock
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DIR = (
    ROOT
    / "examples"
    / "python"
    / "dynamic_properties_tester_plugin"
    / "src"
    / "endstone_dynamic_properties_tester"
)


def load_plugin_module() -> ModuleType:
    package_name = "_dynamic_properties_tester_plugin_tests"
    package = ModuleType(package_name)
    package.__path__ = [str(PACKAGE_DIR)]  # type: ignore[attr-defined]
    sys.modules[package_name] = package
    fake_endstone = ModuleType("endstone")
    fake_command = ModuleType("endstone.command")
    fake_plugin = ModuleType("endstone.plugin")
    fake_command.Command = type("Command", (), {})  # type: ignore[attr-defined]
    fake_command.CommandSender = type("CommandSender", (), {})  # type: ignore[attr-defined]
    fake_plugin.Plugin = type("Plugin", (), {})  # type: ignore[attr-defined]
    previous = {
        name: sys.modules.get(name)
        for name in ("endstone", "endstone.command", "endstone.plugin")
    }
    sys.modules["endstone"] = fake_endstone
    sys.modules["endstone.command"] = fake_command
    sys.modules["endstone.plugin"] = fake_plugin
    try:
        name = f"{package_name}.plugin"
        spec = importlib.util.spec_from_file_location(name, PACKAGE_DIR / "plugin.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        for name, value in previous.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


PLUGIN_MODULE = load_plugin_module()
PluginClass = PLUGIN_MODULE.DynamicPropertiesTesterPlugin
REPORT = sys.modules[f"{PLUGIN_MODULE.__package__}.report"]


class FakeSender:
    def __init__(
        self, *, name: str = "operator", xuid: str = "2533274790000000"
    ) -> None:
        self.name = name
        self.xuid = xuid
        self.messages: list[str] = []

    def send_message(self, message: str) -> None:
        self.messages.append(str(message))


class FakeLogger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)

    def warning(self, message: str) -> None:
        self.messages.append(message)

    def error(self, message: str) -> None:
        self.messages.append(message)


class FakeServer:
    def __init__(self) -> None:
        self.level = type("Level", (), {"name": "acceptance-world"})()


class FakeBridge:
    __version__ = "0.1.0a3"

    def __init__(self) -> None:
        self.stores: dict[str, dict[str, Any]] = {}
        self.revisions: dict[str, int] = {}
        self.calls: list[str] = []
        self.watch_active = False
        self.external_events: list[dict[str, Any]] = []

    @staticmethod
    def _id(target: dict[str, str]) -> str:
        return json.dumps(target, sort_keys=True)

    def available(self, server: Any) -> bool:
        return True

    def status(self, server: Any) -> dict[str, Any]:
        return {
            "available": True,
            "adapter": "fake-complete-live",
            "complete_control": True,
            "capabilities": {"world": True, "online_player": True},
        }

    def capture(
        self, server: Any, target: dict[str, str], collection: str
    ) -> dict[str, Any]:
        self.calls.append("capture")
        identity = self._id(target)
        if identity not in self.stores:
            return {
                "ok": False,
                "status": "not_found",
                "message": "collection absent",
                "revision": 0,
                "snapshot": None,
            }
        properties = deepcopy(self.stores[identity])
        revision = self.revisions[identity]
        return {
            "ok": True,
            "status": "captured",
            "message": "captured",
            "revision": revision,
            "snapshot": {
                "target": deepcopy(target),
                "collection": collection,
                "properties": properties,
                "revision": revision,
                "exists": True,
                "loaded": True,
                "persistent": True,
                "writable": True,
            },
        }

    def list_collections(self, server: Any, target: dict[str, Any]) -> dict[str, Any]:
        self.calls.append("list_collections")
        collections = [REPORT.COLLECTION] if self._id(target) in self.stores else []
        return {
            "ok": True,
            "status": "captured",
            "message": "listed",
            "collections": collections,
        }

    def set_value(
        self,
        server: Any,
        target: dict[str, str],
        collection: str,
        key: str,
        value: Any,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        self.calls.append("set_value")
        identity = self._id(target)
        current = self.revisions.get(identity, 0)
        if expected_revision is not None and expected_revision != current:
            return {
                "ok": False,
                "status": "conflict",
                "message": "stale",
                "revision": current,
            }
        self.stores.setdefault(identity, {})[key] = deepcopy(value)
        self.revisions[identity] = current + 1
        return {
            "ok": True,
            "status": "applied",
            "message": "set",
            "revision": current + 1,
        }

    def remove_value(
        self,
        server: Any,
        target: dict[str, str],
        collection: str,
        key: str,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        self.calls.append("remove_value")
        identity = self._id(target)
        current = self.revisions.get(identity, 0)
        if expected_revision is not None and expected_revision != current:
            return {
                "ok": False,
                "status": "conflict",
                "message": "stale",
                "revision": current,
            }
        self.stores.setdefault(identity, {}).pop(key, None)
        self.revisions[identity] = current + 1
        return {
            "ok": True,
            "status": "applied",
            "message": "removed",
            "revision": current + 1,
        }

    def clear_collection(
        self,
        server: Any,
        target: dict[str, str],
        collection: str,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        self.calls.append("clear_collection")
        identity = self._id(target)
        current = self.revisions.get(identity, 0)
        if expected_revision is not None and expected_revision != current:
            return {
                "ok": False,
                "status": "conflict",
                "message": "stale",
                "revision": current,
            }
        self.stores[identity] = {}
        self.revisions[identity] = current + 1
        return {
            "ok": True,
            "status": "applied",
            "message": "cleared",
            "revision": current + 1,
        }

    def flush(self, server: Any, target: dict[str, str]) -> dict[str, Any]:
        self.calls.append("flush")
        return {
            "ok": True,
            "status": "applied",
            "message": "flushed",
            "revision": self.revisions.get(self._id(target), 0),
        }

    def start_external_watch(self, server: Any) -> dict[str, Any]:
        self.watch_active = True
        self.external_events.clear()
        return self.external_watch_status(server)

    def stop_external_watch(self, server: Any) -> dict[str, Any]:
        self.watch_active = False
        return self.external_watch_status(server)

    def external_watch_status(self, server: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "captured",
            "active": self.watch_active,
            "queued": len(self.external_events),
            "dropped": 0,
            "capacity": 1024,
        }

    def drain_external_events(self, server: Any) -> dict[str, Any]:
        events = deepcopy(self.external_events)
        self.external_events.clear()
        return {
            **self.external_watch_status(server),
            "events": events,
            "dropped": 0,
        }


def make_plugin(folder: str, bridge: FakeBridge | None) -> Any:
    plugin = object.__new__(PluginClass)
    plugin.server = FakeServer()
    plugin.data_folder = folder
    plugin.live_bridge = bridge
    plugin.bridge_error = "test bridge missing"
    plugin.logger = FakeLogger()
    return plugin


def different_incarnation(token: str) -> str:
    replacement = "0" if token[0] != "0" else "1"
    return replacement + token[1:]


def test_run_requires_exact_confirmation_before_any_bridge_call() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        bridge = FakeBridge()
        plugin = make_plugin(temporary, bridge)
        sender = FakeSender()
        assert plugin._handle_run(sender, ["world"])
        assert bridge.calls == []
        assert any("confirm" in message for message in sender.messages)


def test_world_acceptance_suite_passes_and_leaves_collection_empty() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        bridge = FakeBridge()
        plugin = make_plugin(temporary, bridge)
        sender = FakeSender()
        assert plugin._handle_run(sender, ["world", "confirm"])
        report = REPORT.load_latest(Path(temporary))
        assert report["state"] == "completed"
        assert report["outcome"] == "passed"
        assert all(check["passed"] for check in report["checks"])
        assert all(resource["owned"] is False for resource in report["resources"])
        assert bridge.stores[json.dumps(plugin._world_target(), sort_keys=True)] == {}
        assert not REPORT.checkpoint_path(Path(temporary)).exists()
        assert any("PASSED" in message for message in sender.messages)


def test_unavailable_bridge_reports_failure_and_never_uses_a_fallback(
    monkeypatch,
) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        plugin = make_plugin(temporary, None)
        sender = FakeSender()

        def missing(version: str):
            raise ModuleNotFoundError("package-local live bridge is missing")

        monkeypatch.setattr(PLUGIN_MODULE, "import_live_bridge", missing)
        assert plugin._handle_run(sender, ["world", "confirm"])
        assert any(
            "unavailable; no test was run" in message for message in sender.messages
        )
        assert not REPORT.latest_report_path(Path(temporary)).exists()


def test_status_reports_activation_failures_even_when_service_is_unavailable(
    monkeypatch,
) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        plugin = make_plugin(temporary, None)
        sender = FakeSender()
        bridge = FakeBridge()
        bridge.available = lambda server: False  # type: ignore[method-assign]
        bridge.status = lambda server: {  # type: ignore[method-assign]
            "available": False,
            "complete_control": False,
            "failures": ["stage probe not passed"],
        }
        monkeypatch.setattr(PLUGIN_MODULE, "import_live_bridge", lambda version: bridge)

        assert plugin._handle_status(sender, [])

        assert any("stage probe not passed" in message for message in sender.messages)


def test_absent_collection_creation_race_is_revision_guarded() -> None:
    class CreationRaceBridge(FakeBridge):
        def set_value(
            self,
            server: Any,
            target: dict[str, str],
            collection: str,
            key: str,
            value: Any,
            expected_revision: int | None = None,
        ) -> dict[str, Any]:
            identity = self._id(target)
            if identity not in self.stores:
                self.stores[identity] = {"outside.concurrent": "preserve"}
                self.revisions[identity] = 1
            return super().set_value(
                server, target, collection, key, value, expected_revision
            )

    with tempfile.TemporaryDirectory() as temporary:
        bridge = CreationRaceBridge()
        plugin = make_plugin(temporary, bridge)

        assert plugin._handle_run(FakeSender(), ["world", "confirm"])

        report = REPORT.load_checkpoint(Path(temporary))
        set_intent = next(
            operation
            for operation in report["operations"]
            if operation["name"] == "set_value"
        )
        store = bridge.stores[json.dumps(plugin._world_target(), sort_keys=True)]
        assert report["state"] == "failed"
        assert set_intent["expected_revision"] == 0
        assert store == {"outside.concurrent": "preserve"}


def test_persistence_creation_race_is_revision_guarded() -> None:
    class CreationRaceBridge(FakeBridge):
        def set_value(
            self,
            server: Any,
            target: dict[str, str],
            collection: str,
            key: str,
            value: Any,
            expected_revision: int | None = None,
        ) -> dict[str, Any]:
            identity = self._id(target)
            if identity not in self.stores:
                self.stores[identity] = {"outside.concurrent": "preserve"}
                self.revisions[identity] = 1
            return super().set_value(
                server, target, collection, key, value, expected_revision
            )

    with tempfile.TemporaryDirectory() as temporary:
        bridge = CreationRaceBridge()
        plugin = make_plugin(temporary, bridge)

        assert plugin._handle_persistence(FakeSender(), ["prepare"])

        report = REPORT.load_checkpoint(Path(temporary))
        set_intent = next(
            operation
            for operation in report["operations"]
            if operation["name"] == "set_value"
        )
        store = bridge.stores[json.dumps(plugin._world_target(), sort_keys=True)]
        assert report["state"] == "failed"
        assert set_intent["expected_revision"] == 0
        assert store == {"outside.concurrent": "preserve"}


def test_false_remove_success_preserves_cleanup_ownership() -> None:
    class FalseSuccessRemoveBridge(FakeBridge):
        def remove_value(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            self.calls.append("remove_value")
            return {
                "ok": True,
                "status": "applied",
                "message": "removed",
                "revision": 0,
            }

    with tempfile.TemporaryDirectory() as temporary:
        bridge = FalseSuccessRemoveBridge()
        plugin = make_plugin(temporary, bridge)

        assert plugin._handle_run(FakeSender(), ["world", "confirm"])

        report = REPORT.load_checkpoint(Path(temporary))
        removed_key = next(
            resource["key"]
            for resource in report["resources"]
            if resource["key"].endswith(".double")
        )
        resource = next(
            item for item in report["resources"] if item["key"] == removed_key
        )
        assert report["state"] == "failed"
        assert resource["owned"] is True


def test_false_clear_success_preserves_cleanup_ownership() -> None:
    class FalseSuccessClearBridge(FakeBridge):
        def clear_collection(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            self.calls.append("clear_collection")
            return {
                "ok": True,
                "status": "applied",
                "message": "cleared",
                "revision": 0,
            }

    with tempfile.TemporaryDirectory() as temporary:
        bridge = FalseSuccessClearBridge()
        plugin = make_plugin(temporary, bridge)

        assert plugin._handle_run(FakeSender(), ["world", "confirm"])

        report = REPORT.load_checkpoint(Path(temporary))
        assert report["state"] == "failed"
        assert any(resource["owned"] is True for resource in report["resources"])


def test_clear_flush_failure_preserves_cleanup_ownership() -> None:
    class ClearFlushFailureBridge(FakeBridge):
        def __init__(self) -> None:
            super().__init__()
            self.flush_count = 0

        def flush(self, server: Any, target: dict[str, str]) -> dict[str, Any]:
            self.flush_count += 1
            if self.flush_count == 1:
                return super().flush(server, target)
            self.calls.append("flush")
            return {
                "ok": False,
                "status": "persistence_failed",
                "message": "not durable",
            }

    with tempfile.TemporaryDirectory() as temporary:
        bridge = ClearFlushFailureBridge()
        plugin = make_plugin(temporary, bridge)

        assert plugin._handle_run(FakeSender(), ["world", "confirm"])

        report = REPORT.load_checkpoint(Path(temporary))
        assert report["state"] == "failed"
        assert any(resource["owned"] is True for resource in report["resources"])


def test_cleanup_preserves_a_changed_value_as_an_ownership_conflict() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        bridge = FakeBridge()
        plugin = make_plugin(temporary, bridge)
        target = plugin._world_target()
        report = REPORT.new_report(
            mode="acceptance", operator="operator", scopes=["world"]
        )
        report["state"] = "failed"
        report["resources"].append(
            {
                "target": target,
                "collection": REPORT.COLLECTION,
                "key": "dptest.owned",
                "value": "original-token",
                "owned": True,
                "certainty": "set_value_applied",
            }
        )
        REPORT.save_report(Path(temporary), report, checkpoint=True)
        identity = json.dumps(target, sort_keys=True)
        bridge.stores[identity] = {"dptest.owned": "outside-edit"}
        bridge.revisions[identity] = 8
        sender = FakeSender()
        assert plugin._handle_cleanup(sender, ["confirm"])
        cleaned = REPORT.load_latest(Path(temporary))
        assert cleaned["state"] == "cleanup_conflicts"
        assert cleaned["cleanup"]["conflicts"]
        assert bridge.stores[identity]["dptest.owned"] == "outside-edit"
        assert "remove_value" not in bridge.calls


def test_cleanup_flush_failure_preserves_ownership_for_retry() -> None:
    class FlushFailureBridge(FakeBridge):
        def flush(self, server: Any, target: dict[str, str]) -> dict[str, Any]:
            self.calls.append("flush")
            return {
                "ok": False,
                "status": "persistence_failed",
                "message": "not durable",
            }

    with tempfile.TemporaryDirectory() as temporary:
        bridge = FlushFailureBridge()
        plugin = make_plugin(temporary, bridge)
        target = plugin._world_target()
        report = REPORT.new_report(
            mode="acceptance", operator="operator", scopes=["world"]
        )
        report["state"] = "failed"
        report["resources"].append(
            {
                "target": target,
                "collection": REPORT.COLLECTION,
                "key": "dptest.owned",
                "value": "owned-token",
                "owned": True,
                "certainty": "set_value_applied",
            }
        )
        REPORT.save_report(Path(temporary), report, checkpoint=True)
        identity = json.dumps(target, sort_keys=True)
        bridge.stores[identity] = {"dptest.owned": "owned-token"}
        bridge.revisions[identity] = 1

        assert plugin._handle_cleanup(FakeSender(), ["confirm"])

        cleaned = REPORT.load_checkpoint(Path(temporary))
        resource = cleaned["resources"][0]
        assert cleaned["state"] == "cleanup_conflicts"
        assert resource["owned"] is True
        assert resource["cleanup_result"] == "removed_pending_flush"


def test_persistence_prepare_then_verify_uses_the_same_checkpoint_and_cleans_up() -> (
    None
):
    with tempfile.TemporaryDirectory() as temporary:
        bridge = FakeBridge()
        plugin = make_plugin(temporary, bridge)
        sender = FakeSender()
        assert plugin._handle_persistence(sender, ["prepare"])
        prepared = REPORT.load_checkpoint(Path(temporary))
        assert prepared["state"] == "awaiting_restart"
        assert any(resource["owned"] for resource in prepared["resources"])

        # The bridge store represents world data that survived the clean restart.
        restarted_plugin = make_plugin(temporary, bridge)
        restarted_plugin._process_incarnation = lambda: different_incarnation(
            prepared["prepare_process_incarnation"]
        )
        verify_sender = FakeSender()
        assert restarted_plugin._handle_persistence(verify_sender, ["verify"])
        verified = REPORT.load_latest(Path(temporary))
        assert verified["outcome"] == "persistence_passed"
        assert all(resource["owned"] is False for resource in verified["resources"])
        assert not REPORT.checkpoint_path(Path(temporary)).exists()
        assert any(
            "persistence PASSED" in message for message in verify_sender.messages
        )


def test_persistence_verify_requires_a_different_server_process() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        bridge = FakeBridge()
        plugin = make_plugin(temporary, bridge)
        assert plugin._handle_persistence(FakeSender(), ["prepare"])
        calls_before_verify = list(bridge.calls)

        sender = FakeSender()
        assert plugin._handle_persistence(sender, ["verify"])

        preserved = REPORT.load_checkpoint(Path(temporary))
        assert preserved["state"] == "awaiting_restart"
        assert bridge.calls == calls_before_verify
        assert any(
            "requires a clean server restart" in message for message in sender.messages
        )


def test_process_incarnation_is_stable_across_plugin_instances() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        first = make_plugin(temporary, FakeBridge())._process_incarnation()
        second = make_plugin(temporary, FakeBridge())._process_incarnation()

    assert first == second
    assert len(first) == 32
    assert all(character in "0123456789abcdef" for character in first)


def test_persistence_cleanup_flush_failure_preserves_ownership() -> None:
    class CleanupFlushFailureBridge(FakeBridge):
        def __init__(self) -> None:
            super().__init__()
            self.flush_count = 0

        def flush(self, server: Any, target: dict[str, str]) -> dict[str, Any]:
            self.flush_count += 1
            if self.flush_count == 1:
                return super().flush(server, target)
            self.calls.append("flush")
            return {
                "ok": False,
                "status": "persistence_failed",
                "message": "not durable",
            }

    with tempfile.TemporaryDirectory() as temporary:
        bridge = CleanupFlushFailureBridge()
        plugin = make_plugin(temporary, bridge)
        assert plugin._handle_persistence(FakeSender(), ["prepare"])
        prepared = REPORT.load_checkpoint(Path(temporary))
        plugin._process_incarnation = lambda: different_incarnation(
            prepared["prepare_process_incarnation"]
        )

        assert plugin._handle_persistence(FakeSender(), ["verify"])

        failed = REPORT.load_checkpoint(Path(temporary))
        assert failed["state"] == "failed"
        assert failed["resources"][0]["owned"] is True


def test_persistence_verify_rejects_multiple_owned_resources_without_mutation() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        bridge = FakeBridge()
        plugin = make_plugin(temporary, bridge)
        assert plugin._handle_persistence(FakeSender(), ["prepare"])
        report = REPORT.load_checkpoint(Path(temporary))
        report["resources"].append(
            {
                "target": plugin._world_target(),
                "collection": REPORT.COLLECTION,
                "key": "dptest.unexpected",
                "value": "unexpected",
                "owned": True,
                "certainty": "set_value_applied",
            }
        )
        REPORT.save_report(Path(temporary), report, checkpoint=True)
        calls_before_verify = list(bridge.calls)
        plugin._process_incarnation = lambda: different_incarnation(
            report["prepare_process_incarnation"]
        )

        sender = FakeSender()
        assert plugin._handle_persistence(sender, ["verify"])

        rejected = REPORT.load_checkpoint(Path(temporary))
        identity = json.dumps(plugin._world_target(), sort_keys=True)
        assert rejected["state"] == "failed"
        assert sum(item.get("owned") is True for item in rejected["resources"]) == 2
        assert bridge.calls == calls_before_verify
        assert bridge.stores[identity]["dptest.persistence"].startswith(
            "restart-proof:"
        )


def test_second_run_cannot_overwrite_an_active_persistence_ownership_checkpoint() -> (
    None
):
    with tempfile.TemporaryDirectory() as temporary:
        bridge = FakeBridge()
        plugin = make_plugin(temporary, bridge)
        first_sender = FakeSender()
        assert plugin._handle_persistence(first_sender, ["prepare"])
        first = REPORT.load_checkpoint(Path(temporary))
        first_call_count = len(bridge.calls)

        second_sender = FakeSender()
        assert plugin._handle_run(second_sender, ["world", "confirm"])
        preserved = REPORT.load_checkpoint(Path(temporary))
        assert preserved["run_id"] == first["run_id"]
        assert preserved["state"] == "awaiting_restart"
        assert len(bridge.calls) == first_call_count
        assert any("active checkpoint" in message for message in second_sender.messages)


def test_cleanup_refuses_a_live_mutation_journal() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        bridge = FakeBridge()
        plugin = make_plugin(temporary, bridge)
        report = REPORT.new_report(
            mode="acceptance", operator="operator", scopes=["world"]
        )
        REPORT.save_report(Path(temporary), report, checkpoint=True)

        sender = FakeSender()
        assert plugin._handle_cleanup(sender, ["confirm"])

        preserved = REPORT.load_checkpoint(Path(temporary))
        assert preserved["state"] == "running"
        assert bridge.calls == []
        assert any(
            "mutation journal is still active" in message for message in sender.messages
        )


def test_mutation_command_is_rejected_while_another_mutation_holds_the_gate() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        bridge = FakeBridge()
        plugin = make_plugin(temporary, bridge)
        plugin._mutation_lock = Lock()
        assert plugin._mutation_lock.acquire(blocking=False)
        try:
            sender = FakeSender()
            assert plugin.on_command(sender, None, ["cleanup", "confirm"])
        finally:
            plugin._mutation_lock.release()

        assert bridge.calls == []
        assert any("mutation is still active" in message for message in sender.messages)


def test_player_target_uses_authenticated_xuid_and_never_the_player_name() -> None:
    sender = FakeSender(name="Visible Name", xuid="123456789")
    assert PluginClass._player_target(sender) == {
        "kind": "online_player",
        "xuid": "123456789",
    }
    sender.xuid = ""
    try:
        PluginClass._player_target(sender)
    except PLUGIN_MODULE.TestFailure as error:
        assert "XUID" in str(error)
    else:
        raise AssertionError("player target accepted a sender without an XUID")


def test_configured_target_runs_full_crud_in_the_fixed_tester_collection() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        (folder / "targets.json").write_text(
            json.dumps(
                {
                    "schema": 1,
                    "targets": [
                        {
                            "label": "offline",
                            "enabled": True,
                            "target": {
                                "kind": "offline_player",
                                "world_id": "acceptance-world",
                                "xuid": "2533274790000001",
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        bridge = FakeBridge()
        plugin = make_plugin(temporary, bridge)

        assert plugin._handle_run(FakeSender(), ["configured", "confirm"])

        report = REPORT.load_latest(folder)
        assert report["outcome"] == "passed"
        assert report["scopes"] == ["configured:offline"]
        assert any(check["name"].endswith(".edit") for check in report["checks"])
        assert any(
            check["name"].endswith(".edit_readback") for check in report["checks"]
        )


def test_configured_suite_executes_all_twelve_target_families() -> None:
    targets: list[dict[str, Any]] = [
        {"kind": "world", "world_id": "acceptance-world"},
        {"kind": "online_player", "xuid": "online"},
        {"kind": "offline_player", "xuid": "offline"},
        {"kind": "loaded_entity", "entity_id": "loaded"},
        {"kind": "stored_entity", "entity_id": "stored"},
        {"kind": "player_inventory_slot", "xuid": "inventory", "slot": 0},
        {"kind": "player_armor_slot", "xuid": "armor", "slot": 0},
        {"kind": "player_offhand_slot", "xuid": "offhand", "slot": 0},
        {"kind": "player_ender_chest_slot", "xuid": "ender", "slot": 0},
        {
            "kind": "block_container_slot",
            "slot": 0,
            "block": {"dimension": "overworld", "x": 1, "y": 64, "z": 1},
        },
        {"kind": "dropped_item", "item_entity_id": "dropped"},
        {
            "kind": "block_entity",
            "block": {"dimension": "overworld", "x": 2, "y": 64, "z": 2},
        },
    ]
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        (folder / "targets.json").write_text(
            json.dumps(
                {
                    "schema": 1,
                    "targets": [
                        {
                            "label": f"target-{index}",
                            "enabled": True,
                            "target": target,
                        }
                        for index, target in enumerate(targets)
                    ],
                }
            ),
            encoding="utf-8",
        )
        bridge = FakeBridge()
        plugin = make_plugin(temporary, bridge)

        assert plugin._handle_run(FakeSender(), ["configured", "confirm"])

        report = REPORT.load_latest(folder)
        assert report["outcome"] == "passed"
        assert len(report["scopes"]) == 12
        assert len(bridge.stores) == 12
        assert all(properties == {} for properties in bridge.stores.values())


def test_inventory_records_existing_tester_visible_properties_without_mutation() -> (
    None
):
    with tempfile.TemporaryDirectory() as temporary:
        bridge = FakeBridge()
        plugin = make_plugin(temporary, bridge)
        target = plugin._world_target()
        identity = bridge._id(target)
        bridge.stores[identity] = {"existing": "old-value", "current": True}
        bridge.revisions[identity] = 7

        sender = FakeSender()
        assert plugin._handle_inventory(sender, ["world"])

        report = REPORT.load_latest(Path(temporary))
        snapshots = report["inventory"][0]["collections"]
        assert report["outcome"] == "inventory_captured"
        assert snapshots[0]["properties"] == {
            "existing": "old-value",
            "current": True,
        }
        assert "set_value" not in bridge.calls
        assert "remove_value" not in bridge.calls
        assert "clear_collection" not in bridge.calls


def test_external_watch_drain_writes_a_sealed_report() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        bridge = FakeBridge()
        plugin = make_plugin(temporary, bridge)
        sender = FakeSender()

        assert plugin._handle_watch(sender, ["start"])
        bridge.external_events.append(
            {
                "kind": "after_external_mutation",
                "operation": "set",
                "key": "new-property",
            }
        )
        assert plugin._handle_watch(sender, ["drain"])

        report = REPORT.load_latest(Path(temporary))
        assert report["outcome"] == "external_events_drained"
        assert report["external_events"][0]["key"] == "new-property"
        assert bridge.external_events == []
        REPORT.validate_report(report)


def test_on_disable_stops_the_external_watch() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        bridge = FakeBridge()
        bridge.watch_active = True
        plugin = make_plugin(temporary, bridge)

        plugin.on_disable()

        assert bridge.watch_active is False
