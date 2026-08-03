#!/usr/bin/env python3
"""Build the in-game tester wheel with its exact CPython bridge bundled."""

from __future__ import annotations

import argparse
from email.parser import Parser
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
WHEEL_PROJECT = Path("examples/python/dynamic_properties_tester_plugin")
WHEEL_PACKAGE = Path("src/endstone_dynamic_properties_tester")
API_PACKAGE = Path("python/endstone_dynamic_properties")
PACKAGE_NAME = "endstone_dynamic_properties_tester"
BRIDGE_MODULE = "_endstone_dynamic_properties_live"
REQUIRED_PYTHON = (3, 14)
RUNTIME_DIRECTORY = "_native_libs"
REQUIRED_LINUX_RUNTIME_LIBRARIES = (
    "libc++.so.1",
    "libc++abi.so.1",
    "libunwind.so.1",
)
LLVM_LICENSE = Path("third_party/llvm/LLVM-LICENSE.txt")


def platform_tag() -> str:
    return sysconfig.get_platform().replace("-", "_").replace(".", "_")


def validate_bridge_binary(bridge: Path, target_platform: str) -> None:
    """Reject a bridge whose executable format or machine mismatches its wheel tag."""

    if target_platform == "win_amd64":
        with bridge.open("rb") as stream:
            dos_header = stream.read(64)
            if len(dos_header) != 64 or dos_header[:2] != b"MZ":
                raise SystemExit(
                    f"Native bridge is not a valid PE image for {target_platform}: {bridge}"
                )
            pe_offset = int.from_bytes(dos_header[0x3C:0x40], "little")
            if pe_offset < 64 or pe_offset + 6 > bridge.stat().st_size:
                raise SystemExit(
                    f"Native bridge has an invalid PE header offset: {bridge}"
                )
            stream.seek(pe_offset)
            pe_header = stream.read(6)
        if pe_header[:4] != b"PE\0\0":
            raise SystemExit(f"Native bridge has no PE signature: {bridge}")
        machine = int.from_bytes(pe_header[4:6], "little")
        if machine != 0x8664:
            raise SystemExit(
                "Native bridge PE machine does not match win_amd64 "
                f"(expected 0x8664, got 0x{machine:04x}): {bridge}"
            )
        return

    if target_platform == "linux_x86_64":
        with bridge.open("rb") as stream:
            elf_header = stream.read(20)
        if len(elf_header) != 20 or elf_header[:4] != b"\x7fELF":
            raise SystemExit(
                f"Native bridge is not a valid ELF image for {target_platform}: {bridge}"
            )
        if elf_header[4] != 2 or elf_header[5] != 1:
            raise SystemExit(
                "Native bridge ELF class/data encoding does not match linux_x86_64: "
                f"{bridge}"
            )
        machine = int.from_bytes(elf_header[18:20], "little")
        if machine != 62:
            raise SystemExit(
                "Native bridge ELF machine does not match linux_x86_64 "
                f"(expected 62, got {machine}): {bridge}"
            )
        return

    raise SystemExit(
        "Dynamic Properties tester native wheels support only win_amd64 and "
        f"linux_x86_64; running platform tag is {target_platform!r}"
    )


def validate_runtime_libraries(
    libraries: list[Path], target_platform: str
) -> dict[str, Path]:
    """Validate the complete package-local Linux C++ runtime closure."""

    if target_platform != "linux_x86_64":
        if libraries:
            raise SystemExit(
                "Package-local LLVM runtime libraries are supported only for "
                "linux_x86_64 tester wheels"
            )
        return {}

    by_name: dict[str, Path] = {}
    for candidate in libraries:
        if candidate.name in by_name:
            raise SystemExit(f"Duplicate runtime library {candidate.name!r}")
        if not candidate.is_file() or candidate.stat().st_size == 0:
            raise SystemExit(f"Runtime library is missing or empty: {candidate}")
        by_name[candidate.name] = candidate

    required = set(REQUIRED_LINUX_RUNTIME_LIBRARIES)
    supplied = set(by_name)
    if supplied != required:
        missing = sorted(required - supplied)
        unexpected = sorted(supplied - required)
        raise SystemExit(
            "Linux tester wheel requires the exact LLVM runtime closure; "
            f"missing={missing}, unexpected={unexpected}"
        )
    for name, library in by_name.items():
        validate_bridge_binary(library, target_platform)
    return by_name


