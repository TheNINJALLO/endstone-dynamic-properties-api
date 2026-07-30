from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import json
import logging
import math
from threading import Barrier

import pytest
import endstone_dynamic_properties as public_api

from endstone_dynamic_properties import (
    AccessContext, BlockLocation, Capabilities, CaptureResult, ClearCollectionOperation, CollectionRef,
    DynamicPropertyService, DynamicPropertyTarget, EventFilter, EventKind,
    ExternalMutationDecision, ImportCollectionOperation, ImportPolicy, InMemoryAdapter, InventorySection,
    MutationOrigin, RemoveManyOperation, RenameCollectionOperation, SetPropertyOperation,
    SetManyOperation, Status, Transaction, TransferCollectionOperation, TransferPropertyOperation,
    ValidationLimits, Vector3,
)


@pytest.fixture()
def setup_api():
    adapter = InMemoryAdapter()
    api = DynamicPropertyService(adapter)
    plugin = AccessContext("Test.Plugin", "tester")
    admin = AccessContext("admin", "console", True, MutationOrigin.COMMAND, "admin test")
    collection = api.access_policy.plugin_collection(plugin.plugin_id, "main")
    return api, adapter, plugin, admin, collection


def test_package_exports_only_supported_public_names():
    assert "DynamicPropertyService" in public_api.__all__
    assert "dataclass" not in public_api.__all__
    assert "field" not in public_api.__all__
    assert "Mapping" not in public_api.__all__


def test_audit_sink_exception_does_not_replace_committed_result(caplog):
    class FailingAuditSink:
        def record(self, _record):
            raise RuntimeError("audit unavailable")

    api = DynamicPropertyService(audit_sink=FailingAuditSink())
    context = AccessContext("audit-test", "tester")
    collection = api.access_policy.plugin_collection(context.plugin_id, "main")
    ref = CollectionRef(DynamicPropertyTarget.world(), collection)

    result = api.set(ref, "committed", True, context)

    assert result.ok
    assert api.get(ref, "committed", context).value is True
    assert "audit sink failed" in caplog.text


def test_failure_reporting_handlers_cannot_escape_committed_results():
    class RaisingHandler(logging.Handler):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def emit(self, _record):
            self.calls += 1
            raise RuntimeError("logging unavailable")

    class FailingAuditSink:
        def record(self, _record):
            raise RuntimeError("audit unavailable")

    service_logger = logging.getLogger("endstone_dynamic_properties.service")
    event_logger = logging.getLogger("endstone_dynamic_properties.events")
    service_handler = RaisingHandler()
    event_handler = RaisingHandler()
    service_logger.addHandler(service_handler)
    event_logger.addHandler(event_handler)
    try:
        context = AccessContext("reporting-test", "tester")

        audit_api = DynamicPropertyService(audit_sink=FailingAuditSink())
        collection = audit_api.access_policy.plugin_collection(context.plugin_id, "audit")
        audit_ref = CollectionRef(DynamicPropertyTarget.world(), collection)
        audit_result = audit_api.set(audit_ref, "committed", True, context)

        event_bus = public_api.EventBus()

        def fail_after(_event):
            raise RuntimeError("listener unavailable")

        event_bus.subscribe(EventFilter(kind=EventKind.AFTER_MUTATION), fail_after)
        event_api = DynamicPropertyService(event_bus=event_bus)
        collection = event_api.access_policy.plugin_collection(context.plugin_id, "event")
        event_ref = CollectionRef(DynamicPropertyTarget.world(), collection)
        event_result = event_api.set(event_ref, "committed", True, context)
    finally:
        service_logger.removeHandler(service_handler)
        event_logger.removeHandler(event_handler)

    assert audit_result.ok
    assert audit_api.get(audit_ref, "committed", context).value is True
    assert event_result.ok
    assert event_api.get(event_ref, "committed", context).value is True
    assert service_handler.calls == 1
    assert event_handler.calls == 1


