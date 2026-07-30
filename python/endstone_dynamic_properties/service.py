from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import hashlib
import itertools
import json
import logging
import math
import re
from threading import Lock, RLock
from typing import Iterable, Iterator, Mapping

from .audit import AuditRecord, AuditSink, VectorAuditSink
from .events import Event, EventBus, EventFilter, EventKind
from .model import *


_TRANSACTION_IDS = itertools.count(1)
_LOGGER = logging.getLogger(__name__)
_REFERENCE_NATIVE_GATES = {
    "exact_build_match": False,
    "exact_binary_hash_match": False,
    "symbols_validated": False,
    "stage_probe_passed": False,
}


def _transaction_id(prefix: str = "dptx") -> str:
    return f"{prefix}-{next(_TRANSACTION_IDS)}"


def _value_type(value: DynamicPropertyValue) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, float) and not isinstance(value, bool):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, Vector3):
        return "vector3"
    raise TypeError(f"unsupported dynamic-property type: {type(value).__name__}")


def _validate_value(value: DynamicPropertyValue, limits: ValidationLimits) -> str | None:
    try:
        type_name = _value_type(value)
    except TypeError as exc:
        return str(exc)
    if type_name == "number" and not math.isfinite(value):
        return "numbers must be finite"
    if type_name == "string":
        try:
            encoded = value.encode("utf-8")
        except UnicodeError:
            return "string must be valid UTF-8"
        if len(encoded) > limits.max_string_bytes:
            return "string exceeds byte limit"
    if type_name == "vector3" and not all(math.isfinite(v) for v in (value.x, value.y, value.z)):
        return "vector coordinates must be finite"
    return None


def _validate_key(key: str, limits: ValidationLimits) -> str | None:
    if not isinstance(key, str):
        return "property key must be a string"
    if not key:
        return "property key must not be empty"
    if "\x00" in key:
        return "property key contains NUL"
    try:
        encoded = key.encode("utf-8")
    except UnicodeError:
        return "property key must be valid UTF-8"
    if len(encoded) > limits.max_key_bytes:
        return "property key exceeds byte limit"
    return None


def _validate_collection(name: str, limits: ValidationLimits) -> str | None:
    if not isinstance(name, str):
        return "collection name must be a string"
    if not name:
        return "collection name must not be empty"
    if "\x00" in name:
        return "collection name contains NUL"
    try:
        encoded = name.encode("utf-8")
    except UnicodeError:
        return "collection name must be valid UTF-8"
    if len(encoded) > limits.max_collection_bytes:
        return "collection name exceeds byte limit"
    return None


def _estimate_bytes(key: str, value: DynamicPropertyValue) -> int:
    base = len(key.encode("utf-8")) + 8
    if isinstance(value, bool):
        return base + 1
    if isinstance(value, float):
        return base + 8
    if isinstance(value, str):
        return base + len(value.encode("utf-8"))
    return base + 24


def _encoded_value(value: DynamicPropertyValue) -> dict[str, object]:
    type_name = _value_type(value)
    if type_name == "vector3":
        encoded: object = [value.x, value.y, value.z]
    else:
        encoded = value
    return {"type": type_name, "value": encoded}


def _decoded_value(data: object) -> DynamicPropertyValue:
    if not isinstance(data, dict) or set(data) != {"type", "value"}:
        raise ValueError("property entry must contain only type and value")
    type_name = data["type"]
    value = data["value"]
    if type_name == "bool" and isinstance(value, bool):
        return value
    if type_name == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("number must be finite")
        return number
    if type_name == "string" and isinstance(value, str):
        return value
    if type_name == "vector3" and isinstance(value, list) and len(value) == 3:
        if not all(isinstance(component, (int, float)) and not isinstance(component, bool)
                   for component in value):
            raise ValueError("vector coordinates must be numbers")
        coordinates = [float(component) for component in value]
        if not all(math.isfinite(component) for component in coordinates):
            raise ValueError("vector coordinates must be finite")
        return Vector3(*coordinates)
    raise ValueError(f"invalid {type_name!r} property value")


def _object_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object key: {key}")
        result[key] = value
    return result


def describe_target(target: DynamicPropertyTarget) -> str:
    parts = [target.kind.value, target.world_id]
    if target.xuid:
        parts.append(f"xuid={target.xuid}")
    if target.entity_id:
        parts.append(f"entity={target.entity_id}")
    if target.item_entity_id:
        parts.append(f"item={target.item_entity_id}")
    if target.block:
        parts.append(f"{target.block.dimension}@{target.block.x},{target.block.y},{target.block.z}")
    if target.slot >= 0:
        parts.append(f"slot={target.slot}")
    return ":".join(parts)


def _snapshot(ref: CollectionRef, properties: dict[str, DynamicPropertyValue] | None,
              *, exists: bool = True) -> CollectionSnapshot:
    values = dict(properties or {})
    byte_count = sum(_estimate_bytes(key, value) for key, value in values.items())
    canonical = {
        "target": describe_target(ref.target),
        "collection": ref.collection,
        "exists": exists,
        "properties": {key: _encoded_value(value) for key, value in sorted(values.items())},
    }
    revision = int.from_bytes(
        hashlib.blake2b(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode(),
                        digest_size=8).digest(), "big"
    )
    return CollectionSnapshot(ref, values, byte_count, revision, exists, True, True, True)


