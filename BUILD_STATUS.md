# Build status

Version: **0.1.0-alpha.1**

## Portable unified system

- C++20 core: implemented.
- Pure Python reference package: implemented.
- Service ABI: `endstone:dynamic-properties:v1`.
- All live and stored target types: represented in one model.
- CRUD, bulk operations, transfers, migration, export/import: implemented.
- Optimistic revisions: implemented.
- Cross-target atomic transactions and rollback: implemented in the reference adapter.
- Event cancellation, external-mutation contract, watches, and audits: implemented.
- Commit-time validation is serialized across shared-adapter services; listener failures are isolated and audited.
- GCC, Clang, and sanitizer hosted jobs: configured; pending the first repository CI run.
- MSVC 19.44 Debug and Release builds with warnings as errors: validated.
- C++ and Python tests: passing locally (MSVC Debug/Release and Python 3.11).
- Installed CMake package consumer (`EndstoneDynamicProperties::core`): passing.
- Python wheel and source-distribution build metadata: configured.
- GitHub CI and draft portable-release workflows: configured.

## Exact native bridge

- Target BDS package: `1.26.33.1`.
- Runtime: `26.33`.
- Endstone: `0.11.6`.
- Windows and Linux archive identities: pinned.
- Executable identities: intentionally empty pending private local inspection.
- Required symbol manifest: present, unresolved.
- Offline-player storage contract: not yet behavior-verified.
- Stored-entity storage contract: not yet behavior-verified.
- Block dynamic-property contract: not yet behavior-verified.
- External set/remove/clear hooks: not yet behavior-verified.
- Reviewed native bridge source: absent.
- Complete stage probe: not passed.
- Live service registration: disabled by design.

This alpha is a complete portable API/reference and activation package. It is not yet an installable working native server plugin, and the release workflow deliberately produces no native DLL/SO.
