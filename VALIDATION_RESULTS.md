# Validation results

Release metadata: `0.1.0-alpha.1`<br>
Working-tree validation date: `2026-07-29`

## Passed locally

- Project metadata consistency verification.
- Native fail-closed source verification.
- Linux and Windows blocked-manifest structural inspection.
- Rejection of incomplete native activation.
- Strict public/tool manifest-verifier parity, including omitted proof sections and duplicate symbols.
- Strict stage-probe rejection of empty result sets and non-hexadecimal evidence hashes.
- Python 3.11 package compilation and tests: `51/51` passed.
- MSVC 19.44 C++20 Debug compilation with warnings as errors.
- MSVC 19.44 C++20 Release compilation with warnings as errors.
- Debug CTest: `2/2` passed.
- Release CTest: `2/2` passed.
- Clean installed-SDK `find_package()` consumer build and execution.
- C++ complete-control example execution.
- Python wheel and source distribution build.
- `twine check` for both Python distributions.
- Pure-Python wheel isolated installation and functional smoke test.
- Portable Windows SDK installation, installed-tool smoke test, and repeatable byte-identical ZIP packaging.
- CMake preset parsing and GitHub workflow YAML parsing.

## Configured CI coverage

The repository workflow is configured to repeat policy and Python tests on Python 3.10, 3.11, and 3.14; build/test with GCC, Clang, and MSVC; run Clang AddressSanitizer and UndefinedBehaviorSanitizer; validate the installed CMake consumer; build/check Python distributions; and upload test artifacts.

These hosted jobs remain pending until the repository is published and its first GitHub Actions run completes. Earlier bundle results are not treated as validation of the modified working tree.

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

The exact BDS bridge is not activated and no installable native DLL/SO is produced.

Still required independently for Windows and Linux BDS package `1.26.33.1`:

- executable SHA-256 and size;
- exact symbol RVAs and fingerprints;
- signature and behavior review for every required symbol;
- offline-player and stored-entity storage contract review;
- supported block dynamic-property contract review;
- external set/remove/clear hook review;
- reviewed `src/verified_bds_26_30_adapter.cpp` source and SHA-256;
- complete disposable-world stage probe with retained evidence.

The plugin refuses to register `endstone:dynamic-properties:v1` until all proof gates pass together.
