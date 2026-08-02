from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "linux-native.yml"


def test_linux_workflow_builds_the_plugin_and_matching_native_tester() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "runs-on: ubuntu-24.04" in source
    assert 'python-version: "3.14"' in source
    assert "-DENDSTONE_DYNAMIC_PROPERTIES_BUILD_PLUGIN=ON" in source
    assert "-DENDSTONE_DYNAMIC_PROPERTIES_BUILD_LIVE_PYTHON=ON" in source
    assert "scripts/build_test_wheel.py" in source
    assert "endstone_dynamic_properties_bds_1_26_33.so" in source
    assert "ELF 64-bit LSB shared object, x86-64" in source


def test_linux_workflow_cannot_label_an_incomplete_gate_verified() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    verification = source.index("python tools/verify_native_manifest.py")
    verified_mode = source.index('echo "mode=verified"')
    closed_mode = source.index('echo "mode=gate-closed"')
    assert verification < verified_mode < closed_mode
    assert "test -s src/verified_bds_26_30_adapter.cpp" in source
    assert "python tools/verify_fail_closed.py" in source
    assert "GATE CLOSED:" in source
    assert "linux-native-${{ steps.gate.outputs.mode }}" in source
