#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIRECTORIES = {".git", ".pytest_cache", ".venv", "dist"}
FORBIDDEN_SUFFIXES = {
    ".i64", ".id0", ".id1", ".id2", ".nam", ".til", ".pdb",
    ".dmp", ".core", ".ldb", ".sst",
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
        if any(part in GENERATED_DIRECTORIES or part.startswith("build") for part in relative.parts):
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
    python_version = base if phase is None else f"{base}{ {'alpha':'a','beta':'b','rc':'rc'}[phase] }{serial}"

    compatibility = json.loads(
        (ROOT / "compatibility/versions.json").read_text(encoding="utf-8")
    )
    checks = {
        "CMake project version": (
            capture("CMakeLists.txt", r"project\([^\n]*\bVERSION\s+([^\s\)]+)", "project version"),
            base,
        ),
        "Python project version": (
            capture("pyproject.toml", r'^version\s*=\s*"([^"]+)"', "Python version"),
            python_version,
        ),
        "Python package version": (
            capture("python/endstone_dynamic_properties/__init__.py", r'^__version__\s*=\s*"([^"]+)"', "__version__"),
            python_version,
        ),
        "C++ release version": (
            capture("include/endstone_dynamic_properties/version.h", r'#define\s+ENDSTONE_DYNAMIC_PROPERTIES_VERSION\s+"([^"]+)"', "C++ release version"),
            release,
        ),
        "README release": (
            capture("README.md", r"\*\*Release:\*\* `v([^`]+)`", "README release"),
            release,
        ),
        "build status version": (
            capture("BUILD_STATUS.md", r"Version:\s*\*\*([^*]+)\*\*", "build status version"),
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
    if source.get("release_kind") != "portable-core-and-reference-prerelease":
        failures.append("source release kind must identify the portable/reference prerelease")
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
            (ROOT / f"native/manifests/{platform}-1.26.33.1.json").read_text(encoding="utf-8")
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
        path for path in source_files()
        if path.suffix.lower() in FORBIDDEN_SUFFIXES
        or path.name.lower() in FORBIDDEN_FILENAMES
        or (path.suffix.lower() in {".zip", ".tar", ".gz"}
            and "bedrock" in path.name.lower())
    ]
    if forbidden:
        names = ", ".join(str(path.relative_to(ROOT)) for path in forbidden[:10])
        failures.append(f"private binary-analysis or world-storage artifacts are present: {names}")
    if failures:
        raise SystemExit("Metadata verification failed:\n- " + "\n- ".join(failures))
    print(f"Verified metadata for endstone-dynamic-properties-api {release}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
