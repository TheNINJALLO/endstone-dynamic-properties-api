# Migration and recovery

## Behavior-pack UUID migration

Dynamic-property collections may be associated with a behavior-pack identity. When a pack identity changes, administrators can migrate the old collection into the new collection without splitting the API or exporting through Script API.

Recommended sequence:

1. Export the old collection.
2. Capture old and destination revisions.
3. Run a transaction using `TransferCollectionOperation`, or pass both captured revisions to `migrateCollection()`.
4. Use `FailIfDestinationExists` unless a deliberate merge/replace has been reviewed.
5. Flush persistence.
6. Restart or reload the stage world and verify both collection states.
7. Retain the export until production validation is complete.

## Cross-target migration

The source and destination may be different target types. Examples include world-to-player defaults, player-to-offline profile archival, stored-entity repair, or item-template migration.

## Import safety

Imports use explicit type tags and are fully parsed and validated before any mutation. Unknown types, malformed vectors, non-finite numbers, duplicate JSON keys, oversized documents, and invalid keys are rejected.
