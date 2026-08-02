from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "package_native_release.py"
WHEEL_NAME = (
    "endstone_dynamic_properties_tester-0.1.0a2-"
    "cp314-cp314-linux_x86_64.whl"
)
RELEASE_SUFFIX = (
    "0.1.0-alpha.2-bds-1.26.33.1-endstone-0.11.6-"
    "linux-x86_64-glibc-2.35-gate-closed"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_stage(
    root: Path, *, plugin_glibc: str = "2.2.5", bridge_glibc: str = "2.2.5"
) -> tuple[Path, Path]:
    stage = root / "stage"
    plugins = stage / "plugins"
    evidence = stage / "evidence"
    plugins.mkdir(parents=True)
    evidence.mkdir(parents=True)
    elf_header = b"\x7fELF\x02\x01" + (b"\x00" * 12) + b"\x3e\x00"
    (plugins / "endstone_dynamic_properties_api.so").write_bytes(
        elf_header + b"canonical-plugin\x00GLIBC_" + plugin_glibc.encode("ascii")
    )
    wheel = plugins / WHEEL_NAME
    with ZipFile(wheel, "w") as archive:
        archive.writestr(
            "endstone_dynamic_properties_tester/"
            "_endstone_dynamic_properties_live.cpython-314-x86_64-linux-gnu.so",
            elf_header + b"bridge\x00GLIBC_" + bridge_glibc.encode("ascii"),
        )
        archive.writestr(
            "endstone_dynamic_properties_tester-0.1.0a2.dist-info/WHEEL",
            "Wheel-Version: 1.0\n"
            "Generator: test\n"
            "Root-Is-Purelib: false\n"
            "Tag: cp314-cp314-linux_x86_64\n",
        )
    (evidence / "BUILD_MODE.txt").write_text(
        "GATE CLOSED: compilation and packaging validation only.\n",
        encoding="utf-8",
    )
    return stage, wheel


def run_packager(stage: Path, wheel: Path, output: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["SOURCE_DATE_EPOCH"] = "1785686400"
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--stage-dir",
            str(stage),
            "--wheel",
            str(wheel),
            "--output-dir",
            str(output),
            "--mode",
            "gate-closed",
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_packager_creates_named_plugin_wheel_and_deterministic_bundle(
    tmp_path: Path,
) -> None:
    stage, wheel = make_stage(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_result = run_packager(stage, wheel, first)
    second_result = run_packager(stage, wheel, second)
    assert first_result.returncode == 0, first_result.stderr
    assert second_result.returncode == 0, second_result.stderr

    plugin_name = f"endstone_dynamic_properties_api-{RELEASE_SUFFIX}.so"
    bundle_name = f"endstone-dynamic-properties-api-{RELEASE_SUFFIX}.zip"
    assert sorted(path.name for path in first.iterdir()) == sorted(
        (plugin_name, WHEEL_NAME, bundle_name)
    )
    assert digest(first / bundle_name) == digest(second / bundle_name)

    prefix = f"endstone-dynamic-properties-api-{RELEASE_SUFFIX}"
    with ZipFile(first / bundle_name) as archive:
        names = set(archive.namelist())
        assert f"{prefix}/plugins/endstone_dynamic_properties_api.so" in names
        assert f"{prefix}/plugins/{WHEEL_NAME}" in names
        assert f"{prefix}/evidence/BUILD_MODE.txt" in names
        manifest = json.loads(archive.read(f"{prefix}/RELEASE_MANIFEST.json"))
        assert manifest["mode"] == "gate-closed"
        assert manifest["operational"] is False
        assert manifest["python_abi"] == "cp314"
        assert manifest["glibc"] == {
            "ceiling": "2.35",
            "plugin_minimum": "2.2.5",
            "tester_bridge_minimum": "2.2.5",
        }
        assert manifest["plugin"] == "plugins/endstone_dynamic_properties_api.so"
        assert manifest["tester_wheel"] == f"plugins/{WHEEL_NAME}"


def test_packager_rejects_nonmatching_tester_wheel(tmp_path: Path) -> None:
    stage, wheel = make_stage(tmp_path)
    wrong_wheel = wheel.with_name("wrong.whl")
    wheel.rename(wrong_wheel)

    result = run_packager(stage, wrong_wheel, tmp_path / "output")

    assert result.returncode != 0
    assert "Matching tester wheel must be" in result.stderr


def test_packager_rejects_plugin_above_glibc_ceiling(tmp_path: Path) -> None:
    stage, wheel = make_stage(tmp_path, plugin_glibc="2.38")

    result = run_packager(stage, wheel, tmp_path / "output")

    assert result.returncode != 0
    assert "requires GLIBC_2.38" in result.stderr
    assert "release ceiling GLIBC_2.35" in result.stderr


def test_packager_rejects_tester_bridge_above_glibc_ceiling(
    tmp_path: Path,
) -> None:
    stage, wheel = make_stage(tmp_path, bridge_glibc="2.38")

    result = run_packager(stage, wheel, tmp_path / "output")

    assert result.returncode != 0
    assert "Tester wheel bridge requires GLIBC_2.38" in result.stderr