def test_crud_all_value_types(setup_api):
    api, _, plugin, _, collection = setup_api
    ref = CollectionRef(DynamicPropertyTarget.world(), collection)
    assert api.set(ref, "flag", True, plugin).ok
    assert api.set(ref, "number", 42.5, plugin).ok
    assert api.set(ref, "text", "Kingdom", plugin).ok
    assert api.set(ref, "vector", Vector3(1, 2, 3), plugin).ok
    snapshot = api.capture(ref, plugin).snapshot
    assert snapshot and snapshot.byte_count > 0 and len(snapshot.properties) == 4
    assert api.remove(ref, "flag", plugin, require_existing=True).ok
    assert api.get(ref, "flag", plugin).status is Status.NOT_FOUND
    assert api.clear(ref, plugin).ok
    assert api.capture(ref, plugin).snapshot.properties == {}


def test_now_and_later_target_families(setup_api):
    api, _, plugin, _, collection = setup_api
    targets = (
        DynamicPropertyTarget.world(),
        DynamicPropertyTarget.online_player("xuid"),
        DynamicPropertyTarget.offline_player("xuid"),
        DynamicPropertyTarget.loaded_entity("loaded"),
        DynamicPropertyTarget.stored_entity("stored"),
        DynamicPropertyTarget.player_item("xuid", InventorySection.MAIN, 1),
        DynamicPropertyTarget.player_item("xuid", InventorySection.ARMOR, 2),
        DynamicPropertyTarget.player_item("xuid", InventorySection.OFFHAND, 0),
        DynamicPropertyTarget.player_item("xuid", InventorySection.ENDER_CHEST, 5),
        DynamicPropertyTarget.block_container_item(BlockLocation("overworld", 1, 64, 1), 3),
        DynamicPropertyTarget.dropped_item("item-entity"),
        DynamicPropertyTarget.block_entity(BlockLocation("overworld", 2, 64, 2)),
    )
    for index, target in enumerate(targets):
        ref = CollectionRef(target, collection)
        assert api.set(ref, "index", float(index), plugin).ok
        assert api.get(ref, "index", plugin).value == float(index)


def test_plugin_scope_and_admin_raw_access(setup_api):
    api, _, plugin, admin, collection = setup_api
    own = CollectionRef(DynamicPropertyTarget.world(), collection)
    raw = CollectionRef(DynamicPropertyTarget.world(), "behavior-pack-uuid")
    assert api.set(own, "a", True, plugin).ok
    assert api.set(raw, "a", True, plugin).status is Status.PERMISSION_DENIED
    assert api.set(raw, "a", True, admin).ok
    assert "behavior-pack-uuid" not in api.list_collections(raw.target, plugin).collections
    assert "behavior-pack-uuid" in api.list_collections(raw.target, admin).collections


def test_empty_plugin_identity_cannot_bypass_collection_scope(setup_api):
    api, _, _, admin, _ = setup_api
    raw = CollectionRef(DynamicPropertyTarget.world(), "behavior-pack-secret")
    assert api.set(raw, "secret", "value", admin).ok
    anonymous = AccessContext()
    assert api.capture(raw, anonymous).status is Status.PERMISSION_DENIED
    assert api.set(raw, "secret", "changed", anonymous).status is Status.PERMISSION_DENIED
    assert api.list_collections(raw.target, anonymous).status is Status.PERMISSION_DENIED


def test_revision_conflict(setup_api):
    api, _, plugin, _, collection = setup_api
    ref = CollectionRef(DynamicPropertyTarget.world(), collection)
    assert api.set(ref, "value", 1.0, plugin).ok
    revision = api.capture(ref, plugin).snapshot.revision
    assert api.set(ref, "value", 2.0, plugin, revision + 1).status is Status.CONFLICT
    assert api.get(ref, "value", plugin).value == 1.0


def test_force_requires_raw_administrative_access(setup_api):
    api, _, plugin, admin, collection = setup_api
    ref = CollectionRef(DynamicPropertyTarget.world(), collection)
    assert api.set(ref, "value", 1.0, plugin).ok
    stale_revision = api.capture(ref, plugin).snapshot.revision + 1
    operation = SetPropertyOperation(ref, "value", 2.0, stale_revision)
    assert api.apply(operation, plugin, force=True).status is Status.PERMISSION_DENIED
    assert api.apply(operation, admin, force=True).ok
    assert api.get(ref, "value", plugin).value == 2.0
    forced_transaction = Transaction((SetPropertyOperation(ref, "value", 3.0, stale_revision),), force=True)
    assert api.transact(forced_transaction, plugin).status is Status.PERMISSION_DENIED


