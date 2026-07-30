# Offline players and stored entities

Offline and stored targets are part of v1, not a future service.

## Required behavior

### Offline players

- Read and modify a player while no live `Player` object exists.
- Preserve inventory, abilities, position, tags, attributes, and all unrelated NBT.
- Prevent a second record from being created.
- Coordinate with a login that begins during the operation.
- Persist through join, disconnect, and restart.

### Stored entities

- Read and modify a persistent entity while its owning chunk is unloaded.
- Preserve entity identity and chunk ownership.
- Coordinate with chunk loading or entity activation during the operation.
- Persist through chunk load/unload and restart.

## Forbidden implementation

The server process must not open and modify the live world LevelDB through an independent database handle. This can bypass Bedrock caches, locks, journaling, and ownership rules. Native acceptance requires a Bedrock-owned storage path or a verified pause/exclusive ownership mechanism.

## Crash safety

Storage operations require:

- immutable before image;
- validated candidate image;
- atomic or journaled commit;
- recovery detection after forced termination;
- no half-written collection or duplicate record;
- integration with cross-target rollback.
