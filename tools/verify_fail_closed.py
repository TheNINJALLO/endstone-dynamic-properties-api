#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
header = (ROOT / "include/endstone_dynamic_properties/generated/native_manifest_data.h").read_text(encoding="utf-8")
plugin = (ROOT / "src/plugin.cpp").read_text(encoding="utf-8")
adapter = (ROOT / "src/bds_26_30_adapter.cpp").read_text(encoding="utf-8")
cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
failures: list[str] = []
for required in (
    'NativeManifestActivated = false',
    'ExactBuildMatch = false',
    'ExactBinaryHashMatch = false',
    'SymbolsValidated = false',
    'StorageContractsValidated = false',
    'ExternalHooksValidated = false',
    'StageProbePassed = false',
):
    if required not in header:
        failures.append(f"generated header is not closed: {required}")
for required_identity in (
    "4a0b867eee6c24310f405410b17e9794441b81ed8f2976cdd4cef54d0c441829",
    "61995841f21baf9bfab96e0d9b0cb798501dcc9789dab68e496f3b8e3bc83375",
    "207171408ULL",
    "232842872ULL",
):
    if required_identity not in header:
        failures.append(
            f"generated header lacks exact executable identity: {required_identity}"
        )
if (
    "capabilities.completeControl()" not in plugin
    or "hasExperimentalLiveControl(capabilities)" not in plugin
    or "refused to register" not in plugin
):
    failures.append("verified/experimental service registration guards are missing")
if "BinaryIdentityMismatch" not in adapter or "SymbolValidationFailed" not in adapter:
    failures.append("guarded native adapter failure modes are missing")
if "ENDSTONE_DYNAMIC_PROPERTIES_VERIFIED_NATIVE_BRIDGE" not in cmake:
    failures.append("verified native bridge option is missing")
if "if(ENDSTONE_DYNAMIC_PROPERTIES_BUILD_NATIVE_2630)" not in cmake:
    failures.append("guarded native support is not conditional on its build option")
if "#if !ENDSTONE_DYNAMIC_PROPERTIES_NATIVE_2630" not in plugin:
    failures.append("provider code is not compile-guarded when native support is disabled")
for manifest in (ROOT / "native/manifests").glob("*.json"):
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("status") != "blocked":
        failures.append(f"{manifest.name} is not blocked")
    if data.get("stage_probe", {}).get("passed"):
        failures.append(f"{manifest.name} claims a passed probe")
if (ROOT / "src/verified_bds_26_30_adapter.cpp").exists():
    failures.append("unverified native bridge source is present")
if failures:
    raise SystemExit("fail-closed verification failed:\n- " + "\n- ".join(failures))
print("native Dynamic Properties API boundary is fail-closed")
