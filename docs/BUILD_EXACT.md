# Building the exact native Dynamic Properties API

A normal source build produces the portable core and guarded boundary. It does not produce a usable complete-control native plugin.

## Prerequisites

- Official BDS package `1.26.33.1` for the target platform.
- Endstone `v0.11.6` dependency graph through Conan 2.
- CPython `3.14` interpreter and development files for the in-game tester bridge.
- A private symbol/ABI analysis workspace.
- A disposable stage world and test clients/accounts.
- Storage test records created solely for the probe.

Never commit the BDS executable, PDB, reconstructed private headers, full symbol dumps, decompiler output, world database, or player records.

## 1. Hash the package and executable

```bash
python tools/hash_bds_package.py /private/path/bedrock-server-1.26.33.1.zip \
  --platform linux-x64 \
  --json-out /private/path/linux-executable-identity.json
```

Confirm that the verified executable SHA-256 and size exactly match the identity
already recorded in the matching manifest. Stop on any difference; do not
rewrite the manifest to accept another binary or package revision.

## 2. Complete symbol and contract review

Follow `docs/NATIVE_SYMBOL_AUDIT.md` and the storage/hook documents. Every required symbol and ABI contract must be complete in the same manifest.

## 3. Implement the unified bridge

Create `src/verified_bds_26_30_adapter.cpp`. It must implement every target and capability in `DynamicPropertyCapabilities::completeControl()`. Record its SHA-256 and review evidence in the manifest.

## 4. Run the complete stage probe

Complete the platform report and validate it:

```bash
python tools/validate_stage_probe_report.py \
  native/probes/linux-x64-1.26.33.1-stage-probe.json
```

## 5. Open the activation gate

```bash
python tools/verify_native_manifest.py \
  native/manifests/linux-x64-1.26.33.1.json

python tools/activate_verified_manifest.py \
  native/manifests/linux-x64-1.26.33.1.json
```

## 6. Build through Conan

The checked-in Linux profile pins the Clang 18/libc++ toolchain required by
Endstone v0.11.6. On Ubuntu 24.04, install it and then register Endstone's
source-recipe remote:

```bash
sudo apt-get update
sudo apt-get install --no-install-recommends \
  clang-18 libc++-18-dev libc++abi-18-dev
conan remote add endstone https://conan.cloudsmith.io/endstone/conan/ \
  --index 0 --force
```

The Endstone remote supplies the project-specific `funchook` and RakNet source
recipes that are not published by Conan Center.

```bash
conan install . -of build-conan --build=missing \
  -pr:h native/profiles/linux-x64 \
  -pr:b native/profiles/linux-x64 \
  -o '&:bds_build=1.26.33'

cmake -S . -B build-exact \
  -DCMAKE_TOOLCHAIN_FILE=build-conan/conan_toolchain.cmake \
  -DCMAKE_BUILD_TYPE=Release \
  -DENDSTONE_DYNAMIC_PROPERTIES_BUILD_PLUGIN=ON \
  -DENDSTONE_DYNAMIC_PROPERTIES_BUILD_LIVE_PYTHON=ON \
  -DENDSTONE_DYNAMIC_PROPERTIES_BUILD_TESTS=ON \
  -DENDSTONE_DYNAMIC_PROPERTIES_VERIFIED_NATIVE_BRIDGE=ON \
  -DENDSTONE_BDS_BUILD=1.26.33 \
  -DENDSTONE_BDS_PACKAGE=1.26.33.1

cmake --build build-exact --parallel
ctest --test-dir build-exact --output-on-failure
```

Configure fails if the reviewed bridge source is absent. Runtime registration still fails if the running binary identity or generated gate differs from the activated proof.

## 7. Stage the plugin and build the tester wheel

Install with the same CPython 3.14 selected during configuration, then point the
wheel builder at the staged, package-local extension:

```bash
cmake --install build-exact --prefix stage/exact

python3.14 scripts/build_test_wheel.py \
  --bridge "stage/exact/python/_endstone_dynamic_properties_live$(python3.14-config --extension-suffix)" \
  --stage-dir stage/exact
```

On Windows, pass the staged
`python/_endstone_dynamic_properties_live.cp314-win_amd64.pyd` path instead.
The builder rejects a bridge from another stage, Python ABI, host binary
format, or x86-64 machine architecture, then copies the completed tester wheel
into `stage/exact/plugins/`.

## Hosted Linux compilation

`.github/workflows/linux-native.yml` repeats the Conan, CMake, CTest, install,
ELF inspection, and tester-wheel build on Ubuntu x86-64 with CPython 3.14. It
classifies the native proof before configuring CMake:

- incomplete proof builds `linux-native-gate-closed` for compilation and
  packaging validation only; the plugin refuses service registration;
- complete proof requires the verified adapter source and builds
  `linux-native-verified` with the same runtime checks still active.

Every staged file is covered by `evidence/SHA256SUMS.txt`, and
`evidence/BUILD_MODE.txt` prevents a closed-gate artifact from being mistaken
for an installable API.
