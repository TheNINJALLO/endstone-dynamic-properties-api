# External mutation hooks

## Purpose

Script API, behavior packs, and other native modules may call Bedrock’s dynamic-property methods directly. The verified bridge hooks the common native mutation paths so the Endstone API can observe the same property universe.

## Required hooks

- `DynamicProperties::setDynamicProperty`
- `DynamicProperties::removeDynamicProperty`
- `DynamicProperties::clearCollection`
- item helper set/remove/clear paths where they do not converge on the common collection methods

## Hook contract

Each hook must:

1. Resolve the owning target and collection.
2. Capture the old value or collection snapshot.
3. Build an external mutation event.
4. Run cancellable before-listeners only when interception occurs before mutation.
5. Call the exact original function once when allowed.
6. Capture the resulting state.
7. Publish after-events and audit records.

## Suppression

No normal mutation events are emitted while:

- loading world or actor save data;
- deserializing an item;
- replaying a rollback;
- applying an API mutation already represented by its own event;
- shutting down persistence internals.

A thread-local recursion guard and transaction token are mandatory.

## Cancellation policy

Observation may be enabled only after the hook’s old/new capture is correct. Cancellation is a stronger capability and remains false until the disposable-world tests prove that returning without the original call does not corrupt caches, network state, or persistence bookkeeping.
