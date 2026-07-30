# Block dynamic properties

Block dynamic properties are included in the unified target model, but they are not available on every block.

## Valid target

A valid block target must expose Bedrock’s supported block-entity dynamic-properties component. The native adapter checks the component at runtime and rejects blocks without it.

## Operations

Supported block targets use the same get, list, set, remove, clear, transfer, migration, export/import, event, audit, revision, and transaction APIs as all other targets.

## Persistence requirements

The native bridge must prove:

- chunk reload persistence;
- server restart persistence;
- client/server consistency where applicable;
- cleanup or intentional transfer when the block is replaced;
- no property leakage to a new block occupying the same coordinates;
- correct behavior when a piston, structure, or world operation moves/recreates the block entity.

## Experimental status

The stage server must use the exact experimental configuration required by the target BDS build. The capability remains closed if the server cannot create a supported block-entity dynamic-property target.
