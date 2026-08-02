# Endstone Dynamic Properties API

**Release:** `v0.1.0-alpha.2`<br>
**Service ABI:** `endstone:dynamic-properties:v1`<br>
**Target:** Minecraft Bedrock Dedicated Server package `1.26.33.1`, runtime `26.33`, Endstone `v0.11.6`

Endstone Dynamic Properties API is one unified persistence system for the entire Bedrock dynamic-property surface. The live targets and the traditionally “later” storage targets are not split into separate APIs. They share one target model, one value model, one access policy, one event stream, one audit log, and one atomic transaction coordinator.

## One complete-control contract

The service covers:

- world collections;
- online and offline players;
- loaded and stored entities;
- player main inventory, armor, offhand, and Ender Chest item stacks;
- block-container item stacks;
- dropped item entities;
- supported dynamic-property block entities;
- external mutations made by Script API or other native callers;
- property and collection migration, including behavior-pack UUID changes.

Supported public values are `bool`, finite `double`, UTF-8 `string`, and `Vector3`. Native `float` values are normalized to `double` at the public boundary.

## Current release status

> **Native-validation alpha:** this source produces a Linux Endstone plugin and
> its ABI-matched tester wheel, but the plugin is gate-closed and is not yet a
> working server API. It also provides the portable C++ SDK, pure-Python
> reference implementation, strict native activation gate, and the tooling
> needed to complete platform verification.

The **portable C++ API, Python reference package, in-memory complete-control adapter, validation, access isolation, events, audits, export/import, migrations, optimistic revisions, and atomic rollback transactions are implemented and tested**.

Mutation requests are defensively copied, callbacks run outside commit locks, and final limit validation is serialized across services sharing an adapter. Event-listener failures cannot suppress later listeners or erase the audit of an already committed write. Audit-sink failures are reported without replacing the committed result.

The exact native bridge is intentionally fail-closed. The Endstone service does not register unless the same platform adapter proves every target family in one activation:

1. Exact BDS `26.33` and Endstone `0.11.6` runtime match.
2. Exact running executable SHA-256 and size match the reviewed `1.26.33.1` manifest.
3. Every required live, item, storage, block, and hook symbol is signature- and behavior-verified.
4. Offline-player and stored-entity read/write contracts are crash-safe and never edit a live LevelDB directly.
5. External set/remove/clear hooks preserve the original call, suppress load/rollback recursion, and are cancellable before mutation.
6. The reviewed native bridge source matches its recorded SHA-256.
7. The complete disposable-world probe passes on the target platform.

A live-only subset cannot register under this ABI. This is deliberate: one service means one truthful capability contract.

The source tree also includes an operator-only CPython 3.14 tester wheel. Its
package-local native bridge exposes no in-memory fallback, its configured
target file represents all 12 target families, and its mutating commands
require explicit confirmation. The tester can inventory existing
tester-visible collections and capture bounded before/after external-mutation
events for the verified native hooks. See
[`examples/python/dynamic_properties_tester_plugin/README.md`](examples/python/dynamic_properties_tester_plugin/README.md)
and [`docs/BUILD_EXACT.md`](docs/BUILD_EXACT.md).

## Target examples

```python
from endstone_dynamic_properties import (
    BlockLocation,
    CollectionRef,
    DynamicPropertyTarget,
    InventorySection,
)

world = CollectionRef(
    DynamicPropertyTarget.world(),
    "endstone-plugin:kingdom_core:settings",
)

offline_player = CollectionRef(
    DynamicPropertyTarget.offline_player("2533274790000000"),
    "endstone-plugin:kingdom_core:profiles",
)

stored_entity = CollectionRef(
    DynamicPropertyTarget.stored_entity("actor-unique-id"),
    "endstone-plugin:kingdom_core:mobs",
)

inventory_item = CollectionRef(
    DynamicPropertyTarget.player_item(
        "2533274790000000", InventorySection.MAIN, 4
    ),
    "endstone-plugin:kingdom_core:item_data",
)

container_item = CollectionRef(
    DynamicPropertyTarget.block_container_item(
        BlockLocation("overworld", 120, 64, -300), 7
    ),
    "endstone-plugin:kingdom_core:item_data",
)
```

## CRUD and revisions

```python
snapshot = api.capture(world, plugin_context)
assert snapshot.ok and snapshot.snapshot is not None

result = api.set(
    world,
    "season",
    "winter",
    plugin_context,
    expected_revision=snapshot.snapshot.revision,
)

api.set_many(world, {
    "pvp": False,
    "tax_rate": 0.05,
    "spawn": Vector3(0.5, 64.0, 0.5),
}, plugin_context)

api.remove(world, "old_event", plugin_context)
api.clear(world, plugin_context, remove_collection=False)
```

Stale revisions return `conflict`; they never silently overwrite newer data.

## Cross-target atomic transactions

```python
transaction = Transaction((
    SetPropertyOperation(world, "season", "winter"),
    SetPropertyOperation(offline_player, "rank", "citizen"),
    SetPropertyOperation(stored_entity, "faction", "midgard"),
))

result = api.transact(transaction, admin_context)
assert result.ok
```

The reference adapter applies the transaction to a candidate store and publishes it only after every operation succeeds. The native acceptance contract requires equivalent preflight and rollback behavior across live actors, items, offline storage, stored entities, block entities, and world properties.