def operation_name(operation: Operation) -> str:
    names = {
        SetPropertyOperation: "set_property",
        SetManyOperation: "set_many",
        RemovePropertyOperation: "remove_property",
        RemoveManyOperation: "remove_many",
        ClearCollectionOperation: "clear_collection",
        RenameCollectionOperation: "rename_collection",
        TransferPropertyOperation: "transfer_property",
        TransferCollectionOperation: "transfer_collection",
        ImportCollectionOperation: "import_collection",
    }
    return names[type(operation)]


def operation_refs(operation: Operation) -> tuple[CollectionRef, ...]:
    if isinstance(operation, RenameCollectionOperation):
        return (CollectionRef(operation.target, operation.source),
                CollectionRef(operation.target, operation.destination))
    if isinstance(operation, (TransferPropertyOperation, TransferCollectionOperation)):
        return (operation.source, operation.destination)
    if isinstance(operation, ImportCollectionOperation):
        return (operation.destination,)
    return (operation.ref,)


def operation_key(operation: Operation) -> str | None:
    if isinstance(operation, (SetPropertyOperation, RemovePropertyOperation)):
        return operation.key
    if isinstance(operation, TransferPropertyOperation):
        return operation.destination_key
    return None


def _expected_revision(operation: Operation, ref: CollectionRef) -> int | None:
    if isinstance(operation, (SetPropertyOperation, SetManyOperation, RemovePropertyOperation,
                              RemoveManyOperation, ClearCollectionOperation)):
        return operation.expected_revision if operation.ref == ref else None
    if isinstance(operation, RenameCollectionOperation):
        source = CollectionRef(operation.target, operation.source)
        destination = CollectionRef(operation.target, operation.destination)
        if ref == source:
            return operation.expected_source_revision
        if ref == destination:
            return operation.expected_destination_revision
    if isinstance(operation, (TransferPropertyOperation, TransferCollectionOperation)):
        if (isinstance(operation, TransferPropertyOperation)
                and operation.source == operation.destination
                and ref == operation.source):
            return (operation.expected_source_revision
                    if operation.expected_source_revision is not None
                    else operation.expected_destination_revision)
        if ref == operation.source:
            return operation.expected_source_revision
        if ref == operation.destination:
            return operation.expected_destination_revision
    if isinstance(operation, ImportCollectionOperation) and ref == operation.destination:
        return operation.expected_destination_revision
    return None


def validate_target(target: DynamicPropertyTarget) -> str | None:
    if not isinstance(target.kind, TargetKind):
        return "unknown target kind"
    if not target.world_id:
        return "world id must not be empty"
    if target.kind in (TargetKind.ONLINE_PLAYER, TargetKind.OFFLINE_PLAYER) and not target.xuid:
        return "player target requires an XUID"
    if target.kind in (TargetKind.LOADED_ENTITY, TargetKind.STORED_ENTITY) and not target.entity_id:
        return "entity target requires an entity identifier"
    item_sections = {
        TargetKind.PLAYER_INVENTORY_SLOT: InventorySection.MAIN,
        TargetKind.PLAYER_ARMOR_SLOT: InventorySection.ARMOR,
        TargetKind.PLAYER_OFFHAND_SLOT: InventorySection.OFFHAND,
        TargetKind.PLAYER_ENDER_CHEST_SLOT: InventorySection.ENDER_CHEST,
    }
    if target.kind in item_sections:
        if not target.xuid or target.slot < 0 or target.section is not item_sections[target.kind]:
            return "player item target requires an XUID, non-negative slot, and matching inventory section"
    if target.kind is TargetKind.BLOCK_CONTAINER_SLOT and (
        target.block is None or target.slot < 0 or target.section is not InventorySection.BLOCK_CONTAINER
    ):
        return "block-container target requires a block location, non-negative slot, and block-container section"
    if target.kind is TargetKind.DROPPED_ITEM and not target.item_entity_id:
        return "dropped-item target requires an entity identifier"
    if target.kind is TargetKind.BLOCK_ENTITY and target.block is None:
        return "block-entity target requires a block location"
    return None


class AccessPolicy:
    def __init__(self, prefix: str = "endstone-plugin") -> None:
        self.prefix = self._normalize(prefix) or "endstone-plugin"

    @staticmethod
    def _normalize(value: str) -> str:
        normalized = re.sub(r"[^a-z0-9._-]", "_", value.lower()).strip("_")
        return normalized

    def plugin_prefix(self, plugin_id: str) -> str:
        normalized = self._normalize(plugin_id)
        return f"{self.prefix}:{normalized}:" if normalized else ""

    def plugin_collection(self, plugin_id: str, logical_collection: str = "default") -> str:
        prefix = self.plugin_prefix(plugin_id)
        logical = self._normalize(logical_collection)
        return f"{prefix}{logical}" if prefix and logical else ""

    def can_access(self, context: AccessContext, ref: CollectionRef) -> bool:
        if context.raw_admin:
            return True
        prefix = self.plugin_prefix(context.plugin_id)
        return bool(prefix) and ref.collection.startswith(prefix)


