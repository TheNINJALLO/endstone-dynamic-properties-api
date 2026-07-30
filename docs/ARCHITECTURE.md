# Architecture

## One service, several native backends

The public API is target-neutral. The exact native implementation composes five backend families behind one `IDynamicPropertyAdapter`:

1. **Level backend** for world collections and persistence flushes.
2. **Actor backend** for online players and loaded entities.
3. **Item backend** for live item stacks in inventories, containers, and dropped-item actors.
4. **Storage backend** for offline players and unloaded persistent entities.
5. **Block backend** for block entities that actually expose Bedrock dynamic properties.

An external hook coordinator surrounds Bedrock’s mutation paths, while a transaction coordinator unifies preflight, commit, persistence, rollback, events, and auditing.

```text
Endstone plugins
      |
      v
LiveDynamicPropertyService  (endstone:dynamic-properties:v1)
      |
      v
DynamicPropertyService
  | access policy
  | validation
  | revisions
  | events/audit
  | transaction planning
      |
      v
Verified BDS 1.26.33.1 adapter
  | level
  | actors
  | items
  | offline/stored records
  | supported block entities
  | external mutation hooks
```

## Why the complete gate is strict

Registering only live world/player/entity access would create a service whose name promises more than its implementation. Therefore the native plugin checks every capability and refuses registration unless the same adapter supports all declared target types, atomic cross-target transactions, rollback, external observation/cancellation, and persistence verification.

## Main-thread boundary

Every live BDS object is resolved and mutated on the primary server thread. Background work may parse imports, compute hashes, or prepare immutable transaction plans, but it may not retain live `Actor`, `ItemStack`, `Container`, `BlockActor`, `LevelStorage`, or `DynamicProperties` pointers.

## Coordinator boundary

Mutation callbacks run without coordinator locks. Immediately afterward, the service serializes final validation and commit for every service that wraps the same adapter instance. A listener may therefore perform a nested write; the outer request is revalidated against the resulting state before it can commit.

Callers must mutate through the service, not by invoking adapter mutation methods directly. Direct adapter writes bypass access policy, limits, events, and audits. A verified native hook must retain its platform transaction lease across the before gate, original Bedrock call, and after notification; the split hook API alone is not a lock.

## Storage boundary

Offline-player and stored-entity operations use Bedrock’s storage ownership and serialization mechanisms. They do not open LevelDB directly while the server owns the world. The adapter must coordinate with the server’s storage manager, maintain record identity, and use crash-safe commit semantics.

## Transaction stages

1. Resolve every target.
2. Capture every collection and record revision.
3. Validate access, keys, values, item constraints, target lifecycle, and destination policies.
4. Build immutable before snapshots and rollback plans.
5. Acquire deterministic target locks or a main-thread transaction lease.
6. Recheck every revision.
7. Apply live and stored mutations.
8. Mark actors/items/blocks dirty and schedule persistence.
9. Flush where requested.
10. Publish after-events and audit records.
11. On failure, restore every before snapshot and verify restoration.

The adapter returns `RollbackFailed` rather than hiding a failed recovery.

## External-hook recursion

Native set/remove/clear hooks carry a thread-local mutation token. API writes, storage loads, deserialization, and rollback writes are marked so the hook layer does not recursively re-enter the service or emit duplicate events.
