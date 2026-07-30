# Building the exact native Dynamic Properties API

A normal source build produces the portable core and guarded boundary. It does not produce a usable complete-control native plugin.

## Prerequisites

- Official BDS package `1.26.33.1` for the target platform.
- Endstone `v0.11.6` dependency graph through Conan 2.
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

Copy only the verified executable SHA-256 and size into the matching manifest.

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

Create a Conan 2 default profile once if the machine does not already have one:

```bash
conan profile detect
```

```bash
conan install . -of build-conan --build=missing \
  -s build_type=Release \
  -o bds_build=1.26.33

cmake -S . -B build-exact \
  -DCMAKE_TOOLCHAIN_FILE=build-conan/conan_toolchain.cmake \
  -DCMAKE_BUILD_TYPE=Release \
  -DENDSTONE_DYNAMIC_PROPERTIES_BUILD_PLUGIN=ON \
  -DENDSTONE_DYNAMIC_PROPERTIES_BUILD_TESTS=ON \
  -DENDSTONE_DYNAMIC_PROPERTIES_VERIFIED_NATIVE_BRIDGE=ON \
  -DENDSTONE_BDS_BUILD=1.26.33 \
  -DENDSTONE_BDS_PACKAGE=1.26.33.1

cmake --build build-exact --parallel
ctest --test-dir build-exact --output-on-failure
```

Configure fails if the reviewed bridge source is absent. Runtime registration still fails if the running binary identity or generated gate differs from the activated proof.