def test_atomic_transaction_rolls_back(setup_api):
    api, _, plugin, _, collection = setup_api
    world = CollectionRef(DynamicPropertyTarget.world(), collection)
    offline = CollectionRef(DynamicPropertyTarget.offline_player("xuid"), collection)
    assert api.set(world, "season", "winter", plugin).ok
    tx = Transaction((
        SetPropertyOperation(world, "season", "spring"),
        SetPropertyOperation(offline, "season", "spring", expected_revision=1),
    ))
    result = api.transact(tx, plugin)
    assert result.status is Status.TRANSACTION_FAILED
    assert result.rolled_back
    assert api.get(world, "season", plugin).value == "winter"


def test_cross_target_atomic_transaction(setup_api):
    api, _, plugin, _, collection = setup_api
    world = CollectionRef(DynamicPropertyTarget.world(), collection)
    offline = CollectionRef(DynamicPropertyTarget.offline_player("xuid"), collection)
    result = api.transact(Transaction((
        SetPropertyOperation(world, "season", "winter"),
        SetPropertyOperation(offline, "season", "winter"),
    )), plugin)
    assert result.ok
    assert api.get(world, "season", plugin).value == "winter"
    assert api.get(offline, "season", plugin).value == "winter"


def test_transaction_uses_one_correlation_id_and_committed_after_state(setup_api):
    api, _, plugin, _, collection = setup_api
    ref = CollectionRef(DynamicPropertyTarget.world(), collection)
    observed = []
    api.event_bus.subscribe(EventFilter(EventKind.BEFORE_TRANSACTION), observed.append)
    api.event_bus.subscribe(EventFilter(EventKind.AFTER_TRANSACTION), observed.append)
    result = api.transact(
        Transaction((SetPropertyOperation(ref, "season", "winter"),), audit_reason="release test"),
        plugin,
    )
    assert result.ok
    assert [event.transaction_id for event in observed] == [result.transaction_id, result.transaction_id]
    assert observed[1].after[0].properties["season"] == "winter"
    assert api.audit_sink.records()[-1].actor.reason == "release test"


def test_transfer_property_and_collection(setup_api):
    api, _, plugin, _, collection = setup_api
    source = CollectionRef(DynamicPropertyTarget.world(), collection)
    destination = CollectionRef(DynamicPropertyTarget.offline_player("xuid"), collection)
    api.set(source, "name", "Kingdom", plugin)
    moved = api.apply(TransferPropertyOperation(source, "name", destination, "server", remove_source=True), plugin)
    assert moved.ok
    assert api.get(source, "name", plugin).status is Status.NOT_FOUND
    assert api.get(destination, "server", plugin).value == "Kingdom"
    copied_collection = CollectionRef(DynamicPropertyTarget.stored_entity("stored"), collection)
    result = api.apply(TransferCollectionOperation(destination, copied_collection,
                                                    destination_policy=ImportPolicy.REPLACE), plugin)
    assert result.ok
    assert api.get(copied_collection, "server", plugin).value == "Kingdom"


def test_rename_and_uuid_migration(setup_api):
    api, _, _, admin, _ = setup_api
    target = DynamicPropertyTarget.world()
    old = CollectionRef(target, "old-pack-uuid")
    new = CollectionRef(target, "new-pack-uuid")
    api.set(old, "legacy", "data", admin)
    assert api.migrate_collection(old, new, admin).ok
    assert not api.capture(old, admin).snapshot.exists
    assert api.get(new, "legacy", admin).value == "data"
    newer = CollectionRef(target, "newer-pack-uuid")
    assert api.apply(RenameCollectionOperation(target, new.collection, newer.collection), admin).ok
    assert api.get(newer, "legacy", admin).value == "data"


def test_rename_enforces_destination_revision(setup_api):
    api, _, plugin, _, collection = setup_api
    target = DynamicPropertyTarget.world()
    source = CollectionRef(target, collection)
    destination = CollectionRef(target, f"{collection}.renamed")
    assert api.set(source, "source", "value", plugin).ok
    assert api.set(destination, "destination", "keep-until-renamed", plugin).ok
    source_revision = api.capture(source, plugin).snapshot.revision
    destination_revision = api.capture(destination, plugin).snapshot.revision

    stale = api.apply(
        RenameCollectionOperation(
            target,
            source.collection,
            destination.collection,
            source_revision,
            ImportPolicy.REPLACE,
            destination_revision + 1,
        ),
        plugin,
    )
    assert stale.status is Status.CONFLICT
    assert api.get(source, "source", plugin).value == "value"
    assert api.get(destination, "destination", plugin).value == "keep-until-renamed"

    renamed = api.apply(
        RenameCollectionOperation(
            target,
            source.collection,
            destination.collection,
            expected_source_revision=source_revision,
            expected_destination_revision=destination_revision,
            destination_policy=ImportPolicy.REPLACE,
        ),
        plugin,
    )
    assert renamed.ok
    assert api.get(destination, "source", plugin).value == "value"


