# Target behavior

## World

World properties are addressed by world ID and collection. They are persisted by Bedrock’s level dynamic-properties manager. `flush()` requests the native manager’s verified write path.

## Online players and loaded entities

The adapter resolves the live actor by stable identity, obtains its dynamic-properties component, performs mutations on the primary thread, marks the actor persistent state dirty, and confirms a save/reload round trip.

## Offline players

Offline access is not implemented by fabricating a temporary live player. The storage backend reads the persistent player record through Bedrock-owned storage interfaces, modifies only the dynamic-property payload, preserves unrelated data, and commits atomically. A joining player must observe the new value without duplicate records.

## Stored entities

Stored entity operations address a persistent actor record while its chunk is unloaded. The adapter must preserve actor identifiers, dimension/chunk ownership, and unrelated save fields. If the same entity becomes loaded during an operation, the coordinator must abandon the storage path and retry against the live actor.

## Player item slots

Item operations target the real slot, not a detached copy. The native implementation captures the slot revision, clones and validates the item, updates dynamic-property custom data, writes the item back, signals the inventory/container change, and verifies client refresh.

## Block-container item slots

The block and chunk must be loaded. The adapter validates the container actor and slot, updates the live stack, marks the slot/container/block actor changed, and sends the appropriate client update.

## Dropped items

The target is the dropped-item actor and its live stack. Changes must preserve pickup behavior, count, net IDs, and client representation.

## Block entities

Only block entities that genuinely support Bedrock’s block dynamic-property component are valid. The API never treats arbitrary vanilla blocks as dynamic-property stores. Unsupported blocks return `Unsupported` or `CollectionUnavailable`.
