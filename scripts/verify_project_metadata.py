#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIRECTORIES = {".git", ".pytest_cache", ".venv", "dist"}
FORBIDDEN_SUFFIXES = {
    ".i64",
    ".id0",
    ".id1",
    ".id2",
    ".nam",
    ".til",
    ".pdb",
    ".dmp",
    ".core",
    ".ldb",
    ".sst",
}
FORBIDDEN_FILENAMES = {
    "bedrock_server",
    "bedrock_server.exe",
    "bedrock_server_symbols.debug",
}


def source_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if any(
            part in GENERATED_DIRECTORIES or part.startswith("build")
            for part in relative.parts
        ):
            continue
        if path.is_file():
            files.append(path)
    return files


def capture(path: str, pattern: str, label: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        raise SystemExit(f"Could not find {label} in {path}")
    return match.group(1)


def main() -> int:
    source = json.loads((ROOT / "SOURCE_RELEASE.json").read_text(encoding="utf-8"))
    release = source["version"]
    match = re.fullmatch(r"(\d+\.\d+\.\d+)(?:-(alpha|beta|rc)\.(\d+))?", release)
    if not match:
        raise SystemExit(f"Unsupported release version: {release}")
    base, phase, serial = match.groups()
    python_version = (
        base
        if phase is None
        else f"{base}{ {'alpha': 'a', 'beta': 'b', 'rc': 'rc'}[phase] }{serial}"
    )

    compatibility = json.loads(
        (ROOT / "compatibility/versions.json").read_text(encoding="utf-8")
    )
    checks = {
        "CMake project version": (
            capture(
                "CMakeLists.txt",
                r"project\([^\n]*\bVERSION\s+([^\s\)]+)",
                "project version",
            ),
            base,
        ),
        "Python project version": (
            capture("pyproject.toml", r'^version\s*=\s*"([^"]+)"', "Python version"),
            python_version,
        ),
        "Python package version": (
            capture(
                "python/endstone_dynamic_properties/__init__.py",
                r'^__version__\s*=\s*"([^"]+)"',
                "__version__",
            ),
            python_version,
        ),
        "tester project version": (
            capture(
                "examples/python/dynamic_properties_tester_plugin/pyproject.toml",
                r'^version\s*=\s*"([^"]+)"',
                "tester Python version",
            ),
            python_version,
        ),
        "tester required Python": (
            capture(
                "examples/python/dynamic_properties_tester_plugin/pyproject.toml",
                r'^requires-python\s*=\s*"([^"]+)"',
                "tester required Python",
            ),
            "==3.14.*",
        ),
        "tester report version": (
            capture(
                "examples/python/dynamic_properties_tester_plugin/src/"
                "endstone_dynamic_properties_tester/report.py",
                r'^TESTER_VERSION\s*=\s*"([^"]+)"',
                "tester report version",
            ),
            python_version,
        ),
        "tester README API version": (
            capture(
                "examples/python/dynamic_properties_tester_plugin/README.md",
                r"Properties API `([^`]+)`",
                "tester README API version",
            ),
            python_version,
        ),
        "C++ release version": (
            capture(
                "include/endstone_dynamic_properties/version.h",
                r'#define\s+ENDSTONE_DYNAMIC_PROPERTIES_VERSION\s+"([^"]+)"',
                "C++ release version",
            ),
            release,
        ),
        "README release": (
            capture("README.md", r"\*\*Release:\*\* `v([^`]+)`", "README release"),
            release,
        ),
        "build status version": (
            capture(
                "BUILD_STATUS.md", r"Version:\s*\*\*([^*]+)\*\*", "build status version"
            ),
            release,
        ),
        "validation results version": (
            capture(
                "VALIDATION_RESULTS.md",
                r"Release metadata:\s*`([^`]+)`",
                "validation results version",
            ),
            release,
        ),
        "security policy version": (
            capture(
                "SECURITY.md",
                r"Version `([^`]+)` is a portable SDK/reference release",
                "security policy version",
            ),
            release,
        ),
        "compatibility API": (compatibility["api"], base),
        "compatibility service ABI": (
            compatibility["service"],
            "endstone:dynamic-properties:v1",
        ),
        "service ABI": (source["service"], "endstone:dynamic-properties:v1"),
    }
    failures = [
        f"{label}: expected {expected!r}, got {actual!r}"
        for label, (actual, expected) in checks.items()
        if actual != expected
    ]
    if source.get("schema") != 1:
        failures.append("source release schema must be 1")
    cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
    bridge = (ROOT / "src/live_python_bindings.cpp").read_text(encoding="utf-8")
    wheel_builder = (ROOT / "scripts/build_test_wheel.py").read_text(encoding="utf-8")
    conanfile = (ROOT / "conanfile.py").read_text(encoding="utf-8")
    tester_plugin = (
        ROOT / "examples/python/dynamic_properties_tester_plugin/src/"
        "endstone_dynamic_properties_tester/plugin.py"
    ).read_text(encoding="utf-8")
    tester_loader = (
        ROOT / "examples/python/dynamic_properties_tester_plugin/src/"
        "endstone_dynamic_properties_tester/_bridge_loader.py"
    ).read_text(encoding="utf-8")
    tester_targets = (
        ROOT / "examples/python/dynamic_properties_tester_plugin/src/"
        "endstone_dynamic_properties_tester/targets.py"
    ).read_text(encoding="utf-8")
    linux_workflow = (
        ROOT / ".github/workflows/linux-native.yml"
    ).read_text(encoding="utf-8")
    if (
        "find_package(Python 3.14 EXACT REQUIRED COMPONENTS Interpreter Development.Module)"
        not in cmake
    ):
        failures.append("live bridge must require the exact CPython 3.14 ABI")
    if "ENDSTONE_DYNAMIC_PROPERTIES_PYTHON_VERSION" not in bridge:
        failures.append("live bridge version must come from release metadata")
    if "REQUIRED_PYTHON = (3, 14)" not in wheel_builder:
        failures.append("tester wheel builder must require CPython 3.14")
    if not all(
        marker in wheel_builder
        for marker in ("validate_bridge_binary", "machine != 0x8664", "machine != 62")
    ):
        failures.append(
            "tester wheel builder must validate the bridge machine architecture"
        )
    if 'check_min_cppstd(self, "20")' not in conanfile:
        failures.append("Conan dependency resolution must require C++20")
    if "version = TESTER_VERSION" not in tester_plugin:
        failures.append("tester plugin version must use the report package version")
    required_live_exports = (
        "list_collections",
        "start_external_watch",
        "drain_external_events",
        "external_watch_status",
        "stop_external_watch",
    )
    if not all(f'"{name}"' in tester_loader for name in required_live_exports):
        failures.append("tester loader is missing inventory/external-watch exports")
    target_kinds = (
        "world",
        "online_player",
        "offline_player",
        "loaded_entity",
        "stored_entity",
        "player_inventory_slot",
        "player_armor_slot",
        "player_offhand_slot",
        "player_ender_chest_slot",
        "block_container_slot",
        "dropped_item",
        "block_entity",
    )
    if not all(f'"{kind}"' in tester_targets for kind in target_kinds):
        failures.append("tester target template must represent all 12 target families")
    required_linux_workflow_markers = (
        "ubuntu-24.04",
        'python-version: "3.14"',
        "ENDSTONE_DYNAMIC_PROPERTIES_BUILD_PLUGIN=ON",
        "ENDSTONE_DYNAMIC_PROPERTIES_BUILD_LIVE_PYTHON=ON",
        "endstone_dynamic_properties_bds_1_26_33.so",
        "linux-native-${{ steps.gate.outputs.mode }}",
        "GATE CLOSED:",
    )
    if not all(marker in linux_workflow for marker in required_linux_workflow_markers):
        failures.append("Linux native workflow is missing an exact build/gate marker")
    if source.get("release_kind") != "portable-core-and-reference-prerelease":
        failures.append(
            "source release kind must identify the portable/reference prerelease"
        )
    if source.get("native_plugin_included") is not False:
        failures.append("blocked alpha must declare native_plugin_included=false")
    if source.get("supported_bds_packages") != ["1.26.33.1"]:
        failures.append("supported BDS package must be exactly 1.26.33.1")
    if source.get("supported_bds_runtime") != ["26.33"]:
        failures.append("supported BDS runtime must be exactly 26.33")
    if source.get("endstone_tags") != ["v0.11.6"]:
        failures.append("supported Endstone tag must be exactly v0.11.6")
    adapters = compatibility.get("adapters")
    if not isinstance(adapters, list) or len(adapters) != 1:
        failures.append("compatibility metadata must contain exactly one adapter")
    else:
        adapter = adapters[0]
        if adapter.get("bds_package") != "1.26.33.1":
            failures.append("compatibility BDS package must be exactly 1.26.33.1")
        if adapter.get("bds_runtime") != "26.33":
            failures.append("compatibility BDS runtime must be exactly 26.33")
        if adapter.get("endstone") != "0.11.6":
            failures.append("compatibility Endstone version must be exactly 0.11.6")
    for platform in ("linux-x64", "windows-x64"):
        manifest = json.loads(
            (ROOT / f"native/manifests/{platform}-1.26.33.1.json").read_text(
                encoding="utf-8"
            )
        )
        if manifest.get("status") != "blocked":
            failures.append(f"{platform} source manifest must remain blocked")
        if manifest.get("platform") != platform:
            failures.append(f"{platform} manifest platform mismatch")
        if manifest.get("bds_package_version") != "1.26.33.1":
            failures.append(f"{platform} manifest package mismatch")
        if manifest.get("runtime_bds") != "26.33":
            failures.append(f"{platform} manifest runtime mismatch")
        if manifest.get("endstone_version") != "0.11.6":
            failures.append(f"{platform} manifest Endstone mismatch")
    forbidden = [
        path
        for path in source_files()
        if path.suffix.lower() in FORBIDDEN_SUFFIXES
        or path.name.lower() in FORBIDDEN_FILENAMES
        or (
            path.suffix.lower() in {".zip", ".tar", ".gz"}
            and "bedrock" in path.name.lower()
        )
    ]
    if forbidden:
        names = ", ".join(str(path.relative_to(ROOT)) for path in forbidden[:10])
        failures.append(
            f"private binary-analysis or world-storage artifacts are present: {names}"
        )
    if failures:
        raise SystemExit("Metadata verification failed:\n- " + "\n- ".join(failures))
    print(f"Verified metadata for endstone-dynamic-properties-api {release}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