def project_version(project: Path) -> str:
    import tomllib

    with (project / "pyproject.toml").open("rb") as stream:
        document = tomllib.load(stream)
    value = document.get("project", {}).get("version")
    if not isinstance(value, str) or not value:
        raise SystemExit(
            f"Project version is missing from {project / 'pyproject.toml'}"
        )
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a platform-specific Dynamic Properties tester wheel around "
            "an exact native bridge."
        )
    )
    parser.add_argument("--bridge", type=Path, required=True)
    parser.add_argument("--stage-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist" / "release")
    parser.add_argument(
        "--runtime-library",
        action="append",
        default=[],
        type=Path,
        help=(
            "Package-local Linux runtime library; repeat for libc++.so.1, "
            "libc++abi.so.1, and libunwind.so.1"
        ),
    )
    args = parser.parse_args()

    required_python_text = ".".join(str(part) for part in REQUIRED_PYTHON)
    if sys.implementation.name != "cpython" or sys.version_info[:2] != REQUIRED_PYTHON:
        raise SystemExit(
            "Dynamic Properties tester wheels with a native bridge must be built "
            f"with CPython {required_python_text}; running "
            f"{sys.implementation.name} {sys.version_info.major}.{sys.version_info.minor}"
        )

    stage_dir = args.stage_dir.resolve()
    if not stage_dir.is_dir():
        raise SystemExit(f"Exact install stage does not exist: {stage_dir}")
    if args.bridge.is_symlink():
        raise SystemExit(f"Native bridge must not be a symbolic link: {args.bridge}")
    bridge = args.bridge.resolve()
    try:
        bridge.relative_to(stage_dir / "python")
    except ValueError as exc:
        raise SystemExit(
            f"Native bridge must be inside the exact stage's python directory: {bridge}"
        ) from exc
    if not bridge.is_file() or bridge.stat().st_size == 0:
        raise SystemExit(f"Native bridge is missing or empty: {bridge}")

    extension_suffix = sysconfig.get_config_var("EXT_SUFFIX")
    if not isinstance(extension_suffix, str) or not extension_suffix:
        raise SystemExit("CPython did not report an EXT_SUFFIX for native modules")
    expected_bridge_name = BRIDGE_MODULE + extension_suffix
    if bridge.name != expected_bridge_name:
        raise SystemExit(
            f"Native bridge must use this CPython's extension suffix; got {bridge.name!r}, "
            f"expected {expected_bridge_name!r}"
        )
    target_platform = platform_tag()
    validate_bridge_binary(bridge, target_platform)
    runtime_libraries = validate_runtime_libraries(
        args.runtime_library, target_platform
    )
    llvm_license = ROOT / LLVM_LICENSE
    if runtime_libraries and not llvm_license.is_file():
        raise SystemExit(f"LLVM runtime license is missing: {llvm_license}")

    wheel_project = ROOT / WHEEL_PROJECT
    if not (wheel_project / "pyproject.toml").is_file():
        raise SystemExit(f"Tester wheel project is missing: {wheel_project}")
    api_version = project_version(ROOT)
    tester_version = project_version(wheel_project)
    if tester_version != api_version:
        raise SystemExit(
            "Tester and public API versions must match exactly; got "
            f"tester {tester_version!r}, API {api_version!r}"
        )

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    ignore = shutil.ignore_patterns(
        ".git",
        ".cache",
        ".conan2-ci",
        "build",
        "build-*",
        "dist",
        "__pycache__",
        "*.egg-info",
        "*.dll",
        "*.pyd",
        "*.so",
    )
    with tempfile.TemporaryDirectory(
        prefix="endstone-dynamic-properties-wheel-"
    ) as temporary:
        staged_root = Path(temporary) / "repo"
        shutil.copytree(ROOT, staged_root, ignore=ignore)
        staged_project = staged_root / WHEEL_PROJECT
        staged_package = staged_project / WHEEL_PACKAGE
        staged_package.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bridge, staged_package / bridge.name)
        if runtime_libraries:
            runtime_directory = staged_package / RUNTIME_DIRECTORY
            runtime_directory.mkdir()
            for name, library in sorted(runtime_libraries.items()):
                shutil.copy2(library, runtime_directory / name)
            shutil.copy2(llvm_license, staged_package / "LLVM-LICENSE.txt")
        shutil.copytree(
            staged_root / API_PACKAGE,
            staged_project / "src" / "endstone_dynamic_properties",
        )

        build_output = Path(temporary) / "wheel"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "build",
                "--wheel",
                "--no-isolation",
                "--outdir",
                str(build_output),
                str(staged_project),
            ],
            check=True,
        )
        wheels = list(build_output.glob("*.whl"))
        if len(wheels) != 1:
            raise SystemExit(
                f"Expected one tester wheel, found {len(wheels)}: {wheels}"
            )
        wheel = wheels[0]
        python_tag = "cp" + "".join(str(part) for part in REQUIRED_PYTHON)
        expected_tag = f"{python_tag}-{python_tag}-{target_platform}"
        expected_name_prefix = f"endstone_dynamic_properties_tester-{tester_version}-"
        if not wheel.name.startswith(expected_name_prefix):
            raise SystemExit(
                f"Tester wheel has the wrong project version: {wheel.name}; "
                f"expected prefix {expected_name_prefix}"
            )
        if not wheel.name.endswith(f"-{expected_tag}.whl"):
            raise SystemExit(
                f"Tester wheel has the wrong compatibility tag: {wheel.name}; "
                f"expected {expected_tag}"
            )

        with ZipFile(wheel) as archive:
            names = archive.namelist()
            expected_bridge = f"{PACKAGE_NAME}/{bridge.name}"
            if names.count(expected_bridge) != 1:
                raise SystemExit(
                    "Tester wheel must contain exactly one package-local bridge "
                    f"{expected_bridge}"
                )
            expected_runtime_members = (
                {
                    f"{PACKAGE_NAME}/{RUNTIME_DIRECTORY}/{name}"
                    for name in REQUIRED_LINUX_RUNTIME_LIBRARIES
                }
                if target_platform == "linux_x86_64"
                else set()
            )
            runtime_members = {
                name
                for name in names
                if name.startswith(f"{PACKAGE_NAME}/{RUNTIME_DIRECTORY}/")
                and not name.endswith("/")
            }
            if runtime_members != expected_runtime_members:
                raise SystemExit(
                    "Tester wheel LLVM runtime closure mismatch; "
                    f"expected={sorted(expected_runtime_members)}, "
                    f"got={sorted(runtime_members)}"
                )
            expected_license = f"{PACKAGE_NAME}/LLVM-LICENSE.txt"
            if runtime_libraries and names.count(expected_license) != 1:
                raise SystemExit(
                    f"Tester wheel must contain the LLVM runtime license {expected_license}"
                )
            if "endstone_dynamic_properties/__init__.py" not in names:
                raise SystemExit(
                    "Tester wheel must vendor the matching public Dynamic Properties API"
                )
            wheel_metadata_files = [
                name for name in names if name.endswith(".dist-info/WHEEL")
            ]
            if len(wheel_metadata_files) != 1:
                raise SystemExit(
                    "Tester wheel must contain exactly one WHEEL metadata file"
                )
            metadata = Parser().parsestr(
                archive.read(wheel_metadata_files[0]).decode("utf-8")
            )
            if metadata.get("Root-Is-Purelib") != "false":
                raise SystemExit(
                    "Tester wheel containing a native bridge must not be pure Python"
                )
            if metadata.get_all("Tag", []) != [expected_tag]:
                raise SystemExit(
                    f"Tester wheel metadata tag mismatch: {metadata.get_all('Tag', [])!r}"
                )

        destination = output_dir / wheel.name
        shutil.copy2(wheel, destination)
        bundled_destination = stage_dir / "plugins" / wheel.name
        bundled_destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(wheel, bundled_destination)

    print(destination)
    print(bundled_destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
