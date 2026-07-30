from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Iterator, Mapping, TypeAlias


@dataclass(frozen=True, order=True, slots=True)
class Vector3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


DynamicPropertyValue: TypeAlias = bool | float | str | Vector3
DynamicPropertyMap: TypeAlias = dict[str, DynamicPropertyValue]


class _ImmutablePropertyMap(Mapping[str, DynamicPropertyValue]):
    """Defensive, deepcopy- and pickle-safe immutable property mapping."""

    __slots__ = ("__data",)

    def __init__(self, values: Mapping[str, DynamicPropertyValue]) -> None:
        self.__data = MappingProxyType(deepcopy(dict(values)))

    def __getitem__(self, key: str) -> DynamicPropertyValue:
        return self.__data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.__data)

    def __len__(self) -> int:
        return len(self.__data)

    def __repr__(self) -> str:
        return repr(dict(self.__data))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Mapping):
            return NotImplemented
        return dict(self.__data) == dict(other)

    def __deepcopy__(self, memo: dict[int, object]) -> _ImmutablePropertyMap:
        del memo
        return self

    def __reduce__(self) -> tuple[object, tuple[dict[str, DynamicPropertyValue]]]:
        return type(self), (dict(self.__data),)


def _immutable_properties(
    values: Mapping[str, DynamicPropertyValue],
) -> Mapping[str, DynamicPropertyValue]:
    if isinstance(values, _ImmutablePropertyMap):
        return values
    return _ImmutablePropertyMap(values)


class TargetKind(str, Enum):
    WORLD = "world"
    ONLINE_PLAYER = "online_player"
    OFFLINE_PLAYER = "offline_player"
    LOADED_ENTITY = "loaded_entity"
    STORED_ENTITY = "stored_entity"
    PLAYER_INVENTORY_SLOT = "player_inventory_slot"
    PLAYER_ARMOR_SLOT = "player_armor_slot"
    PLAYER_OFFHAND_SLOT = "player_offhand_slot"
    PLAYER_ENDER_CHEST_SLOT = "player_ender_chest_slot"
    BLOCK_CONTAINER_SLOT = "block_container_slot"
    DROPPED_ITEM = "dropped_item"
    BLOCK_ENTITY = "block_entity"


class InventorySection(str, Enum):
    NONE = "none"
    MAIN = "main"
    ARMOR = "armor"
    OFFHAND = "offhand"
    ENDER_CHEST = "ender_chest"
    BLOCK_CONTAINER = "block_container"


@dataclass(frozen=True, order=True, slots=True)
class BlockLocation:
    dimension: str = "overworld"
    x: int = 0
    y: int = 0
    z: int = 0


@dataclass(frozen=True, order=True, slots=True)
class DynamicPropertyTarget:
    kind: TargetKind = TargetKind.WORLD
    world_id: str = "default"
    xuid: str = ""
    entity_id: str = ""
    block: BlockLocation | None = None
    section: InventorySection = InventorySection.NONE
    slot: int = -1
    item_entity_id: str = ""

    @classmethod
    def world(cls, world_id: str = "default") -> DynamicPropertyTarget:
        return cls(TargetKind.WORLD, world_id)

    @classmethod
    def online_player(cls, xuid: str, world_id: str = "default") -> DynamicPropertyTarget:
        return cls(TargetKind.ONLINE_PLAYER, world_id, xuid=xuid)

    @classmethod
    def offline_player(cls, xuid: str, world_id: str = "default") -> DynamicPropertyTarget:
        return cls(TargetKind.OFFLINE_PLAYER, world_id, xuid=xuid)

    @classmethod
    def loaded_entity(cls, entity_id: str, world_id: str = "default") -> DynamicPropertyTarget:
        return cls(TargetKind.LOADED_ENTITY, world_id, entity_id=entity_id)

    @classmethod
    def stored_entity(cls, entity_id: str, world_id: str = "default") -> DynamicPropertyTarget:
        return cls(TargetKind.STORED_ENTITY, world_id, entity_id=entity_id)

    @classmethod
    def player_item(
        cls, xuid: str, section: InventorySection, slot: int, world_id: str = "default"
    ) -> DynamicPropertyTarget:
        mapping = {
            InventorySection.MAIN: TargetKind.PLAYER_INVENTORY_SLOT,
            InventorySection.ARMOR: TargetKind.PLAYER_ARMOR_SLOT,
            InventorySection.OFFHAND: TargetKind.PLAYER_OFFHAND_SLOT,
            InventorySection.ENDER_CHEST: TargetKind.PLAYER_ENDER_CHEST_SLOT,
        }
        return cls(mapping.get(section, TargetKind.PLAYER_INVENTORY_SLOT), world_id, xuid=xuid,
                   section=section, slot=slot)

    @classmethod
    def block_container_item(
        cls, block: BlockLocation, slot: int, world_id: str = "default"
    ) -> DynamicPropertyTarget:
        return cls(TargetKind.BLOCK_CONTAINER_SLOT, world_id, block=block,
                   section=InventorySection.BLOCK_CONTAINER, slot=slot)

    @classmethod
    def dropped_item(cls, entity_id: str, world_id: str = "default") -> DynamicPropertyTarget:
        return cls(TargetKind.DROPPED_ITEM, world_id, item_entity_id=entity_id)

    @classmethod
    def block_entity(cls, block: BlockLocation, world_id: str = "default") -> DynamicPropertyTarget:
        return cls(TargetKind.BLOCK_ENTITY, world_id, block=block)


