# Exact native symbol and ABI audit

The inspected public/generated headers from other projects are discovery aids only. They are not accepted as offsets, fingerprints, or layout proof for BDS package `1.26.33.1`.

## Required symbol groups

### Common collection operations

- get property
- list property IDs
- total byte count
- set property
- remove property
- clear collection
- update collection name
- validate property
- collection to/from variant map

### World

- server-level dynamic-property accessor
- dynamic-properties manager accessor
- verified level-storage write/flush path

### Actors

- actor dynamic-properties accessor
- actor dirty/save coordination

### Items

- get all/get one
- set/remove/clear
- live slot write-back and client notification paths

### Stored targets

- offline-player record read/write
- persistent stored-entity record read/write
- ownership/locking coordination

### Blocks

- supported block dynamic-properties component lookup
- block actor dirty/persistence path

### External mutations

- before/after set
- before/after remove
- before/after clear

## Per-symbol evidence

Each manifest entry requires:

- exact mangled name where available;
- exact RVA;
- short stable fingerprint or reviewed resolution mechanism;
- uniqueness result;
- signature confirmation;
- behavior confirmation against callers and effects;
- concise verification notes;
- platform and executable identity.

## ABI contracts

The manifest separately records review notes for:

- property variant layout and ownership;
- `Vec3` argument/return ABI;
- reflection context access;
- actor component lifetime;
- item mutation and network notification;
- offline-player storage ownership;
- stored-entity storage ownership;
- block component lifetime;
- hook calling convention and original-call preservation.

A compile or unique byte pattern is not sufficient. The target behavior must be confirmed.
