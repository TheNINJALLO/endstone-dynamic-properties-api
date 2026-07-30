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
    'ExecutableSha256 = ""',
    'ExecutableSize = 0',
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
if "if (!service_->capabilities().completeControl())" not in plugin or "refused to register" not in plugin:
    failures.append("complete-control service registration refusal is missing")
if "BinaryIdentityMismatch" not in adapter or "SymbolValidationFailed" not in adapter:
    failures.append("guarded native adapter failure modes are missing")
if "ENDSTONE_DYNAMIC_PROPERTIES_VERIFIED_NATIVE_BRIDGE" not in cmake:
    failures.append("verified native bridge option is missing")
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
