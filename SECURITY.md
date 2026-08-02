# Security policy

## Supported releases

Only the latest tagged prerelease is eligible for security fixes. Version `0.1.0-alpha.2` is a portable SDK/reference release; it is not a working native Endstone plugin and must not be represented as one.

## Reporting a vulnerability

Please use the repository's private GitHub Security Advisory form:

`https://github.com/TheNINJALLO/endstone-dynamic-properties-api/security/advisories/new`

Do not open a public issue for collection-isolation bypasses, unsafe persistence behavior, native-hook vulnerabilities, binary-address disclosures, or leaks of player/world data. Include affected versions, a minimal reproduction, impact, and any suggested mitigation. Do not include proprietary BDS binaries, private symbols, or real player/world records.

## Security boundaries

The service enforces collection prefixes and raw-administrator checks using an `AccessContext`. A hosting Endstone provider must create that context from its authenticated plugin/command boundary; arbitrary callers must not be allowed to choose another plugin ID or assert `raw_admin=true`.

The native bridge is intentionally fail-closed. A manifest marked `verified` is not sufficient by itself: executable identity, ABI/symbol evidence, storage and hook contracts, bridge source hash, and the complete stage report must all validate together. Never disable these checks to recover availability.