def test_migrate_collection_passes_both_revision_guards(setup_api):
    api, _, plugin, _, collection = setup_api
    target = DynamicPropertyTarget.world()
    source = CollectionRef(target, collection)
    destination = CollectionRef(target, f"{collection}.migrated")
    assert api.set(source, "source", "value", plugin).ok
    assert api.set(destination, "destination", "old", plugin).ok
    source_revision = api.capture(source, plugin).snapshot.revision
    destination_revision = api.capture(destination, plugin).snapshot.revision

    assert api.migrate_collection(
        source,
        destination,
        plugin,
        policy=ImportPolicy.REPLACE,
        remove_source=False,
        expected_source_revision=source_revision + 1,
        expected_destination_revision=destination_revision,
    ).status is Status.CONFLICT
    assert api.migrate_collection(
        source,
        destination,
        plugin,
        policy=ImportPolicy.REPLACE,
        remove_source=False,
        expected_source_revision=source_revision,
        expected_destination_revision=destination_revision + 1,
    ).status is Status.CONFLICT
    assert api.migrate_collection(
        source,
        destination,
        plugin,
        policy=ImportPolicy.REPLACE,
        remove_source=False,
        expected_source_revision=source_revision,
        expected_destination_revision=destination_revision,
    ).ok
    assert api.get(source, "source", plugin).value == "value"
    assert api.get(destination, "source", plugin).value == "value"


def test_same_collection_transfer_enforces_and_reconciles_revision_guards(setup_api):
    api, _, plugin, _, collection = setup_api
    ref = CollectionRef(DynamicPropertyTarget.world(), collection)
    assert api.set(ref, "source", "value", plugin).ok
    revision = api.capture(ref, plugin).snapshot.revision

    destination_stale = api.apply(
        TransferPropertyOperation(
            ref,
            "source",
            ref,
            "copy",
            expected_destination_revision=revision + 1,
        ),
        plugin,
    )
    assert destination_stale.status is Status.CONFLICT
    assert api.get(ref, "copy", plugin).status is Status.NOT_FOUND

    conflicting = api.apply(
        TransferPropertyOperation(
            ref,
            "source",
            ref,
            "copy",
            expected_source_revision=revision,
            expected_destination_revision=revision + 1,
        ),
        plugin,
    )
    assert conflicting.status is Status.INVALID_VALUE
    assert api.get(ref, "copy", plugin).status is Status.NOT_FOUND

    copied = api.apply(
        TransferPropertyOperation(
            ref,
            "source",
            ref,
            "copy",
            expected_source_revision=revision,
            expected_destination_revision=revision,
        ),
        plugin,
    )
    assert copied.ok
    assert api.get(ref, "copy", plugin).value == "value"


def test_self_moves_are_rejected_without_deleting_data(setup_api):
    api, _, plugin, _, collection = setup_api
    ref = CollectionRef(DynamicPropertyTarget.world(), collection)
    assert api.set(ref, "value", "keep", plugin).ok
    renamed = api.apply(
        RenameCollectionOperation(ref.target, ref.collection, ref.collection,
                                  destination_policy=ImportPolicy.REPLACE),
        plugin,
    )
    assert renamed.status is Status.INVALID_COLLECTION
    moved = api.apply(
        TransferPropertyOperation(ref, "value", ref, "value", remove_source=True, overwrite=True),
        plugin,
    )
    assert moved.status is Status.INVALID_KEY
    assert api.get(ref, "value", plugin).value == "keep"


