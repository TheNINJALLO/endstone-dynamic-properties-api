# Contributing

Thank you for helping improve Endstone Dynamic Properties API. The current public milestone is a portable C++ SDK and pure-Python reference implementation. The native BDS bridge remains fail-closed until its complete proof gate passes.

## Development setup

Required tools:

- Python 3.10 or newer;
- CMake 3.20 or newer;
- a C++20 compiler (MSVC, GCC, or Clang).

Create a virtual environment, install the test extra, and run the portable suites:

```bash
python -m venv .venv
python -m pip install -e ".[test]"
python -m pytest -q tests/python

cmake --preset portable-release
cmake --build --preset portable-release
ctest --preset portable-release
```

Before submitting a change, also run:

```bash
python scripts/verify_project_metadata.py
python tools/verify_fail_closed.py
python tools/verify_native_manifest.py native/manifests/linux-x64-1.26.33.1.json --allow-incomplete
python tools/verify_native_manifest.py native/manifests/windows-x64-1.26.33.1.json --allow-incomplete
```

## Change expectations

- Add C++ and Python regression coverage when behavior exists in both APIs.
- Preserve collection isolation, optimistic-revision, transaction, event, and audit semantics.
- Keep unsupported native paths fail-closed; never replace a missing proof with a guessed address or signature.
- Update `CHANGELOG.md` for user-visible changes.
- Keep commits focused and avoid committing generated build or release artifacts.

## Native evidence policy

Do not commit or attach BDS executables, private symbols, decompiler databases, full dumps, world databases, player records, private stage evidence, or generated verified bridge source. Public native work should contain only the minimum redacted manifest structure and documentation needed to review the gate.

Native activation changes require an exact executable identity, complete symbol and ABI review, storage and hook verification, a reviewed bridge hash, and a passing disposable-world probe for each platform. See `docs/BUILD_EXACT.md` and `docs/STAGE_PROBE.md`.

## Pull requests

Describe the behavior changed, the safety impact, and the commands used to validate it. A pull request that weakens a native gate or changes persistence semantics should include a focused threat/failure analysis.