## Collection migration

```python
old_pack = CollectionRef(DynamicPropertyTarget.world(), "old-pack-header-uuid")
new_pack = CollectionRef(DynamicPropertyTarget.world(), "new-pack-header-uuid")

result = api.migrate_collection(
    old_pack,
    new_pack,
    admin_context,
    policy=ImportPolicy.REPLACE,
    remove_source=True,
)
```

The same operation works across targets, so data can be copied or moved between world, player, entity, item, and supported block stores under one transaction.

## Safe and administrative access

Normal plugins receive namespaced collections:

```text
endstone-plugin:<plugin-id>:<logical-name>
```

They cannot enumerate or alter another plugin’s collections. Raw collection access and cross-namespace or behavior-pack UUID migration require an explicit administrative context. A plugin may remove its own namespaced collections; every mutation is audited.

`AccessContext` is an authorization input, not an identity provider. The hosting Endstone boundary must construct it from the authenticated calling plugin or command sender; untrusted callers must never choose `plugin_id` or set `raw_admin` themselves.

## External mutation interception

The service contract contains before/after gates for mutations originating outside the API. The verified native bridge must hook Bedrock’s set, remove, and clear paths so Script API changes can be observed and, where proven safe, cancelled before mutation.

```python
def protect_rank(event):
    if event.key == "rank" and event.actor.origin is MutationOrigin.SCRIPT_API:
        event.cancelled = True
        event.cancellation_reason = "rank is server-managed"

api.event_bus.subscribe(
    EventFilter(EventKind.BEFORE_EXTERNAL_MUTATION, key="rank"),
    protect_rank,
)
```

## Build the portable core

With CMake presets:

```bash
cmake --preset portable-release
cmake --build --preset portable-release
ctest --preset portable-release
PYTHONPATH=python python -m pytest -q tests/python
```

Or configure it directly:

```bash
cmake -S . -B build \
  -DENDSTONE_DYNAMIC_PROPERTIES_BUILD_TESTS=ON \
  -DENDSTONE_DYNAMIC_PROPERTIES_BUILD_PLUGIN=OFF
cmake --build build --parallel
ctest --test-dir build --output-on-failure
PYTHONPATH=python python -m pytest -q tests/python
```

The install tree exports `EndstoneDynamicProperties::core` for downstream CMake consumers:

```cmake
find_package(EndstoneDynamicProperties 0.1 CONFIG REQUIRED)
target_link_libraries(my_plugin PRIVATE EndstoneDynamicProperties::core)
```

## Exact native activation

Read these before attempting a native build:

- `docs/NATIVE_SYMBOL_AUDIT.md`
- `docs/OFFLINE_AND_STORED.md`
- `docs/EXTERNAL_HOOKS.md`
- `docs/BLOCK_DYNAMIC_PROPERTIES.md`
- `docs/STAGE_PROBE.md`
- `docs/BUILD_EXACT.md`

An incomplete manifest can be inspected but cannot be activated:

```bash
python tools/verify_native_manifest.py \
  native/manifests/linux-x64-1.26.33.1.json \
  --allow-incomplete

python tools/activate_verified_manifest.py \
  native/manifests/linux-x64-1.26.33.1.json
```

The `Linux native plugin and live tester` GitHub workflow compiles the actual
Linux x86-64 Endstone entry point
`endstone_dynamic_properties_api.so` and its matching CPython 3.14
tester wheel. While the checked-in native proof is incomplete, the uploaded
artifact is explicitly named `linux-native-gate-closed`, contains a warning,
and refuses to register the service. After the reviewed bridge, manifest, and
stage report pass the same verifier, the unchanged workflow switches to a
`linux-native-verified` artifact. A successful compile never opens the runtime
gate by itself.

Tagged releases also contain a versioned, platform- and compatibility-named
`.so`, the standard PEP 427 tester wheel, and one versioned ZIP containing both
files under their install-ready names. Gate-closed filenames remain visibly
marked `gate-closed`; the release workflow removes that mode only after the
same native verifier reports a complete proof.

Linux native release assets are built on the Endstone-supported Ubuntu 22.04
floor and rejected during packaging if either the plugin or tester bridge
imports a glibc symbol newer than `GLIBC_2.35`. The compatibility-qualified
`.so` and ZIP filenames include `glibc-2.35`; the installed plugin keeps the
stable `endstone_dynamic_properties_api.so` name.

## Repository map

- `include/endstone_dynamic_properties/`: public C++ ABI and native gate.
- `src/`: portable implementation and guarded plugin boundary.
- `python/endstone_dynamic_properties/`: pure Python reference API.
- `native/manifests/`: per-platform exact-binary proof manifests.
- `native/probes/`: complete disposable-world acceptance matrix.
- `tools/`: hashing, verification, probe validation, and activation.
- `tests/`: C++ and Python regression suites.
- `examples/`: complete-control examples.

## Safety policy

This repository never includes or redistributes BDS executables, PDB files, private reconstructed headers, full symbol dumps, decompiler output, player database contents, or world LevelDB data. Public manifests contain only the minimum reviewed identity, RVA/fingerprint, contract, and probe evidence needed to bind the bridge to one exact binary.