def test_export_import_round_trip(setup_api):
    api, _, plugin, _, collection = setup_api
    source = CollectionRef(DynamicPropertyTarget.world(), collection)
    api.set_many(source, {"a": True, "b": 2.0, "c": Vector3(1, 2, 3)}, plugin)
    exported = api.export_collection(source, plugin)
    assert exported.ok
    parsed = json.loads(exported.document)
    assert parsed["schema"] == 1
    destination = CollectionRef(DynamicPropertyTarget.world("backup"), collection)
    assert api.import_collection(destination, exported.document, plugin, ImportPolicy.REPLACE).ok
    assert api.capture(destination, plugin).snapshot.properties == api.capture(source, plugin).snapshot.properties


def test_event_cancellation(setup_api):
    api, _, plugin, _, collection = setup_api
    ref = CollectionRef(DynamicPropertyTarget.world(), collection)

    def cancel(event):
        event.cancelled = True
        event.cancellation_reason = "blocked"

    sub = api.event_bus.subscribe(EventFilter(EventKind.BEFORE_MUTATION, collection=collection, key="blocked"), cancel)
    assert api.set(ref, "blocked", True, plugin).status is Status.CANCELLED
    assert api.get(ref, "blocked", plugin).status is Status.NOT_FOUND
    assert api.event_bus.unsubscribe(sub)


def test_external_observation_and_cancellation(setup_api):
    api, adapter, plugin, admin, collection = setup_api
    ref = CollectionRef(DynamicPropertyTarget.world(), collection)
    operation = SetPropertyOperation(ref, "external", True)
    gate = api.before_external_mutation(operation, admin, True)
    assert gate.decision is ExternalMutationDecision.ALLOW
    result = adapter.apply(operation)
    api.after_external_mutation(operation, result, admin, gate.transaction_id)
    assert api.get(ref, "external", plugin).value is True
    assert any(record.external for record in api.audit_sink.records())


def test_external_mutation_preserves_the_supplied_origin(setup_api):
    api, _, _, admin, collection = setup_api
    ref = CollectionRef(DynamicPropertyTarget.world(), collection)
    observed = []
    api.event_bus.subscribe(EventFilter(EventKind.BEFORE_EXTERNAL_MUTATION), observed.append)
    script_context = replace(admin, origin=MutationOrigin.SCRIPT_API)
    api.before_external_mutation(SetPropertyOperation(ref, "external", True), script_context, True)
    assert observed[0].actor.origin is MutationOrigin.SCRIPT_API


def test_external_hook_can_be_cancelled(setup_api):
    api, _, _, admin, collection = setup_api
    ref = CollectionRef(DynamicPropertyTarget.world(), collection)

    def cancel(event):
        event.cancelled = True
        event.cancellation_reason = "admin shield"

    api.event_bus.subscribe(EventFilter(EventKind.BEFORE_EXTERNAL_MUTATION, key="protected"), cancel)
    gate = api.before_external_mutation(SetPropertyOperation(ref, "protected", True), admin, True)
    assert gate.decision is ExternalMutationDecision.CANCEL
    assert gate.status is Status.CANCELLED


def test_audit_records_success_cancel_and_rollback(setup_api):
    api, _, plugin, _, collection = setup_api
    ref = CollectionRef(DynamicPropertyTarget.world(), collection)
    api.set(ref, "a", True, plugin)
    api.event_bus.subscribe(EventFilter(EventKind.BEFORE_MUTATION, key="b"),
                            lambda event: setattr(event, "cancelled", True))
    api.set(ref, "b", True, plugin)
    records = api.audit_sink.records()
    assert any(record.status is Status.APPLIED for record in records)
    assert any(record.status is Status.CANCELLED for record in records)


def test_invalid_values_and_imports(setup_api):
    api, _, plugin, _, collection = setup_api
    ref = CollectionRef(DynamicPropertyTarget.world(), collection)
    assert api.set(ref, "nan", math.nan, plugin).status is Status.INVALID_VALUE
    assert api.set(ref, "infvec", Vector3(0, math.inf, 0), plugin).status is Status.INVALID_VALUE
    assert api.set(ref, "", True, plugin).status is Status.INVALID_KEY
    assert api.import_collection(ref, "{bad", plugin).status is Status.INVALID_VALUE
    duplicate = '{"schema":1,"properties":{"a":{"type":"bool","value":true},"a":{"type":"bool","value":false}}}'
    assert api.import_collection(ref, duplicate, plugin).status is Status.INVALID_VALUE
    bool_vector = '{"schema":1,"properties":{"v":{"type":"vector3","value":[true,2,3]}}}'
    assert api.import_collection(ref, bool_vector, plugin).status is Status.INVALID_VALUE
    assert api.set(ref, "bad-unicode", "\ud800", plugin).status is Status.INVALID_VALUE


