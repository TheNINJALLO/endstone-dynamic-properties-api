# Transactions and rollback

## Goals

The transaction engine prevents partial updates across unrelated persistence domains. A single transaction may modify world state, a connected player, an offline player, an unloaded entity, an item stack, and a supported block entity.

## Revisions

Each collection revision hashes:

- target identity;
- collection name;
- collection existence;
- sorted property IDs;
- explicit value types;
- value contents.

An expected revision is checked during preflight and again immediately before commit.

## Native commit requirements

A verified native transaction must:

- run its live-object portion on the primary thread;
- obtain deterministic ownership over all involved persistent records;
- reject a target that changes between live and stored state during preflight;
- validate every final item stack and property collection before writes;
- retain complete before snapshots;
- apply persistence writes in a crash-safe sequence;
- restore all affected participants on failure;
- verify rollback rather than assuming it succeeded.

## Event ordering

1. The service coordinator allocates one transaction ID.
2. One cancellable `BeforeTransaction` event carries all participating collections and their snapshots.
3. Listener failures are isolated and fail closed; any cancellation stops the transaction before adapter writes.
4. The service reacquires the shared coordinator boundary and revalidates the final state.
5. The adapter commits atomically or leaves the committed state unchanged.
6. One `AfterTransaction` event carries snapshots recaptured from committed state.
7. Per-operation audit entries share the coordinator ID and include cancellation or rollback state.

`BeforeTransaction.before` is the state observed when the event was dispatched. If a listener performs a nested write, commit-time validation and each operation result are authoritative; listener edits to event metadata cannot replace the coordinator transaction ID or committed snapshots. Exceptions from after-event listeners are reported by the event bus but never turn an already committed mutation into a caller-visible failure or suppress its audit. An audit-sink exception is separately reported or logged and likewise cannot replace the committed result.

Load/deserialization and rollback-origin operations are distinguishable from normal API and Script API mutations.
