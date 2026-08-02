# Build status

Version: **0.1.0-alpha.2**

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
- GCC, Clang, and sanitizer hosted jobs: configured and required to pass on `main` before tagging.
- MSVC 19.44 Debug and Release builds with warnings as errors: validated.
- C++ and Python tests: passing locally (MSVC Debug/Release and Python 3.11).
- Installed CMake package consumer (`EndstoneDynamicProperties::core`): passing.
- Python wheel and source-distribution build metadata: configured.
- GitHub CI and draft portable-release workflows: configured.
- Operator-only CPython 3.14 live tester, atomic reports, guarded cleanup, and
  exact-stage wheel packager: implemented.
- Configured live acceptance targets cover all 12 target families; read-only
  inventory, successful-edit checks, and bounded external-mutation capture are
  implemented.
- Hosted Linux x86-64 `.so` plus CPython 3.14 tester-wheel compilation is
  configured. Until native proof activation, its artifact is visibly marked
  gate-closed and is not deployable as a working service.

## Exact native bridge

- Target BDS package: `1.26.33.1`.
- Runtime: `26.33`.
- Endstone: `0.11.6`.
- Windows and Linux archive identities: pinned.
- Exact Windows and Linux executable SHA-256/size identities: recorded and
  enforced; identity evidence alone does not activate the native gate.
- Required symbol manifest: present, unresolved.
- Offline-player storage contract: not yet behavior-verified.
- Stored-entity storage contract: not yet behavior-verified.
- Block dynamic-property contract: not yet behavior-verified.
- External set/remove/clear hooks: not yet behavior-verified.
- Reviewed native bridge source: absent.
- Complete stage probe: not passed.
- Live service registration: disabled by design.

This alpha is a complete portable API/reference and activation package. It is
not yet an installable working native server plugin. The portable release
workflow deliberately publishes no native DLL/SO; the separate native
readiness workflow emits a non-deployable gate-closed `.so` only to validate
the exact Linux compilation and packaging graph.
