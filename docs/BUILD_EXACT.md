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

On the Linux stage server, collect the narrow identity-bound symbol discovery
report directly from the installed executable:

```bash
python3 tools/collect_linux_native_evidence.py /home/container/bedrock_server \
  --json-out /home/container/linux-native-evidence.json
```

The command stops before symbol collection if the filename, SHA-256, or size
does not match the pinned manifest. It emits only matching symbol candidates
and ELF/tool metadata; it does not copy the executable, disassembly, full symbol
table, world data, or player records. For a stripped executable it includes
only NUL-terminated DynamicProperties-related diagnostic/RTTI strings and their
ELF RVAs, which provide bounded cross-reference anchors for private analysis.
Keep this report out of source control and return it to the private native
review workspace. Candidate or string discovery alone does not prove a
signature, ABI contract, or behavior. The ELF scan uses only the Python
standard library; `c++filt` is optional and exact mangled names are kept when it
is unavailable in a minimal game-server container.

In the private review workspace, focused code cross-references can then be
resolved from the stripped executable. This second report contains instruction
bytes and must also remain out of source control. Installing `capstone` adds
instruction validation and bounded disassembly context; the identity and unwind
boundary checks do not depend on it.

```bash
python tools/analyze_linux_dynamic_property_xrefs.py \
  /private/path/bedrock_server \
  /private/path/linux-native-evidence.json \
  --json-out /private/path/linux-dynamic-property-xrefs.json
```

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
Endstone v0.11.6. Release binaries must be compiled on Ubuntu 22.04 so they do
not import glibc symbols newer than the supported `GLIBC_2.35` floor. Install
LLVM 18 from LLVM's Jammy repository, then register Endstone's source-recipe
remote:

```bash
curl -fsSL https://apt.llvm.org/llvm-snapshot.gpg.key \
  -o /tmp/llvm-snapshot.gpg.key
gpg --dearmor --output /tmp/apt.llvm.org.gpg \
  /tmp/llvm-snapshot.gpg.key
sudo install -m 0644 /tmp/apt.llvm.org.gpg \
  /usr/share/keyrings/apt.llvm.org.gpg
echo 'deb [signed-by=/usr/share/keyrings/apt.llvm.org.gpg] https://apt.llvm.org/jammy/ llvm-toolchain-jammy-18 main' \
  | sudo tee /etc/apt/sources.list.d/llvm-18.list
sudo apt-get update
sudo apt-get install --no-install-recommends \
  clang-18 clang-tools-18 libc++-18-dev libc++abi-18-dev ninja-build
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

cmake -S . -B build-exact -G Ninja \
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

bridge="stage/exact/python/_endstone_dynamic_properties_live$(python3.14-config --extension-suffix)"
runtime_args=()
for soname in libc++.so.1 libc++abi.so.1 libunwind.so.1; do
  runtime_path="$(ldd "$bridge" | awk -v soname="$soname" \
    '$1 == soname { print $3; exit }')"
  test -s "$runtime_path"
  runtime_args+=(--runtime-library "$runtime_path")
done
python3.14 scripts/build_test_wheel.py \
  --bridge "$bridge" \
  --stage-dir stage/exact \
  "${runtime_args[@]}"
```

On Windows, pass the staged
`python/_endstone_dynamic_properties_live.cp314-win_amd64.pyd` path instead.
The builder rejects a bridge from another stage, Python ABI, host binary
format, or x86-64 machine architecture, then copies the completed tester wheel
into `stage/exact/plugins/`. Linux wheels must receive exactly the LLVM 18
`libc++.so.1`, `libc++abi.so.1`, and `libunwind.so.1` closure; the builder
packages them beside the bridge with their license.

## Hosted Linux compilation

`.github/workflows/linux-native.yml` repeats the Conan, CMake, CTest, install,
ELF inspection, and tester-wheel build on Ubuntu 22.04 x86-64 with CPython
3.14. It rejects a plugin, tester bridge, or bundled LLVM runtime whose highest
imported glibc symbol exceeds `GLIBC_2.35`. It also extracts the wheel and
proves the dynamic loader resolves the C++ runtime from its package-local
directory before classifying the native proof:

- an exact-hash experimental bridge builds `linux-native-experimental-live`
  with truthful per-target capabilities for stage testing;
- source without either bridge builds `linux-native-gate-closed` for
  compilation and packaging validation only;
- complete proof requires the verified adapter source and builds
  `linux-native-verified` with the same runtime checks still active.

Every staged file is covered by `evidence/SHA256SUMS.txt`, and
`evidence/BUILD_MODE.txt` prevents a closed-gate artifact from being mistaken
for an installable API.

## Native release assets

The tagged-release workflow calls the same hosted Linux build and publishes:

- `endstone_dynamic_properties_api-<version>-bds-<package>-endstone-<version>-linux-x86_64-glibc-2.35-<mode>.so`;
- the standard
  `endstone_dynamic_properties_tester-<python-version>-cp314-cp314-linux_x86_64.whl`;
- `endstone-dynamic-properties-api-<compatibility>-glibc-2.35-<mode>.zip`, containing both
  under `plugins/` with `RELEASE_MANIFEST.json`, mode evidence, and checksums.

Inside the ZIP the installed entry point always uses the stable
`plugins/endstone_dynamic_properties_api.so` name. The wheel contains exactly
one package-local CPython 3.14 Linux bridge built from the same CMake stage.
The native release packager independently checks both ELF64 x86-64 boundaries,
the wheel ABI tag, build mode, version, and compatibility metadata before it
creates the release assets.
