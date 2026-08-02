# Validation results

Release metadata: `0.1.0-alpha.2`<br>
Working-tree validation date: `2026-08-02`

## Passed locally

- Project metadata consistency verification.
- Native fail-closed source verification.
- Linux and Windows blocked-manifest structural inspection.
- Rejection of incomplete native activation.
- Strict public/tool manifest-verifier parity, including omitted proof sections and duplicate symbols.
- Strict stage-probe rejection of empty result sets and non-hexadecimal evidence hashes.
- Python 3.11 tests: `115/115` passed.
- MSVC 19.44 C++20 Release compilation with warnings as errors.
- Release CTest: `2/2` passed.
- Clean installed-SDK `find_package()` consumer build and execution.
- C++ complete-control example execution.
- Python wheel and source distribution build.
- `twine check` for both Python distributions.
- Pure-Python wheel isolated installation and functional smoke test.
- Portable Windows SDK installation, installed-tool smoke test, and repeatable byte-identical ZIP packaging.
- CMake preset parsing and GitHub workflow YAML parsing.
- MSVC C++20 syntax compilation of the live pybind bridge against the exact
  pinned Endstone `0.11.6` headers, with project warnings treated as errors.
- Alpha.2 release metadata/tag consistency and native fail-closed policy.
- Tester bridge-loader, command-schema, checkpoint/report, durable
  cleanup-ownership, mutation-serialization, creation-race,
  process-incarnation, persistence-ambiguity, and native-wheel machine-tag
  regression tests.
- All-target configuration validation, existing-property inventory, successful
  edit/readback, external-event drain/report, and Linux workflow gate-mode
  regression tests.

## Configured CI coverage

The repository workflows are configured to repeat policy and Python tests on
Python 3.10, 3.11, and 3.14; build/test with GCC, Clang, and MSVC; run Clang
AddressSanitizer and UndefinedBehaviorSanitizer; validate the installed CMake
consumer; build/check Python distributions; and compile/inspect the Linux
x86-64 Endstone `.so` plus matching CPython 3.14 tester wheel.

These hosted jobs must pass on the exact commit before it is tagged. Earlier bundle results are not treated as validation of the modified working tree.

## Portable behavior covered

- All 12 target kinds and inventory-section validation.
- Boolean, finite number, strictly validated UTF-8 string, and Vector3 values.
- CRUD, bulk operations, transfers, migration, and typed export/import.
- Duplicate-key and malformed-import rejection.
- Collection existence, byte count, and optimistic revisions.
- Independent rename/migration destination guards and reconciled same-collection transfer revisions.
- Plugin collection isolation, including empty-identity denial, and raw-administrator access.
- Administrative authorization for forced revision bypass.
- Cross-target atomic transactions, rollback, one correlation ID, and committed after-state events.
- Resulting collection property-count limits across individual and transaction writes.
- Concurrent and listener-reentrant limit enforcement across shared adapter coordinators.
- Immutable Python request/snapshot mappings and JSON surrogate/overflow rejection.
- API and external mutation events, fail-closed listener isolation, origin preservation, and audits.
- Audit-sink failure isolation without replacing committed results.
- Target-unavailable and capability-denied failures.

## Native status

The exact BDS bridge is not activated and no deployable native DLL/SO is
produced. The hosted native workflow may emit a visibly marked gate-closed ELF
for build-graph validation; it refuses service registration.

The official Windows and Linux executable SHA-256/size identities are recorded
and enforced by both manifest verification and the compiled closed gate. They
are identity evidence only and do not satisfy any capability proof.

Still required independently for Windows and Linux BDS package `1.26.33.1`:

- exact symbol RVAs and fingerprints;
- signature and behavior review for every required symbol;
- offline-player and stored-entity storage contract review;
- supported block dynamic-property contract review;
- external set/remove/clear hook review;
- reviewed `src/verified_bds_26_30_adapter.cpp` source and SHA-256;
- CPython 3.14 compilation/import validation of the live tester bridge and its
  platform wheel in the exact staged server package;
- complete disposable-world stage probe with retained evidence.

The plugin refuses to register `endstone:dynamic-properties:v1` until all proof gates pass together.
