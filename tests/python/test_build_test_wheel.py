from __future__ import annotations

from pathlib import Path

import pytest

from scripts.build_test_wheel import validate_bridge_binary


def _write_pe(path: Path, machine: int) -> None:
    image = bytearray(128)
    image[:2] = b"MZ"
    image[0x3C:0x40] = (64).to_bytes(4, "little")
    image[64:68] = b"PE\0\0"
    image[68:70] = machine.to_bytes(2, "little")
    path.write_bytes(image)


def _write_elf(path: Path, machine: int) -> None:
    image = bytearray(64)
    image[:4] = b"\x7fELF"
    image[4] = 2  # ELFCLASS64
    image[5] = 1  # ELFDATA2LSB
    image[18:20] = machine.to_bytes(2, "little")
    path.write_bytes(image)


def test_accepts_amd64_pe_for_win_amd64(tmp_path: Path) -> None:
    bridge = tmp_path / "bridge.pyd"
    _write_pe(bridge, 0x8664)

    validate_bridge_binary(bridge, "win_amd64")


def test_rejects_wrong_pe_machine_for_win_amd64(tmp_path: Path) -> None:
    bridge = tmp_path / "bridge.pyd"
    _write_pe(bridge, 0x014C)

    with pytest.raises(SystemExit, match="PE machine"):
        validate_bridge_binary(bridge, "win_amd64")


def test_accepts_x86_64_elf_for_linux_x86_64(tmp_path: Path) -> None:
    bridge = tmp_path / "bridge.so"
    _write_elf(bridge, 62)

    validate_bridge_binary(bridge, "linux_x86_64")


def test_rejects_wrong_elf_machine_for_linux_x86_64(tmp_path: Path) -> None:
    bridge = tmp_path / "bridge.so"
    _write_elf(bridge, 183)

    with pytest.raises(SystemExit, match="ELF machine"):
        validate_bridge_binary(bridge, "linux_x86_64")


def test_rejects_unsupported_native_wheel_platform(tmp_path: Path) -> None:
    bridge = tmp_path / "bridge.so"

    with pytest.raises(SystemExit, match="support only"):
        validate_bridge_binary(bridge, "macosx_15_0_arm64")
