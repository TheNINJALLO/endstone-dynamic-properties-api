# Changelog

## Unreleased

## 0.1.0-alpha.4 - 2026-08-02

### Fixed

- Made the Linux CPython 3.14 tester wheel self-contained by bundling its
  pinned LLVM 18 `libc++`, `libc++abi`, and `libunwind` runtime closure.
- Added an origin-relative loader path and CI checks proving the wheel resolves
  all three C++ runtime libraries from its own package instead of the host.

## 0.1.0-alpha.3 - 2026-08-02

### Added

- Added an exact-SHA experimental Linux adapter for real world,
  online-player, and loaded-entity dynamic properties on BDS `1.26.33.1`.
- Added live inventory/CRUD/revision/bulk/transfer/migration/import operations,
  rollback transactions, and BDS persistence-lifecycle handoff.
- Added cancellable external set/remove/clear interception for mapped live
  targets and exposed truthful partial capabilities to the tester.
- Added an operator-only raw native hook probe plus an automated two-boot
  official-BDS acceptance gate covering live world CRUD, interception,
  cancellation, cleanup, and restart persistence.
- Added built-in ELF evidence and dynamic-property xref analysis tools for the
  stripped official Linux server.

### Changed

- Native artifacts are now named `experimental-live` and still enforce the
  Ubuntu 22.04 / `GLIBC_2.35` compatibility ceiling.
- Bumped the plugin, API package, and bound CPython 3.14 tester to alpha.3.

### Changed

- Moved Linux release builds to the Ubuntu 22.04 compatibility floor, added a
  `GLIBC_2.35` import ceiling for both the plugin and tester bridge, and encoded
  that baseline in release filenames and manifests.
- Selected cpptrace's explicit Conan libunwind backend on Linux so its Clang
  18/libc++ build does not depend on host unwind auto-detection.
- Renamed the installed Linux plugin to the stable
  `endstone_dynamic_properties_api.so` entry-point name.
- Added canonical versioned Linux release assets: a compatibility-qualified
  `.so`, its CPython 3.14 tester wheel, and a deterministic install-layout ZIP
  containing both. Gate-closed assets remain explicitly named as such.
- Added the Linux plugin/tester build to the guarded draft-release workflow.

## 0.1.0-alpha.2 - 2026-07-30

### Added

- Recorded and enforced the exact Windows and Linux BDS executable identities
  while keeping every native capability gate closed.
- Added cross-bound validation between native manifests and their complete
  stage-probe reports.
- Added a package-local CPython 3.14 bridge and operator-only in-game tester for
  live CRUD, successful edit, revision, cleanup, and restart-persistence
  acceptance checks across all 12 configurable target families.
- Added atomic tester checkpoints, integrity-sealed reports, guarded recovery,
  and an exact-stage native wheel packager.
- Added read-only tester-visible collection inventory and a bounded observer for
  before/after mutations intercepted from Script API or other native callers.
- Added a hosted Linux x86-64 build that emits the Endstone `.so` and matching
  CPython 3.14 tester wheel, with unmistakable gate-closed versus verified
  artifact modes.

### Fixed

- Corrected verified-adapter factory linkage and made the provider and tester
  bridge share one compiled activation-gate implementation.
- Required the exact CPython ABI and C++20 Conan dependency graph for native
  builds.
- Preserved tester cleanup ownership until remove/clear absence is confirmed
  and durably flushed, guarded absent-collection creation races with revision
  zero, and required a different server process for persistence verification.
- Serialized tester mutations, made atomic-report temporary files collision
  resistant, handled PID reuse with a process-incarnation token, and rejected
  tester bridges whose machine architecture disagrees with the wheel tag.
- Cached executable identity inspection so repeated status checks do not hash
  the server executable on the main thread.

## 0.1.0-alpha.1 - 2026-07-29

### Added

- Created one service ABI, `endstone:dynamic-properties:v1`, for both live and stored targets.
- Added world, online/offline player, loaded/stored entity, player item, block-container item, dropped-item, and supported block-entity targets.
- Added bool, number, string, and Vector3 values with validation and deterministic revisions.
- Added get, list, set, bulk set, remove, bulk remove, clear, collection removal, rename, copy, move, export, import, and UUID migration.
- Added plugin collection isolation and privileged raw-administration access.
- Added cross-target atomic transactions, rollback, event cancellation, watches, and audit records.
- Added external native mutation before/after contracts for Script API and other native callers.
- Added offline-player, stored-entity, block dynamic-property, hook, persistence, and crash-safety acceptance requirements to the same native gate.
- Added exact BDS `1.26.33.1` Windows/Linux manifest skeletons and a complete stage-probe template.
- Added C++20 and Python reference implementations and tests.
- Added strict regression coverage for security gates and mutation invariants.
- Added an exported CMake package and clean installed-SDK consumer test.
- Added CMake presets, typed-package metadata, contributor guidance, and a security policy.

### Fixed

- Closed the empty-plugin-ID collection-isolation bypass in the Python reference service.
- Rejected destructive same-source collection renames and property moves in both APIs.
- Restricted forced revision bypass to raw administrative contexts.
- Preserved external mutation origins and unified transaction event/audit correlation IDs.
- Made Python native-manifest and stage-probe verification fail closed on missing proof sections, duplicate symbols, empty probe sets, and invalid evidence hashes.
- Fixed MSVC warnings-as-errors failures in C++ variant visitors.
- Serialized commit-time limit validation across concurrent and reentrant service writes.
- Made Python operation and snapshot mappings defensively immutable.
- Isolated listener failures, failed closed before writes, and preserved post-commit audits.
- Enforced UTF-8 and JSON surrogate correctness at the C++ boundary and contained Python import overflow/encoding errors.
- Hardened release jobs against mutable tags, published-asset replacement, and untested artifacts.
- Enforced independent source/destination revision guards for rename, migration, and same-collection property transfers.
- Isolated audit-sink failures from committed results and exposed explicit failure reporting.
- Kept missing, malformed, and forged verified native manifests fail-closed even during blocked-manifest inspection.
- Normalized exact runtime metadata on the canonical BDS runtime `26.33` and required an exact draft-release asset set.

[Unreleased]: https://github.com/TheNINJALLO/endstone-dynamic-properties-api/compare/v0.1.0-alpha.4...HEAD
[0.1.0-alpha.4]: https://github.com/TheNINJALLO/endstone-dynamic-properties-api/releases/tag/v0.1.0-alpha.4
[0.1.0-alpha.3]: https://github.com/TheNINJALLO/endstone-dynamic-properties-api/releases/tag/v0.1.0-alpha.3
[0.1.0-alpha.2]: https://github.com/TheNINJALLO/endstone-dynamic-properties-api/releases/tag/v0.1.0-alpha.2
[0.1.0-alpha.1]: https://github.com/TheNINJALLO/endstone-dynamic-properties-api/releases/tag/v0.1.0-alpha.1