@dataclass(frozen=True, order=True, slots=True)
class CollectionRef:
    target: DynamicPropertyTarget
    collection: str


class MutationOrigin(str, Enum):
    API = "api"
    COMMAND = "command"
    SCRIPT_API = "script_api"
    PLAYER = "player"
    WORLD_LOAD = "world_load"
    STORAGE_LOAD = "storage_load"
    MIGRATION = "migration"
    ROLLBACK = "rollback"
    NATIVE_HOOK = "native_hook"
    UNKNOWN = "unknown"


class Status(str, Enum):
    APPLIED = "applied"
    CAPTURED = "captured"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    CANCELLED = "cancelled"
    TARGET_UNAVAILABLE = "target_unavailable"
    COLLECTION_UNAVAILABLE = "collection_unavailable"
    INVALID_TARGET = "invalid_target"
    INVALID_COLLECTION = "invalid_collection"
    INVALID_KEY = "invalid_key"
    INVALID_VALUE = "invalid_value"
    PERMISSION_DENIED = "permission_denied"
    UNSUPPORTED = "unsupported"
    RUNTIME_MISMATCH = "runtime_mismatch"
    BINARY_IDENTITY_MISMATCH = "binary_identity_mismatch"
    SYMBOL_VALIDATION_FAILED = "symbol_validation_failed"
    STORAGE_UNAVAILABLE = "storage_unavailable"
    PERSISTENCE_FAILED = "persistence_failed"
    TRANSACTION_FAILED = "transaction_failed"
    ROLLBACK_FAILED = "rollback_failed"
    ADAPTER_UNAVAILABLE = "adapter_unavailable"
    ADAPTER_ERROR = "adapter_error"


class ImportPolicy(str, Enum):
    FAIL_IF_DESTINATION_EXISTS = "fail_if_destination_exists"
    MERGE = "merge"
    REPLACE = "replace"


class ExternalMutationDecision(str, Enum):
    ALLOW = "allow"
    CANCEL = "cancel"
    OBSERVE_ONLY = "observe_only"


@dataclass(frozen=True, slots=True)
class AccessContext:
    plugin_id: str = ""
    actor_id: str = ""
    raw_admin: bool = False
    origin: MutationOrigin = MutationOrigin.API
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ValidationLimits:
    max_collection_bytes: int = 256
    max_key_bytes: int = 256
    max_string_bytes: int = 32767
    max_properties_per_collection: int = 16384
    max_transaction_operations: int = 4096
    max_import_bytes: int = 16 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class Capabilities:
    world: bool = False
    online_players: bool = False
    offline_players: bool = False
    loaded_entities: bool = False
    stored_entities: bool = False
    player_inventory_items: bool = False
    player_armor_items: bool = False
    player_offhand_items: bool = False
    player_ender_chest_items: bool = False
    block_container_items: bool = False
    dropped_items: bool = False
    block_entities: bool = False
    block_dynamic_properties: bool = False
    read: bool = False
    write: bool = False
    remove: bool = False
    clear: bool = False
    list_ids: bool = False
    list_collections: bool = False
    byte_count: bool = False
    bulk_set: bool = False
    collection_rename: bool = False
    property_copy_move: bool = False
    collection_copy_move: bool = False
    collection_migration: bool = False
    export_import: bool = False
    atomic_transactions: bool = False
    rollback: bool = False
    audit: bool = False
    watches: bool = False
    external_change_observation: bool = False
    external_change_cancellation: bool = False
    persistence_flush: bool = False
    exact_build_match: bool = False
    exact_binary_hash_match: bool = False
    symbols_validated: bool = False
    stage_probe_passed: bool = False

    @property
    def complete_control(self) -> bool:
        return all(self.__dict__.values()) if hasattr(self, "__dict__") else all(
            getattr(self, name) for name in self.__dataclass_fields__
        )


@dataclass(frozen=True, slots=True)
class CollectionSnapshot:
    ref: CollectionRef
    properties: Mapping[str, DynamicPropertyValue] = field(default_factory=dict)
    byte_count: int = 0
    revision: int = 0
    exists: bool = False
    loaded: bool = True
    persistent: bool = True
    writable: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "properties", _immutable_properties(self.properties))


@dataclass(frozen=True, slots=True)
class CaptureResult:
    status: Status
    message: str
    snapshot: CollectionSnapshot | None = None

    @property
    def ok(self) -> bool:
        return self.status is Status.CAPTURED


@dataclass(frozen=True, slots=True)
class ListCollectionsResult:
    status: Status
    message: str
    collections: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status is Status.CAPTURED


@dataclass(frozen=True, slots=True)
class SetPropertyOperation:
    ref: CollectionRef
    key: str
    value: DynamicPropertyValue
    expected_revision: int | None = None


