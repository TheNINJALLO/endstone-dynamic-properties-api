from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import time
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
INSTALLED_PLUGIN_NAME = "endstone_dynamic_properties_api.so"
TESTER_DISTRIBUTION = "endstone_dynamic_properties_tester"
RELEASE_PLATFORM = "linux-x86_64"
PYTHON_ABI_TAG = "cp314-cp314-linux_x86_64"
BRIDGE_MEMBER = (
    "endstone_dynamic_properties_tester/"
    "_endstone_dynamic_properties_live.cpython-314-x86_64-linux-gnu.so"
)
GLIBC_VERSION = re.compile(rb"GLIBC_([0-9]+(?:\.[0-9]+)+)")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def python_version(release: str) -> str:
    match = re.fullmatch(
        r"(\d+\.\d+\.\d+)(?:-(alpha|beta|rc)\.(\d+))?", release
    )
    if match is None:
        raise SystemExit(f"Unsupported release version: {release}")
    base, stage, serial = match.groups()
    markers = {"alpha": "a", "beta": "b", "rc": "rc"}
    return base if stage is None else f"{base}{markers[stage]}{serial}"


def parse_version(value: str) -> tuple[int, ...]:
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", value) is None:
        raise SystemExit(f"Invalid dotted numeric version: {value!r}")
    parts = [int(part) for part in value.split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def validate_elf_x86_64(
    data: bytes, description: str, glibc_ceiling: str
) -> str:
    if (
        len(data) < 20
        or data[:4] != b"\x7fELF"
        or data[4] != 2
        or data[5] != 1
        or int.from_bytes(data[18:20], "little") != 62
    ):
        raise SystemExit(f"{description} must be little-endian ELF64 x86-64")
    versions = {
        match.group(1).decode("ascii") for match in GLIBC_VERSION.finditer(data)
    }
    if not versions:
        raise SystemExit(f"{description} does not declare any imported GLIBC versions")
    required = max(versions, key=parse_version)
    if parse_version(required) > parse_version(glibc_ceiling):
        raise SystemExit(
            f"{description} requires GLIBC_{required}, exceeding the "
            f"release ceiling GLIBC_{glibc_ceiling}"
        )
    return required


def validate_tester_wheel(wheel: Path, glibc_ceiling: str) -> str:
    with ZipFile(wheel) as archive:
        names = archive.namelist()
        if names.count(BRIDGE_MEMBER) != 1:
            raise SystemExit(
                f"Tester wheel must contain exactly one bound bridge {BRIDGE_MEMBER!r}"
            )
        bridge_glibc = validate_elf_x86_64(
            archive.read(BRIDGE_MEMBER), "Tester wheel bridge", glibc_ceiling
        )
        wheel_metadata = [name for name in names if name.endswith(".dist-info/WHEEL")]
        if len(wheel_metadata) != 1:
            raise SystemExit("Tester wheel must contain exactly one WHEEL metadata file")
        metadata = archive.read(wheel_metadata[0]).decode("utf-8")
        if "Root-Is-Purelib: false" not in metadata:
            raise SystemExit("Tester wheel containing the bridge must not be pure Python")
        if f"Tag: {PYTHON_ABI_TAG}" not in metadata:
            raise SystemExit(f"Tester wheel must declare tag {PYTHON_ABI_TAG!r}")
    return bridge_glibc


def zip_timestamp() -> tuple[int, int, int, int, int, int]:
    raw_epoch = os.environ.get("SOURCE_DATE_EPOCH") or "315532800"
    try:
        epoch = max(int(raw_epoch), 315532800)
    except ValueError as exc:
        raise SystemExit("SOURCE_DATE_EPOCH must be an integer") from exc
    value = time.gmtime(epoch)
    return (value.tm_year, value.tm_mon, value.tm_mday, value.tm_hour, value.tm_min, value.tm_sec)


def write_deterministic_zip(source: Path, destination: Path) -> None:
    timestamp = zip_timestamp()
    with ZipFile(destination, "w", ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            relative = path.relative_to(source).as_posix()
            info = ZipInfo(relative, timestamp)
            info.compress_type = ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, path.read_bytes())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create canonical Linux plugin and tester release assets."
    )
    parser.add_argument("--stage-dir", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("gate-closed", "experimental-live", "verified"),
        required=True,
    )
    args = parser.parse_args()

    source_release = json.loads((ROOT / "SOURCE_RELEASE.json").read_text(encoding="utf-8"))
    release = str(source_release["version"])
    expected_mode = source_release.get("native_artifact_mode")
    if source_release.get("native_plugin_included") is not True:
        raise SystemExit("Release metadata must declare native_plugin_included=true")
    if source_release.get("tester_wheel_included") is not True:
        raise SystemExit("Release metadata must declare tester_wheel_included=true")
    if expected_mode != args.mode:
        raise SystemExit(
            f"Native release mode mismatch: metadata={expected_mode!r}, build={args.mode!r}"
        )
    expected_operational = args.mode in {"experimental-live", "verified"}
    if source_release.get("native_plugin_operational") is not expected_operational:
        raise SystemExit(
            "native_plugin_operational does not match the selected native release mode"
        )

    packages = source_release.get("supported_bds_packages")
    endstone_tags = source_release.get("endstone_tags")
    if not isinstance(packages, list) or len(packages) != 1:
        raise SystemExit("Native releases require exactly one supported BDS package")
    if not isinstance(endstone_tags, list) or len(endstone_tags) != 1:
        raise SystemExit("Native releases require exactly one Endstone tag")
    bds_package = str(packages[0])
    endstone_version = str(endstone_tags[0]).removeprefix("v")
    glibc_ceiling = str(source_release.get("linux_glibc_ceiling", ""))
    parse_version(glibc_ceiling)

    stage = args.stage_dir.resolve()
    plugin = stage / "plugins" / INSTALLED_PLUGIN_NAME
    if not plugin.is_file() or plugin.stat().st_size == 0 or plugin.is_symlink():
        raise SystemExit(f"Canonical staged plugin is missing or invalid: {plugin}")
    plugin_glibc = validate_elf_x86_64(
        plugin.read_bytes(), "Canonical staged plugin", glibc_ceiling
    )

    wheel = args.wheel.resolve()
    expected_wheel = (
        f"{TESTER_DISTRIBUTION}-{python_version(release)}-{PYTHON_ABI_TAG}.whl"
    )
    if wheel.name != expected_wheel or not wheel.is_file() or wheel.stat().st_size == 0:
        raise SystemExit(
            f"Matching tester wheel must be {expected_wheel!r}; got {wheel.name!r}"
        )
    bridge_glibc = validate_tester_wheel(wheel, glibc_ceiling)

    build_mode = stage / "evidence" / "BUILD_MODE.txt"
    if not build_mode.is_file():
        raise SystemExit(f"Native build-mode evidence is missing: {build_mode}")
    mode_text = build_mode.read_text(encoding="utf-8")
    required_marker = {
        "verified": "VERIFIED:",
        "experimental-live": "EXPERIMENTAL LIVE:",
        "gate-closed": "GATE CLOSED:",
    }[args.mode]
    if required_marker not in mode_text:
        raise SystemExit(
            f"Build-mode evidence does not contain {required_marker!r}: {build_mode}"
        )

    release_suffix = (
        f"{release}-bds-{bds_package}-endstone-{endstone_version}-"
        f"{RELEASE_PLATFORM}-glibc-{glibc_ceiling}-{args.mode}"
    )
    plugin_asset_name = f"endstone_dynamic_properties_api-{release_suffix}.so"
    bundle_stem = f"endstone-dynamic-properties-api-{release_suffix}"
    bundle_name = f"{bundle_stem}.zip"

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    plugin_asset = output / plugin_asset_name
    wheel_asset = output / expected_wheel
    bundle_asset = output / bundle_name
    for destination in (plugin_asset, wheel_asset, bundle_asset):
        if destination.exists():
            raise SystemExit(f"Refusing to overwrite release asset: {destination}")
    shutil.copy2(plugin, plugin_asset)
    shutil.copy2(wheel, wheel_asset)

    with tempfile.TemporaryDirectory(prefix="dynamic-properties-native-release-") as raw:
        bundle_root = Path(raw) / bundle_stem
        plugins = bundle_root / "plugins"
        evidence = bundle_root / "evidence"
        plugins.mkdir(parents=True)
        evidence.mkdir(parents=True)
        bundled_plugin = plugins / INSTALLED_PLUGIN_NAME
        bundled_wheel = plugins / expected_wheel
        shutil.copy2(plugin, bundled_plugin)
        shutil.copy2(wheel, bundled_wheel)
        shutil.copy2(build_mode, evidence / "BUILD_MODE.txt")

        checksums = {
            f"plugins/{INSTALLED_PLUGIN_NAME}": sha256(bundled_plugin),
            f"plugins/{expected_wheel}": sha256(bundled_wheel),
        }
        manifest = {
            "schema": 1,
            "project": source_release["name"],
            "version": release,
            "platform": RELEASE_PLATFORM,
            "mode": args.mode,
            "operational": expected_operational,
            "service": source_release["service"],
            "bds_package": bds_package,
            "bds_runtime": source_release["supported_bds_runtime"][0],
            "endstone": endstone_version,
            "python_abi": "cp314",
            "glibc": {
                "ceiling": glibc_ceiling,
                "plugin_minimum": plugin_glibc,
                "tester_bridge_minimum": bridge_glibc,
            },
            "plugin": f"plugins/{INSTALLED_PLUGIN_NAME}",
            "tester_wheel": f"plugins/{expected_wheel}",
            "sha256": checksums,
        }
        (bundle_root / "RELEASE_MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (bundle_root / "SHA256SUMS.txt").write_text(
            "".join(f"{digest}  {path}\n" for path, digest in sorted(checksums.items())),
            encoding="utf-8",
        )
        write_deterministic_zip(Path(raw), bundle_asset)

    for asset in (plugin_asset, wheel_asset, bundle_asset):
        print(f"{sha256(asset)}  {asset}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