def test_import_unicode_and_numeric_overflow_return_invalid_value(setup_api):
    api, _, plugin, _, collection = setup_api
    ref = CollectionRef(DynamicPropertyTarget.world(), collection)
    assert api.import_collection(ref, "\ud800", plugin).status is Status.INVALID_VALUE
    oversized_number = json.dumps({
        "schema": 1,
        "properties": {"huge": {"type": "number", "value": 10 ** 400}},
    })
    assert api.import_collection(ref, oversized_number, plugin).status is Status.INVALID_VALUE


def test_operation_snapshots_and_audit_properties_are_defensively_immutable(setup_api):
    api, _, plugin, _, collection = setup_api
    ref = CollectionRef(DynamicPropertyTarget.world(), collection)
    source = {"safe": "original"}
    operation = SetManyOperation(ref, source)
    source["safe"] = "changed"
    source["extra"] = True
    assert dict(operation.values) == {"safe": "original"}
    assert deepcopy(operation).values == operation.values
    with pytest.raises(TypeError):
        operation.values["extra"] = True

    imported = {"imported": True}
    import_operation = ImportCollectionOperation(ref, imported)
    imported["forged"] = True
    assert dict(import_operation.properties) == {"imported": True}

    assert api.apply(operation, plugin).ok
    snapshot = api.capture(ref, plugin).snapshot
    assert snapshot is not None
    with pytest.raises(TypeError):
        snapshot.properties["safe"] = "forged"

    blocked_mutations = []

    def try_to_forge_after_state(event):
        try:
            event.after[0].properties["audited"] = "forged"
        except TypeError as exc:
            blocked_mutations.append(exc)

    api.event_bus.subscribe(EventFilter(EventKind.AFTER_MUTATION, key="audited"),
                            try_to_forge_after_state)
    result = api.set(ref, "audited", "real", plugin)
    assert result.ok and blocked_mutations
    assert result.after[0].properties["audited"] == "real"
    assert api.audit_sink.records()[-1].after[0].properties["audited"] == "real"
    assert api.get(ref, "audited", plugin).value == "real"


def test_listener_failures_are_isolated_fail_closed_before_and_preserve_audit_after(setup_api):
    api, _, plugin, _, collection = setup_api
    ref = CollectionRef(DynamicPropertyTarget.world(), collection)
    observed = []

    def fail(_event):
        raise RuntimeError("listener failed")

    api.event_bus.subscribe(EventFilter(EventKind.BEFORE_MUTATION, key="blocked"), fail)
    api.event_bus.subscribe(EventFilter(EventKind.BEFORE_MUTATION, key="blocked"), observed.append)
    blocked = api.set(ref, "blocked", True, plugin)
    assert blocked.status is Status.CANCELLED
    assert observed and api.get(ref, "blocked", plugin).status is Status.NOT_FOUND
    assert api.audit_sink.records()[-1].status is Status.CANCELLED

    api.event_bus.subscribe(EventFilter(EventKind.AFTER_MUTATION, key="committed"), fail)
    api.event_bus.subscribe(EventFilter(EventKind.AFTER_MUTATION, key="committed"), observed.append)
    committed = api.set(ref, "committed", True, plugin)
    assert committed.ok
    assert api.get(ref, "committed", plugin).value is True
    assert observed[-1].kind is EventKind.AFTER_MUTATION
    assert api.audit_sink.records()[-1].status is Status.APPLIED

    transaction_before_failure_id = api.event_bus.subscribe(
        EventFilter(EventKind.BEFORE_TRANSACTION), fail
    )
    audit_count = len(api.audit_sink.records())
    cancelled_transaction = api.transact(
        Transaction((SetPropertyOperation(ref, "cancelled-transaction", True),)), plugin
    )
    assert cancelled_transaction.status is Status.CANCELLED
    assert len(api.audit_sink.records()) == audit_count + 1
    assert api.audit_sink.records()[-1].status is Status.CANCELLED
    assert api.event_bus.unsubscribe(transaction_before_failure_id)

    api.event_bus.subscribe(EventFilter(EventKind.AFTER_TRANSACTION), fail)
    transaction = api.transact(Transaction((SetPropertyOperation(ref, "transaction", True),)), plugin)
    assert transaction.ok
    assert api.get(ref, "transaction", plugin).value is True
    assert api.audit_sink.records()[-1].status is Status.APPLIED