class InMemoryAdapter:
    """Complete reference backend for every live, offline, stored, item and block target."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._store: dict[CollectionRef, dict[str, DynamicPropertyValue]] = {}
        self._availability: dict[DynamicPropertyTarget, bool] = {}

    @property
    def name(self) -> str:
        return "in-memory-complete-reference"

    @property
    def capabilities(self) -> Capabilities:
        values = {name: True for name in Capabilities.__dataclass_fields__}
        values.update(_REFERENCE_NATIVE_GATES)
        return Capabilities(**values)

    def set_target_available(self, target: DynamicPropertyTarget, available: bool) -> None:
        with self._lock:
            self._availability[target] = available

    @contextmanager
    def mutation_guard(self) -> Iterator[None]:
        """Hold the adapter mutation boundary across service preflight and commit."""
        with self._lock:
            yield

    def _available(self, target: DynamicPropertyTarget) -> bool:
        return self._availability.get(target, True)

    def _capture(self, store: dict[CollectionRef, dict[str, DynamicPropertyValue]], ref: CollectionRef) -> CaptureResult:
        if not self._available(ref.target):
            return CaptureResult(Status.TARGET_UNAVAILABLE, "target is unavailable")
        if ref not in store:
            return CaptureResult(Status.CAPTURED, "collection does not exist", _snapshot(ref, {}, exists=False))
        return CaptureResult(Status.CAPTURED, "captured", _snapshot(ref, store[ref]))

    def capture(self, ref: CollectionRef) -> CaptureResult:
        with self._lock:
            return self._capture(self._store, ref)

    def list_collections(self, target: DynamicPropertyTarget) -> ListCollectionsResult:
        with self._lock:
            if not self._available(target):
                return ListCollectionsResult(Status.TARGET_UNAVAILABLE, "target is unavailable")
            return ListCollectionsResult(Status.CAPTURED, "captured",
                                         tuple(sorted(ref.collection for ref in self._store if ref.target == target)))

    def _apply(self, store: dict[CollectionRef, dict[str, DynamicPropertyValue]],
               operation: Operation, force: bool) -> OperationResult:
        refs = tuple(dict.fromkeys(operation_refs(operation)))
        before: list[CollectionSnapshot] = []
        for ref in refs:
            captured = self._capture(store, ref)
            if not captured.ok or captured.snapshot is None:
                return OperationResult(captured.status, captured.message, tuple(before))
            before.append(captured.snapshot)
            expected = _expected_revision(operation, ref)
            if expected is not None and not force and expected != captured.snapshot.revision:
                return OperationResult(Status.CONFLICT, "collection revision changed", tuple(before))

        def fail(status: Status, message: str) -> OperationResult:
            return OperationResult(status, message, tuple(before))

        if isinstance(operation, SetPropertyOperation):
            store.setdefault(operation.ref, {})[operation.key] = deepcopy(operation.value)
        elif isinstance(operation, SetManyOperation):
            store.setdefault(operation.ref, {}).update(deepcopy(dict(operation.values)))
        elif isinstance(operation, RemovePropertyOperation):
            values = store.get(operation.ref)
            if values is None or operation.key not in values:
                if operation.require_existing:
                    return fail(Status.NOT_FOUND, "property does not exist")
            else:
                values.pop(operation.key)
        elif isinstance(operation, RemoveManyOperation):
            values = store.get(operation.ref)
            if operation.require_all_existing and any(values is None or key not in values for key in operation.keys):
                return fail(Status.NOT_FOUND, "one or more properties do not exist")
            if values is not None:
                for key in operation.keys:
                    values.pop(key, None)
        elif isinstance(operation, ClearCollectionOperation):
            if operation.remove_collection:
                store.pop(operation.ref, None)
            else:
                store[operation.ref] = {}
        elif isinstance(operation, RenameCollectionOperation):
            source = CollectionRef(operation.target, operation.source)
            destination = CollectionRef(operation.target, operation.destination)
            if source not in store:
                return fail(Status.NOT_FOUND, "source collection does not exist")
            if operation.destination_policy is ImportPolicy.FAIL_IF_DESTINATION_EXISTS and destination in store:
                return fail(Status.CONFLICT, "destination collection already exists")
            source_values = deepcopy(store[source])
            if operation.destination_policy is ImportPolicy.MERGE and destination in store:
                merged = deepcopy(store[destination]); merged.update(source_values); store[destination] = merged
            else:
                store[destination] = source_values
            store.pop(source, None)
        elif isinstance(operation, TransferPropertyOperation):
            source_values = store.get(operation.source)
            if source_values is None or operation.source_key not in source_values:
                return fail(Status.NOT_FOUND, "source property does not exist")
            destination_values = store.setdefault(operation.destination, {})
            if operation.destination_key in destination_values and not operation.overwrite:
                return fail(Status.CONFLICT, "destination property already exists")
            destination_values[operation.destination_key] = deepcopy(source_values[operation.source_key])
            if operation.remove_source:
                source_values.pop(operation.source_key, None)
        elif isinstance(operation, TransferCollectionOperation):
            if operation.source not in store:
                return fail(Status.NOT_FOUND, "source collection does not exist")
            if operation.destination_policy is ImportPolicy.FAIL_IF_DESTINATION_EXISTS and operation.destination in store:
                return fail(Status.CONFLICT, "destination collection already exists")
            source_values = deepcopy(store[operation.source])
            if operation.destination_policy is ImportPolicy.MERGE and operation.destination in store:
                merged = deepcopy(store[operation.destination]); merged.update(source_values); store[operation.destination] = merged
            else:
                store[operation.destination] = source_values
            if operation.remove_source and operation.source != operation.destination:
                store.pop(operation.source, None)
        elif isinstance(operation, ImportCollectionOperation):
            if operation.policy is ImportPolicy.FAIL_IF_DESTINATION_EXISTS and operation.destination in store:
                return fail(Status.CONFLICT, "destination collection already exists")
            if operation.policy is ImportPolicy.MERGE and operation.destination in store:
                merged = deepcopy(store[operation.destination]); merged.update(deepcopy(dict(operation.properties)))
                store[operation.destination] = merged
            else:
                store[operation.destination] = deepcopy(dict(operation.properties))
        else:
            return fail(Status.UNSUPPORTED, "unknown operation")

        after = tuple(self._capture(store, ref).snapshot for ref in refs)
        after = tuple(snapshot for snapshot in after if snapshot is not None)
        return OperationResult(Status.APPLIED, "applied", tuple(before), after,
                               after[-1].revision if after else 0)

    def apply(self, operation: Operation, force: bool = False) -> OperationResult:
        with self._lock:
            return self._apply(self._store, operation, force)

    def transact(self, transaction: Transaction) -> TransactionResult:
        with self._lock:
            candidate = deepcopy(self._store)
            results: list[OperationResult] = []
            for operation in transaction.operations:
                result = self._apply(candidate, operation, transaction.force)
                results.append(result)
                if not result.ok:
                    return TransactionResult(Status.TRANSACTION_FAILED, result.message, tuple(results),
                                             transaction.rollback_on_failure, _transaction_id("memtx"))
            self._store = candidate
            return TransactionResult(Status.APPLIED, "transaction applied atomically", tuple(results),
                                     False, _transaction_id("memtx"))

    def flush(self, target: DynamicPropertyTarget) -> OperationResult:
        with self._lock:
            if not self._available(target):
                return OperationResult(Status.TARGET_UNAVAILABLE, "target is unavailable")
            return OperationResult(Status.APPLIED, "persistence flush completed")


class DynamicPropertyService:
    def __init__(self, adapter: InMemoryAdapter | None = None, *, limits: ValidationLimits | None = None,
                 event_bus: EventBus | None = None, audit_sink: AuditSink | None = None,
                 access_policy: AccessPolicy | None = None) -> None:
        self.adapter = adapter or InMemoryAdapter()
        self.limits = limits or ValidationLimits()
        self.event_bus = event_bus or EventBus()
        self.audit_sink = audit_sink or VectorAuditSink()
        self.access_policy = access_policy or AccessPolicy()
        self._mutation_lock = Lock()

    @property
    def capabilities(self) -> Capabilities:
        return replace(self.adapter.capabilities, audit=True, watches=True)

    @property
    def adapter_name(self) -> str:
        return self.adapter.name

    def _target_capable(self, target: DynamicPropertyTarget) -> bool:
        mapping = {
            TargetKind.WORLD: "world",
            TargetKind.ONLINE_PLAYER: "online_players",
            TargetKind.OFFLINE_PLAYER: "offline_players",
            TargetKind.LOADED_ENTITY: "loaded_entities",
            TargetKind.STORED_ENTITY: "stored_entities",
            TargetKind.PLAYER_INVENTORY_SLOT: "player_inventory_items",
            TargetKind.PLAYER_ARMOR_SLOT: "player_armor_items",
            TargetKind.PLAYER_OFFHAND_SLOT: "player_offhand_items",
            TargetKind.PLAYER_ENDER_CHEST_SLOT: "player_ender_chest_items",
            TargetKind.BLOCK_CONTAINER_SLOT: "block_container_items",
            TargetKind.DROPPED_ITEM: "dropped_items",
            TargetKind.BLOCK_ENTITY: "block_entities",
        }
        capable = bool(getattr(self.capabilities, mapping[target.kind]))
        if target.kind is TargetKind.BLOCK_ENTITY:
            capable = capable and self.capabilities.block_dynamic_properties
        return capable

    def _validate_ref(self, ref: CollectionRef, context: AccessContext) -> OperationResult | None:
        if error := validate_target(ref.target):
            return OperationResult(Status.INVALID_TARGET, error)
        if not self._target_capable(ref.target):
            return OperationResult(Status.UNSUPPORTED, f"target kind {ref.target.kind.value} is unsupported")
        if error := _validate_collection(ref.collection, self.limits):
            return OperationResult(Status.INVALID_COLLECTION, error)
        if not self.access_policy.can_access(context, ref):
            return OperationResult(Status.PERMISSION_DENIED, f"collection access denied: {ref.collection}")
        return None

    def capture(self, ref: CollectionRef, context: AccessContext) -> CaptureResult:
        if error := self._validate_ref(ref, context):
            return CaptureResult(error.status, error.message)
        if not self.capabilities.read:
            return CaptureResult(Status.UNSUPPORTED, "adapter does not support reads")
        return self.adapter.capture(ref)

    def get(self, ref: CollectionRef, key: str, context: AccessContext) -> PropertyReadResult:
        if error := _validate_key(key, self.limits):
            return PropertyReadResult(Status.INVALID_KEY, error)
        captured = self.capture(ref, context)
        if not captured.ok or captured.snapshot is None:
            return PropertyReadResult(captured.status, captured.message)
        if key not in captured.snapshot.properties:
            return PropertyReadResult(Status.NOT_FOUND, "property does not exist",
                                      collection_revision=captured.snapshot.revision)
        return PropertyReadResult(Status.CAPTURED, "captured", deepcopy(captured.snapshot.properties[key]),
                                  captured.snapshot.revision)

    def list_collections(self, target: DynamicPropertyTarget, context: AccessContext) -> ListCollectionsResult:
        if error := validate_target(target):
            return ListCollectionsResult(Status.INVALID_TARGET, error)
        if not self._target_capable(target):
            return ListCollectionsResult(Status.UNSUPPORTED, "target kind is unsupported")
        result = self.adapter.list_collections(target)
        if not result.ok or context.raw_admin:
            return result
        prefix = self.access_policy.plugin_prefix(context.plugin_id)
        if not prefix:
            return ListCollectionsResult(Status.PERMISSION_DENIED, "plugin identity is required")
        return replace(result, collections=tuple(name for name in result.collections if name.startswith(prefix)))

    def _validate_operation(self, operation: Operation, context: AccessContext) -> OperationResult | None:
        for ref in operation_refs(operation):
            if error := self._validate_ref(ref, context):
                return error

        def validate_entry(key: str, value: DynamicPropertyValue | None = None) -> OperationResult | None:
            if error := _validate_key(key, self.limits):
                return OperationResult(Status.INVALID_KEY, error)
            if value is not None and (error := _validate_value(value, self.limits)):
                return OperationResult(Status.INVALID_VALUE, error)
            return None

        capabilities = self.capabilities
        if isinstance(operation, SetPropertyOperation):
            if not capabilities.write:
                return OperationResult(Status.UNSUPPORTED, "adapter does not support writes")
            return validate_entry(operation.key, operation.value)
        if isinstance(operation, SetManyOperation):
            if not capabilities.bulk_set:
                return OperationResult(Status.UNSUPPORTED, "adapter does not support bulk writes")
            if len(operation.values) > self.limits.max_properties_per_collection:
                return OperationResult(Status.INVALID_VALUE, "bulk write exceeds property-count limit")
            for key, value in operation.values.items():
                if error := validate_entry(key, value): return error
        elif isinstance(operation, RemovePropertyOperation):
            if not capabilities.remove:
                return OperationResult(Status.UNSUPPORTED, "adapter does not support removals")
            return validate_entry(operation.key)
        elif isinstance(operation, RemoveManyOperation):
            if not capabilities.remove:
                return OperationResult(Status.UNSUPPORTED, "adapter does not support removals")
            if len(operation.keys) > self.limits.max_properties_per_collection:
                return OperationResult(Status.INVALID_VALUE, "bulk removal exceeds property-count limit")
            for key in operation.keys:
                if error := validate_entry(key): return error
        elif isinstance(operation, ClearCollectionOperation):
            if not capabilities.clear:
                return OperationResult(Status.UNSUPPORTED, "adapter does not support collection clearing")
        elif isinstance(operation, RenameCollectionOperation):
            if not capabilities.collection_rename:
                return OperationResult(Status.UNSUPPORTED, "adapter does not support collection renaming")
            if operation.source == operation.destination:
                return OperationResult(Status.INVALID_COLLECTION, "source and destination collections must differ")
        elif isinstance(operation, TransferPropertyOperation):
            if not capabilities.property_copy_move:
                return OperationResult(Status.UNSUPPORTED, "adapter does not support property transfer")
            if error := validate_entry(operation.source_key): return error
            if error := validate_entry(operation.destination_key): return error
            if (operation.source == operation.destination
                    and operation.expected_source_revision is not None
                    and operation.expected_destination_revision is not None
                    and operation.expected_source_revision != operation.expected_destination_revision):
                return OperationResult(
                    Status.INVALID_VALUE,
                    "source and destination revisions must match for a same-collection transfer",
                )
            if (operation.remove_source and operation.source == operation.destination
                    and operation.source_key == operation.destination_key):
                return OperationResult(Status.INVALID_KEY, "source and destination properties must differ for a move")
        elif isinstance(operation, TransferCollectionOperation):
            if not capabilities.collection_copy_move:
                return OperationResult(Status.UNSUPPORTED, "adapter does not support collection transfer")
            if operation.remove_source and operation.source == operation.destination:
                return OperationResult(Status.INVALID_COLLECTION, "source and destination collections must differ for a move")
        elif isinstance(operation, ImportCollectionOperation):
            if not capabilities.export_import:
                return OperationResult(Status.UNSUPPORTED, "adapter does not support import")
            if len(operation.properties) > self.limits.max_properties_per_collection:
                return OperationResult(Status.INVALID_VALUE, "import exceeds property-count limit")
            for key, value in operation.properties.items():
                if error := validate_entry(key, value): return error
        return None

    def _validate_property_limits(self, operations: Iterable[Operation]) -> OperationResult | None:
        operation_list = tuple(operations)
        refs = tuple(dict.fromkeys(
            ref for operation in operation_list for ref in operation_refs(operation)
        ))
        keys: dict[CollectionRef, set[str]] = {}
        exists: dict[CollectionRef, bool] = {}
        for ref in refs:
            captured = self.adapter.capture(ref)
            if captured.snapshot is None:
                status = captured.status if captured.status is not Status.CAPTURED else Status.ADAPTER_ERROR
                return OperationResult(
                    status,
                    captured.message or "adapter capture failed during commit validation",
                )
            keys[ref] = set(captured.snapshot.properties)
            exists[ref] = captured.snapshot.exists

        def stop_for_failed_precondition() -> OperationResult | None:
            return None

        for operation in operation_list:
            if isinstance(operation, SetPropertyOperation):
                keys[operation.ref].add(operation.key)
                exists[operation.ref] = True
            elif isinstance(operation, SetManyOperation):
                keys[operation.ref].update(operation.values)
                exists[operation.ref] = True
            elif isinstance(operation, RemovePropertyOperation):
                if operation.require_existing and operation.key not in keys[operation.ref]:
                    return stop_for_failed_precondition()
                keys[operation.ref].discard(operation.key)
            elif isinstance(operation, RemoveManyOperation):
                if operation.require_all_existing and not set(operation.keys).issubset(keys[operation.ref]):
                    return stop_for_failed_precondition()
                keys[operation.ref].difference_update(operation.keys)
            elif isinstance(operation, ClearCollectionOperation):
                keys[operation.ref].clear()
                exists[operation.ref] = not operation.remove_collection
            elif isinstance(operation, RenameCollectionOperation):
                source = CollectionRef(operation.target, operation.source)
                destination = CollectionRef(operation.target, operation.destination)
                if not exists[source]:
                    return stop_for_failed_precondition()
                if (operation.destination_policy is ImportPolicy.FAIL_IF_DESTINATION_EXISTS
                        and exists[destination]):
                    return stop_for_failed_precondition()
                destination_keys = (
                    keys[destination] | keys[source]
                    if operation.destination_policy is ImportPolicy.MERGE and exists[destination]
                    else set(keys[source])
                )
                keys[destination] = destination_keys
                exists[destination] = True
                keys[source].clear()
                exists[source] = False
            elif isinstance(operation, TransferPropertyOperation):
                if operation.source_key not in keys[operation.source]:
                    return stop_for_failed_precondition()
                if (operation.destination_key in keys[operation.destination]
                        and not operation.overwrite):
                    return stop_for_failed_precondition()
                keys[operation.destination].add(operation.destination_key)
                exists[operation.destination] = True
                if operation.remove_source:
                    keys[operation.source].discard(operation.source_key)
            elif isinstance(operation, TransferCollectionOperation):
                if not exists[operation.source]:
                    return stop_for_failed_precondition()
                if (operation.destination_policy is ImportPolicy.FAIL_IF_DESTINATION_EXISTS
                        and exists[operation.destination]):
                    return stop_for_failed_precondition()
                destination_keys = (
                    keys[operation.destination] | keys[operation.source]
                    if operation.destination_policy is ImportPolicy.MERGE and exists[operation.destination]
                    else set(keys[operation.source])
                )
                keys[operation.destination] = destination_keys
                exists[operation.destination] = True
                if operation.remove_source:
                    keys[operation.source].clear()
                    exists[operation.source] = False
            elif isinstance(operation, ImportCollectionOperation):
                if (operation.policy is ImportPolicy.FAIL_IF_DESTINATION_EXISTS
                        and exists[operation.destination]):
                    return stop_for_failed_precondition()
                keys[operation.destination] = (
                    keys[operation.destination] | set(operation.properties)
                    if operation.policy is ImportPolicy.MERGE and exists[operation.destination]
                    else set(operation.properties)
                )
                exists[operation.destination] = True

            if any(len(collection_keys) > self.limits.max_properties_per_collection
                   for collection_keys in keys.values()):
                return OperationResult(
                    Status.INVALID_VALUE,
                    "resulting collection exceeds property-count limit",
                )
        return None

    def _before(self, kind: EventKind, operation: Operation, context: AccessContext,
                transaction_id: str, cancellable: bool) -> Event:
        before = tuple(result.snapshot for ref in operation_refs(operation)
                       if (result := self.adapter.capture(ref)).snapshot is not None)
        event = Event(kind, transaction_id, operation_name(operation), context, operation_refs(operation),
                      operation_key(operation), before, (), cancellable)
        failures = self.event_bus.publish(event)
        if failures and cancellable and not event.cancelled:
            event.cancelled = True
            event.cancellation_reason = "event listener failed"
        return event

    def _after(self, kind: EventKind, operation: Operation, context: AccessContext,
               result: OperationResult, transaction_id: str) -> None:
        event = Event(kind, transaction_id, operation_name(operation), context, operation_refs(operation),
                      operation_key(operation), result.before, result.after)
        self.event_bus.publish(event)
        if result.ok and isinstance(operation, TransferCollectionOperation) and operation.remove_source:
            self.event_bus.publish(replace(event, kind=EventKind.COLLECTION_MIGRATED))

    def _audit(self, operation: Operation, context: AccessContext, result: OperationResult,
               transaction_id: str, *, external: bool = False, rolled_back: bool = False) -> None:
        try:
            self.audit_sink.record(AuditRecord(transaction_id, operation_name(operation), context,
                                               result.status, result.message, result.before, result.after,
                                               external, rolled_back))
        except Exception:
            try:
                _LOGGER.exception(
                    "dynamic-property audit sink failed for transaction %s operation %s",
                    transaction_id,
                    operation_name(operation),
                )
            except Exception:
                # Failure reporting itself is an untrusted extension boundary.
                pass

    def apply(self, operation: Operation, context: AccessContext, *, force: bool = False) -> OperationResult:
        if force and not context.raw_admin:
            return OperationResult(Status.PERMISSION_DENIED, "force requires raw administrative access")
        if error := self._validate_operation(operation, context):
            return error
        if error := self._validate_property_limits((operation,)):
            return error
        transaction_id = _transaction_id()
        before = self._before(EventKind.BEFORE_MUTATION, operation, context, transaction_id, True)
        if before.cancelled:
            result = OperationResult(Status.CANCELLED, before.cancellation_reason or "mutation cancelled")
            self._audit(operation, context, result, transaction_id)
            return result
        commit_error = None
        result: OperationResult
        with self._mutation_lock, self.adapter.mutation_guard():
            commit_error = self._validate_property_limits((operation,))
            if commit_error is None:
                result = self.adapter.apply(operation, force)
        if commit_error is not None:
            self._audit(operation, context, commit_error, transaction_id)
            return commit_error
        try:
            self._after(EventKind.AFTER_MUTATION, operation, context, result, transaction_id)
        finally:
            self._audit(operation, context, result, transaction_id)
        return result

    def transact(self, transaction: Transaction, context: AccessContext) -> TransactionResult:
        if not transaction.operations:
            return TransactionResult(Status.APPLIED, "empty transaction", transaction_id=_transaction_id())
        if len(transaction.operations) > self.limits.max_transaction_operations:
            return TransactionResult(Status.INVALID_VALUE, "transaction exceeds operation limit")
        if transaction.require_atomic and not self.capabilities.atomic_transactions:
            return TransactionResult(Status.UNSUPPORTED, "adapter does not provide atomic transactions")
        if transaction.force and not context.raw_admin:
            return TransactionResult(Status.PERMISSION_DENIED, "force requires raw administrative access")
        transaction_context = replace(context, reason=transaction.audit_reason) if transaction.audit_reason else context
        for operation in transaction.operations:
            if error := self._validate_operation(operation, transaction_context):
                return TransactionResult(error.status, error.message)
        if error := self._validate_property_limits(transaction.operations):
            return TransactionResult(error.status, error.message)
        transaction_id = _transaction_id()
        refs = tuple(dict.fromkeys(ref for operation in transaction.operations for ref in operation_refs(operation)))
        before = tuple(result.snapshot for ref in refs if (result := self.adapter.capture(ref)).snapshot is not None)
        event = Event(EventKind.BEFORE_TRANSACTION, transaction_id, "transaction", transaction_context, refs,
                      before=before, cancellable=True)
        failures = self.event_bus.publish(event)
        if failures and not event.cancelled:
            event.cancelled = True
            event.cancellation_reason = "event listener failed"
        if event.cancelled:
            message = event.cancellation_reason or "transaction cancelled"
            cancelled = OperationResult(Status.CANCELLED, message)
            operation_results = tuple(cancelled for _ in transaction.operations)
            for operation in transaction.operations:
                self._audit(operation, transaction_context, cancelled, transaction_id)
            return TransactionResult(Status.CANCELLED, message, operation_results,
                                     transaction_id=transaction_id)
        commit_error = None
        with self._mutation_lock, self.adapter.mutation_guard():
            if error := self._validate_property_limits(transaction.operations):
                commit_error = error
            else:
                result = self.adapter.transact(transaction)
                result = replace(result, transaction_id=transaction_id)
                after = tuple(captured.snapshot for ref in refs
                              if (captured := self.adapter.capture(ref)).snapshot is not None)
        if commit_error is not None:
            operation_results = tuple(commit_error for _ in transaction.operations)
            for operation in transaction.operations:
                self._audit(operation, transaction_context, commit_error, transaction_id)
            return TransactionResult(commit_error.status, commit_error.message,
                                     operation_results, transaction_id=transaction_id)
        try:
            self.event_bus.publish(Event(EventKind.AFTER_TRANSACTION, result.transaction_id, "transaction",
                                         transaction_context, refs, before=before, after=after))
        finally:
            for operation, operation_result in zip(transaction.operations, result.operation_results):
                self._audit(operation, transaction_context, operation_result, result.transaction_id,
                            rolled_back=result.rolled_back)
        return result

    def flush(self, target: DynamicPropertyTarget, context: AccessContext) -> OperationResult:
        del context
        if error := validate_target(target):
            return OperationResult(Status.INVALID_TARGET, error)
        if not self._target_capable(target):
            return OperationResult(Status.UNSUPPORTED, f"target kind {target.kind.value} is unsupported")
        if not self.capabilities.persistence_flush:
            return OperationResult(Status.UNSUPPORTED, "adapter does not support persistence flush")
        return self.adapter.flush(target)

    def set(self, ref: CollectionRef, key: str, value: DynamicPropertyValue,
            context: AccessContext, expected_revision: int | None = None) -> OperationResult:
        return self.apply(SetPropertyOperation(ref, key, value, expected_revision), context)

    def set_many(self, ref: CollectionRef, values: Mapping[str, DynamicPropertyValue],
                 context: AccessContext, expected_revision: int | None = None) -> OperationResult:
        return self.apply(SetManyOperation(ref, dict(values), expected_revision), context)

    def remove(self, ref: CollectionRef, key: str, context: AccessContext,
               expected_revision: int | None = None, require_existing: bool = False) -> OperationResult:
        return self.apply(RemovePropertyOperation(ref, key, expected_revision, require_existing), context)

    def clear(self, ref: CollectionRef, context: AccessContext, expected_revision: int | None = None,
              remove_collection: bool = False) -> OperationResult:
        return self.apply(ClearCollectionOperation(ref, expected_revision, remove_collection), context)

    def migrate_collection(self, source: CollectionRef, destination: CollectionRef,
                           context: AccessContext,
                           policy: ImportPolicy = ImportPolicy.FAIL_IF_DESTINATION_EXISTS,
                           remove_source: bool = True,
                           expected_source_revision: int | None = None,
                           expected_destination_revision: int | None = None) -> OperationResult:
        return self.apply(TransferCollectionOperation(source, destination,
                                                      expected_source_revision=expected_source_revision,
                                                      expected_destination_revision=expected_destination_revision,
                                                      destination_policy=policy,
                                                      remove_source=remove_source), context)

    def export_collection(self, ref: CollectionRef, context: AccessContext) -> ExportResult:
        if not self.capabilities.export_import:
            return ExportResult(Status.UNSUPPORTED, "adapter does not support export")
        captured = self.capture(ref, context)
        if not captured.ok or captured.snapshot is None:
            return ExportResult(captured.status, captured.message)
        document = json.dumps({
            "schema": 1,
            "target": describe_target(ref.target),
            "collection": ref.collection,
            "revision": captured.snapshot.revision,
            "properties": {key: _encoded_value(value)
                           for key, value in sorted(captured.snapshot.properties.items())},
        }, sort_keys=True, separators=(",", ":"))
        return ExportResult(Status.CAPTURED, "exported", document, captured.snapshot.revision)

    def import_collection(self, destination: CollectionRef, document: str,
                          context: AccessContext, policy: ImportPolicy = ImportPolicy.MERGE,
                          expected_revision: int | None = None) -> OperationResult:
        try:
            if not isinstance(document, str):
                raise TypeError("import document must be a string")
            if len(document.encode("utf-8")) > self.limits.max_import_bytes:
                return OperationResult(Status.INVALID_VALUE, "import document exceeds byte limit")
            root = json.loads(document, object_pairs_hook=_object_without_duplicates)
            allowed_fields = {"schema", "target", "collection", "revision", "properties"}
            if (not isinstance(root, dict) or root.get("schema") != 1
                    or not isinstance(root.get("properties"), dict)
                    or not set(root).issubset(allowed_fields)):
                raise ValueError("document must use schema 1 with a properties object")
            properties = {key: _decoded_value(value) for key, value in root["properties"].items()}
        except (OverflowError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return OperationResult(Status.INVALID_VALUE, f"invalid import document: {exc}")
        return self.apply(ImportCollectionOperation(destination, properties, expected_revision, policy), context)

    def before_external_mutation(self, operation: Operation, context: AccessContext,
                                 cancellable: bool) -> ExternalMutationGateResult:
        if context.origin is MutationOrigin.API:
            context = replace(context, origin=MutationOrigin.NATIVE_HOOK)
        transaction_id = _transaction_id()
        if not self.capabilities.external_change_observation:
            return ExternalMutationGateResult(ExternalMutationDecision.OBSERVE_ONLY, Status.UNSUPPORTED,
                                              "external change observation is unavailable", transaction_id)
        can_cancel = cancellable and self.capabilities.external_change_cancellation
        if error := self._validate_operation(operation, context):
            decision = ExternalMutationDecision.CANCEL if can_cancel else ExternalMutationDecision.OBSERVE_ONLY
            return ExternalMutationGateResult(decision, error.status, error.message, transaction_id)
        if error := self._validate_property_limits((operation,)):
            decision = ExternalMutationDecision.CANCEL if can_cancel else ExternalMutationDecision.OBSERVE_ONLY
            return ExternalMutationGateResult(decision, error.status, error.message, transaction_id)
        event = self._before(EventKind.BEFORE_EXTERNAL_MUTATION, operation, context, transaction_id, can_cancel)
        if event.cancelled and can_cancel:
            return ExternalMutationGateResult(ExternalMutationDecision.CANCEL, Status.CANCELLED,
                                              event.cancellation_reason or "external mutation cancelled",
                                              transaction_id)
        if cancellable and not self.capabilities.external_change_cancellation:
            return ExternalMutationGateResult(ExternalMutationDecision.OBSERVE_ONLY, Status.UNSUPPORTED,
                                              "external mutation can be observed but not cancelled",
                                              transaction_id)
        return ExternalMutationGateResult(ExternalMutationDecision.ALLOW, Status.APPLIED,
                                          "external mutation allowed", transaction_id)

    def after_external_mutation(self, operation: Operation, result: OperationResult,
                                context: AccessContext, transaction_id: str = "") -> None:
        if context.origin is MutationOrigin.API:
            context = replace(context, origin=MutationOrigin.NATIVE_HOOK)
        transaction_id = transaction_id or _transaction_id()
        try:
            self._after(EventKind.AFTER_EXTERNAL_MUTATION, operation, context, result, transaction_id)
        finally:
            self._audit(operation, context, result, transaction_id, external=True)
