# Validation results

Release metadata: `0.1.0-alpha.3`<br>
Working-tree validation date: `2026-08-02`

## Passed locally

- Project metadata consistency verification.
- Native fail-closed source verification.
- Linux and Windows blocked-manifest structural inspection.
- Rejection of incomplete native activation.
- Strict public/tool manifest-verifier parity, including omitted proof sections and duplicate symbols.
- Strict stage-probe rejection of empty result sets and non-hexadecimal evidence hashes.
- Python tests: `139/139` passed.
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
- Native release packaging rejects either the plugin or tester bridge when its
  imported glibc symbols exceed `GLIBC_2.35`; the earlier Ubuntu 24.04 artifact
  was confirmed rejected because it imports `GLIBC_2.38`.

## Configured CI coverage

The repository workflows are configured to repeat policy and Python tests on
Python 3.10, 3.11, and 3.14; build/test with GCC, Clang, and MSVC; run Clang
AddressSanitizer and UndefinedBehaviorSanitizer; validate the installed CMake
consumer; build/check Python distributions; and compile/inspect the Linux
x86-64 Endstone `.so` plus matching CPython 3.14 tester wheel.

These hosted jobs must pass on the exact commit before it is tagged. Earlier bundle results are not treated as validation of the modified working tree.

The exact alpha.3 head also passed the Ubuntu 22.04 disposable-server gate on
the official BDS `1.26.33.1` executable. Four integrity-sealed reports cover
existing collection inventory, a 19-check world CRUD/value/revision suite,
native external set/remove/clear interception with cancellation, and a clean
two-process persistence round trip. The resulting plugin and tester bridge
also passed the `GLIBC_2.35` import ceiling.

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

The exact-hash Linux experimental bridge now registers world, online-player,
and loaded-entity capabilities. Hosted CI and tagged releases emit a visibly
marked `experimental-live` ELF, its ABI-matched tester wheel, and a combined
install-layout bundle. The verified complete-control gate remains closed.

The official Windows and Linux executable SHA-256/size identities are recorded
and enforced by both manifest verification and the compiled runtime gate. The
experimental adapter additionally binds the exact Linux world/actor
dynamic-property core and mutation-hook paths. Its disposable Linux world and
hook stage now passes; this is experimental target-scoped evidence and does not
open the all-target complete-control gate.

Still required independently for Windows and Linux BDS package `1.26.33.1`:

- remaining item, block, storage, and persistence symbol contracts;
- signature and behavior review for every verified-release symbol;
- offline-player and stored-entity storage contract review;
- supported block dynamic-property contract review;
- reviewed `src/verified_bds_26_30_adapter.cpp` source and SHA-256;
- complete all-target disposable-world stage probe with retained evidence.

The plugin exposes `complete_control=false` until all proof gates pass together;
unimplemented target capabilities remain false.