def test_external_validation_cannot_claim_cancellation_without_adapter_capability(setup_api):
    _, _, _, admin, collection = setup_api

    class ObserveOnlyAdapter(InMemoryAdapter):
        @property
        def capabilities(self):
            return replace(super().capabilities, external_change_cancellation=False)

    api = DynamicPropertyService(ObserveOnlyAdapter())
    ref = CollectionRef(DynamicPropertyTarget.world(), collection)
    gate = api.before_external_mutation(SetPropertyOperation(ref, "", True), admin, True)
    assert gate.decision is ExternalMutationDecision.OBSERVE_ONLY
    assert gate.status is Status.INVALID_KEY


def test_commit_validation_fails_closed_when_adapter_capture_fails(setup_api):
    _, _, _, admin, collection = setup_api

    class CaptureFailureAdapter(InMemoryAdapter):
        def capture(self, ref):
            del ref
            return CaptureResult(Status.ADAPTER_ERROR, "capture failed for test")

    api = DynamicPropertyService(CaptureFailureAdapter())
    ref = CollectionRef(DynamicPropertyTarget.world(), collection)
    result = api.set(ref, "must-not-commit", True, admin)
    assert result.status is Status.ADAPTER_ERROR


def test_reentrant_before_mutation_is_revalidated_before_outer_commit():
    api = DynamicPropertyService(limits=ValidationLimits(max_properties_per_collection=1))
    plugin = AccessContext("reentrant-limit")
    collection = api.access_policy.plugin_collection(plugin.plugin_id, "main")
    ref = CollectionRef(DynamicPropertyTarget.world(), collection)
    nested_results = []

    def add_inner(_event):
        nested_results.append(api.set(ref, "inner", True, plugin))

    api.event_bus.subscribe(EventFilter(EventKind.BEFORE_MUTATION, key="outer"), add_inner)
    outer = api.set(ref, "outer", True, plugin)
    assert nested_results[0].ok
    assert outer.status is Status.INVALID_VALUE
    assert set(api.capture(ref, plugin).snapshot.properties) == {"inner"}


def test_reentrant_before_transaction_is_revalidated_before_atomic_commit():
    api = DynamicPropertyService(limits=ValidationLimits(max_properties_per_collection=1))
    plugin = AccessContext("reentrant-transaction-limit")
    collection = api.access_policy.plugin_collection(plugin.plugin_id, "main")
    ref = CollectionRef(DynamicPropertyTarget.world(), collection)

    def add_inner(_event):
        assert api.set(ref, "inner", True, plugin).ok

    api.event_bus.subscribe(EventFilter(EventKind.BEFORE_TRANSACTION), add_inner)
    transaction = api.transact(Transaction((SetPropertyOperation(ref, "outer", True),)), plugin)
    assert transaction.status is Status.INVALID_VALUE
    assert set(api.capture(ref, plugin).snapshot.properties) == {"inner"}
    assert api.audit_sink.records()[-1].status is Status.INVALID_VALUE
    assert api.audit_sink.records()[-1].transaction_id == transaction.transaction_id


def test_concurrent_mutations_serialize_limit_validation_and_commit():
    api = DynamicPropertyService(limits=ValidationLimits(max_properties_per_collection=1))
    plugin = AccessContext("concurrent-limit")
    collection = api.access_policy.plugin_collection(plugin.plugin_id, "main")
    ref = CollectionRef(DynamicPropertyTarget.world(), collection)
    ready = Barrier(2)

    def align_before_callbacks(_event):
        ready.wait(timeout=5)

    api.event_bus.subscribe(EventFilter(EventKind.BEFORE_MUTATION), align_before_callbacks)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(api.set, ref, key, True, plugin) for key in ("one", "two")]
    results = [future.result() for future in futures]
    assert sum(result.ok for result in results) == 1
    assert {result.status for result in results} == {Status.APPLIED, Status.INVALID_VALUE}
    assert len(api.capture(ref, plugin).snapshot.properties) == 1