@dataclass(frozen=True, slots=True)
class SetManyOperation:
    ref: CollectionRef
    values: Mapping[str, DynamicPropertyValue]
    expected_revision: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", _immutable_properties(self.values))


@dataclass(frozen=True, slots=True)
class RemovePropertyOperation:
    ref: CollectionRef
    key: str
    expected_revision: int | None = None
    require_existing: bool = False


@dataclass(frozen=True, slots=True)
class RemoveManyOperation:
    ref: CollectionRef
    keys: tuple[str, ...]
    expected_revision: int | None = None
    require_all_existing: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "keys", tuple(self.keys))


@dataclass(frozen=True, slots=True)
class ClearCollectionOperation:
    ref: CollectionRef
    expected_revision: int | None = None
    remove_collection: bool = False


@dataclass(frozen=True, slots=True)
class RenameCollectionOperation:
    target: DynamicPropertyTarget
    source: str
    destination: str
    expected_source_revision: int | None = None
    destination_policy: ImportPolicy = ImportPolicy.FAIL_IF_DESTINATION_EXISTS
    # Appended to preserve the original positional argument order.
    expected_destination_revision: int | None = None


@dataclass(frozen=True, slots=True)
class TransferPropertyOperation:
    source: CollectionRef
    source_key: str
    destination: CollectionRef
    destination_key: str
    expected_source_revision: int | None = None
    expected_destination_revision: int | None = None
    remove_source: bool = False
    overwrite: bool = False


@dataclass(frozen=True, slots=True)
class TransferCollectionOperation:
    source: CollectionRef
    destination: CollectionRef
    expected_source_revision: int | None = None
    expected_destination_revision: int | None = None
    destination_policy: ImportPolicy = ImportPolicy.FAIL_IF_DESTINATION_EXISTS
    remove_source: bool = False


@dataclass(frozen=True, slots=True)
class ImportCollectionOperation:
    destination: CollectionRef
    properties: Mapping[str, DynamicPropertyValue]
    expected_destination_revision: int | None = None
    policy: ImportPolicy = ImportPolicy.MERGE

    def __post_init__(self) -> None:
        object.__setattr__(self, "properties", _immutable_properties(self.properties))


Operation: TypeAlias = (
    SetPropertyOperation | SetManyOperation | RemovePropertyOperation | RemoveManyOperation |
    ClearCollectionOperation | RenameCollectionOperation | TransferPropertyOperation |
    TransferCollectionOperation | ImportCollectionOperation
)


@dataclass(frozen=True, slots=True)
class OperationResult:
    status: Status
    message: str
    before: tuple[CollectionSnapshot, ...] = ()
    after: tuple[CollectionSnapshot, ...] = ()
    resulting_revision: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "before", tuple(self.before))
        object.__setattr__(self, "after", tuple(self.after))

    @property
    def ok(self) -> bool:
        return self.status is Status.APPLIED


@dataclass(frozen=True, slots=True)
class Transaction:
    operations: tuple[Operation, ...] = ()
    force: bool = False
    rollback_on_failure: bool = True
    require_atomic: bool = True
    audit_reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "operations", tuple(self.operations))


@dataclass(frozen=True, slots=True)
class TransactionResult:
    status: Status
    message: str
    operation_results: tuple[OperationResult, ...] = ()
    rolled_back: bool = False
    transaction_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation_results", tuple(self.operation_results))

    @property
    def ok(self) -> bool:
        return self.status is Status.APPLIED


@dataclass(frozen=True, slots=True)
class PropertyReadResult:
    status: Status
    message: str
    value: DynamicPropertyValue | None = None
    collection_revision: int = 0

    @property
    def ok(self) -> bool:
        return self.status is Status.CAPTURED


@dataclass(frozen=True, slots=True)
class ExportResult:
    status: Status
    message: str
    document: str = ""
    revision: int = 0

    @property
    def ok(self) -> bool:
        return self.status is Status.CAPTURED


@dataclass(frozen=True, slots=True)
class ExternalMutationGateResult:
    decision: ExternalMutationDecision
    status: Status
    message: str
    transaction_id: str = ""


__all__ = [
    "AccessContext",
    "BlockLocation",
    "Capabilities",
    "CaptureResult",
    "ClearCollectionOperation",
    "CollectionRef",
    "CollectionSnapshot",
    "DynamicPropertyMap",
    "DynamicPropertyTarget",
    "DynamicPropertyValue",
    "ExportResult",
    "ExternalMutationDecision",
    "ExternalMutationGateResult",
    "ImportCollectionOperation",
    "ImportPolicy",
    "InventorySection",
    "ListCollectionsResult",
    "MutationOrigin",
    "Operation",
    "OperationResult",
    "PropertyReadResult",
    "RemoveManyOperation",
    "RemovePropertyOperation",
    "RenameCollectionOperation",
    "SetManyOperation",
    "SetPropertyOperation",
    "Status",
    "TargetKind",
    "Transaction",
    "TransactionResult",
    "TransferCollectionOperation",
    "TransferPropertyOperation",
    "ValidationLimits",
    "Vector3",
]
