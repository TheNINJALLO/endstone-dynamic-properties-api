# Build status

Version: **0.1.0-alpha.5**

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
- C++ and Python tests: passing locally (MSVC Release CTest `2/2` and Python
  `144/144`) and across the hosted compiler/runtime matrix.
- Installed CMake package consumer (`EndstoneDynamicProperties::core`): passing.
- Python wheel and source-distribution build metadata: configured.
- GitHub CI and draft release workflows: configured.
- Operator-only CPython 3.14 live tester, atomic reports, guarded cleanup, and
  exact-stage wheel packager: implemented.
- Configured live acceptance targets cover all 12 target families; read-only
  inventory, successful-edit checks, and bounded external-mutation capture are
  implemented.
- Hosted Linux x86-64 `.so` plus CPython 3.14 tester-wheel compilation is
  configured on the Ubuntu 22.04 / GLIBC 2.35 compatibility floor. Packaging
  rejects newer glibc imports in either native binary or the bundled LLVM 18
  runtime. The tester wheel is self-contained and its loader resolution is
  checked before live acceptance. The artifact is visibly marked
  `experimental-live`.

## Exact native bridge

- Target BDS package: `1.26.33.1`.
- Runtime: `26.33`.
- Endstone: `0.11.6`.
- Windows and Linux archive identities: pinned.
- Exact Windows and Linux executable SHA-256/size identities: recorded and
  enforced; identity evidence alone does not activate the native gate.
- Exact Linux world core RVAs and libc++ value/container ABI: recovered from
  the official executable and bound behind its full SHA-256/size check.
- Online-player and loaded-entity native access: fail-closed after alpha.4 live
  crash evidence identified an invalid actor `EntityContext` registry boundary.
- Offline-player storage contract: not yet behavior-verified.
- Stored-entity storage contract: not yet behavior-verified.
- Block dynamic-property contract: not yet behavior-verified.
- External set/remove/clear hooks: implemented experimentally with funchook;
  a raw-entry-point live probe verifies before/after interception, cancellation,
  absence of the cancelled value, and cleanup on the exact Linux server.
- Reviewed native bridge source: absent.
- Exact Linux experimental world/hook/persistence stage: passed in a disposable
  two-boot BDS run; complete all-target stage probe: not passed.
- Experimental live service registration: enabled for world targets only on
  exact identity match; actor-backed capabilities are explicitly false.
- Live CRUD/list/revision/bulk/transfer/migration/import/rollback: implemented
  for those three targets.
- Offline/stored, item, and block capabilities: disabled and return
  `unsupported`.

This alpha is an installable experimental Linux server plugin plus a matching
CPython 3.14 tester wheel. It is intended to collect live stage evidence and
fix the remaining target paths; it is not a verified complete-control release.