def test_inventory_section_must_match_target_kind(setup_api):
    api, _, plugin, _, collection = setup_api
    invalid = DynamicPropertyTarget.player_item("xuid", InventorySection.NONE, 0)
    result = api.set(CollectionRef(invalid, collection), "value", True, plugin)
    assert result.status is Status.INVALID_TARGET


def test_python_service_enforces_adapter_capabilities(setup_api):
    _, _, plugin, _, collection = setup_api

    class ReadOnlyAdapter(InMemoryAdapter):
        @property
        def capabilities(self):
            return replace(super().capabilities, write=False, block_entities=False)

    api = DynamicPropertyService(ReadOnlyAdapter())
    world = CollectionRef(DynamicPropertyTarget.world(), collection)
    block = CollectionRef(
        DynamicPropertyTarget.block_entity(BlockLocation("overworld", 0, 64, 0)), collection
    )
    assert api.set(world, "value", True, plugin).status is Status.UNSUPPORTED
    assert api.capture(block, plugin).status is Status.UNSUPPORTED


def test_remove_many_require_all(setup_api):
    api, _, plugin, _, collection = setup_api
    ref = CollectionRef(DynamicPropertyTarget.world(), collection)
    api.set_many(ref, {"a": True, "b": True}, plugin)
    result = api.apply(RemoveManyOperation(ref, ("a", "missing"), require_all_existing=True), plugin)
    assert result.status is Status.NOT_FOUND
    assert api.get(ref, "a", plugin).value is True


def test_property_limit_applies_to_resulting_state_and_transactions():
    api = DynamicPropertyService(limits=ValidationLimits(max_properties_per_collection=1))
    plugin = AccessContext("limit-test")
    collection = api.access_policy.plugin_collection(plugin.plugin_id, "main")
    world = CollectionRef(DynamicPropertyTarget.world(), collection)
    offline = CollectionRef(DynamicPropertyTarget.offline_player("xuid"), collection)
    assert api.set(world, "first", True, plugin).ok
    assert api.set(world, "second", True, plugin).status is Status.INVALID_VALUE
    assert set(api.capture(world, plugin).snapshot.properties) == {"first"}

    transaction = Transaction((
        SetPropertyOperation(offline, "first", True),
        SetPropertyOperation(offline, "second", True),
    ))
    assert api.transact(transaction, plugin).status is Status.INVALID_VALUE
    assert not api.capture(offline, plugin).snapshot.exists


def test_clear_removes_collection(setup_api):
    api, _, plugin, _, collection = setup_api
    ref = CollectionRef(DynamicPropertyTarget.world(), collection)
    api.set(ref, "a", True, plugin)
    assert api.apply(ClearCollectionOperation(ref, remove_collection=True), plugin).ok
    snapshot = api.capture(ref, plugin).snapshot
    assert snapshot and not snapshot.exists


def test_target_unavailable(setup_api):
    api, adapter, plugin, _, collection = setup_api
    target = DynamicPropertyTarget.offline_player("missing")
    adapter.set_target_available(target, False)
    assert api.capture(CollectionRef(target, collection), plugin).status is Status.TARGET_UNAVAILABLE
    assert api.flush(target, plugin).status is Status.TARGET_UNAVAILABLE


def test_capabilities_include_advanced_scope_but_native_gate_is_closed(setup_api):
    api, _, _, _, _ = setup_api
    caps = api.capabilities
    assert caps.offline_players and caps.stored_entities and caps.block_dynamic_properties
    assert caps.external_change_observation and caps.external_change_cancellation
    assert caps.atomic_transactions and caps.rollback and caps.collection_migration
    assert not caps.exact_build_match
    assert not caps.complete_control


def test_flush_all_target_families(setup_api):
    api, _, plugin, _, _ = setup_api
    assert api.flush(DynamicPropertyTarget.world(), plugin).ok
    assert api.flush(DynamicPropertyTarget.offline_player("xuid"), plugin).ok
    assert api.flush(DynamicPropertyTarget.stored_entity("stored"), plugin).ok


def test_collection_listing_is_sorted(setup_api):
    api, _, plugin, _, _ = setup_api
    target = DynamicPropertyTarget.world()
    for logical in ("z", "a", "m"):
        ref = CollectionRef(target, api.access_policy.plugin_collection(plugin.plugin_id, logical))
        api.set(ref, "value", True, plugin)
    names = api.list_collections(target, plugin).collections
    assert names == tuple(sorted(names))
