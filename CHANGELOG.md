# Changelog

## Unreleased

No changes yet.

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

[Unreleased]: https://github.com/TheNINJALLO/endstone-dynamic-properties-api/compare/v0.1.0-alpha.1...HEAD
[0.1.0-alpha.1]: https://github.com/TheNINJALLO/endstone-dynamic-properties-api/releases/tag/v0.1.0-alpha.1
