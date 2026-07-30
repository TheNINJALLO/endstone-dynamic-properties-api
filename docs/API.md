# API reference

## Service identity

```cpp
endstone:dynamic-properties:v1
```

A native provider is registered only when `DynamicPropertyCapabilities::completeControl()` returns `true`.

## Values

```cpp
using DynamicPropertyValue = std::variant<bool, double, std::string, Vector3>;
using DynamicPropertyMap = std::map<std::string, DynamicPropertyValue>;
```

All numeric values must be finite. Strings, property keys, collection names, imports, property counts, and transaction sizes are bounded by `ValidationLimits`.

## Targets

`DynamicPropertyTarget` supports:

| Target kind | Identity fields |
|---|---|
| World | world ID |
| Online player | world ID + XUID |
| Offline player | world ID + XUID |
| Loaded entity | world ID + unique entity ID |
| Stored entity | world ID + persistent entity ID |
| Player main inventory item | XUID + slot |
| Player armor item | XUID + armor slot |
| Player offhand item | XUID + slot |
| Player Ender Chest item | XUID + slot |
| Block-container item | dimension + block position + slot |
| Dropped item | item entity ID |
| Supported block entity | dimension + block position |

Each operation addresses a `CollectionRef` containing a target and collection name.

## Reads

```cpp
auto capture = service.capture(ref, context);
auto property = service.get(ref, "rank", context);
auto collections = service.listCollections(target, context);
```

`CollectionSnapshot` includes:

- all property IDs and values;
- total estimated byte count;
- deterministic revision;
- collection existence;
- loaded, persistent, and writable flags.

A missing collection is a successful capture with `exists=false`. A missing key returns `NotFound` and the current collection revision.

## Mutations

```cpp
service.set(ref, "enabled", true, context);
service.setMany(ref, {{"tax", 0.05}, {"season", std::string("winter")}}, context);
service.remove(ref, "legacy", context);
service.clear(ref, context, {}, false); // clear but retain collection
service.clear(ref, context, {}, true);  // remove collection
```

All mutation operations support optimistic revisions. `force=true` is reserved for explicit administrative recovery and migration workflows.

## Property and collection transfers

`TransferPropertyOperation` copies or moves one key between any two supported target collections. `TransferCollectionOperation` copies or moves an entire collection. `ImportPolicy` controls destination conflicts:

- `FailIfDestinationExists`
- `Merge`
- `Replace`

Source and destination revision expectations are checked independently. For a same-collection property transfer, both expectations must match each other and the collection's current revision.

## Collection migration

`migrateCollection()` is a convenience wrapper around a cross-collection transfer. It accepts optional source and destination revisions after the existing `policy` and `remove_source` arguments. Its primary use cases include behavior-pack header UUID changes, plugin namespace migrations, world transfers, and recovery from abandoned collection names.

## Export and import

`exportCollection()` emits a deterministic schema-1 JSON document with explicit value types. `importCollection()` validates the complete document before mutating any target.

## Transactions

```cpp
DynamicPropertyTransaction transaction;
transaction.rollback_on_failure = true;
transaction.require_atomic = true;
transaction.operations = {
    SetPropertyOperation{world, "season", std::string("winter")},
    SetPropertyOperation{player, "rank", std::string("citizen")},
};

auto result = service.transact(transaction, context);
```

The native adapter must preflight every participant before the first write. A transaction may include world, actor, item, block, offline-player, and stored-entity operations together.

## External changes

`beforeExternalMutation()` and `afterExternalMutation()` are called by the native hook layer for mutations that bypass this service. The before gate may return:

- `Allow`
- `Cancel`
- `ObserveOnly`

Cancellation is only exposed after the platform hook proves it intercepts the operation before Bedrock changes memory or persistence state.

Listener exceptions are isolated so one plugin cannot suppress later listeners or prevent an audit. A failure in a cancellable before-event fails closed. Exceptions from after-event listeners do not replace the committed result. Python logs each failure; the C++ bus invokes its configured `setListenerFailureHandler()` callback, and direct `publish()` calls also return the exception pointers.

Audit-sink exceptions likewise never replace a mutation or transaction result after commit. Python logs them. C++ invokes the callback configured through `DynamicPropertyService::setAuditFailureHandler()`; exceptions raised by that reporting callback are also contained. Operators should treat every report as lost audit evidence and repair the sink before continuing production writes.

## Access contexts

`AccessContext` identifies the plugin, actor, origin, administrative authority, and audit reason. Normal plugins are restricted to their generated collection prefix. `raw_admin=true` enables explicit raw collection access and must be guarded by the consuming plugin’s permission system.

## Error model

Important statuses include:

- `Conflict`
- `Cancelled`
- `TargetUnavailable`
- `PermissionDenied`
- `Unsupported`
- `RuntimeMismatch`
- `BinaryIdentityMismatch`
- `SymbolValidationFailed`
- `StorageUnavailable`
- `PersistenceFailed`
- `TransactionFailed`
- `RollbackFailed`

No unsupported path returns success.
