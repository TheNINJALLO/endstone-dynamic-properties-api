from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "linux-native.yml"


def test_linux_workflow_builds_the_plugin_and_matching_native_tester() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "runs-on: ubuntu-22.04" in source
    assert "llvm-toolchain-jammy-18" in source
    assert "6084F3CF814B57C1CF12EFD515CF4D18AF4F7421" in source
    assert "clang-tools-18" in source
    assert "command -v clang-scan-deps-18" in source
    assert 'python-version: "3.14"' in source
    assert "-DENDSTONE_DYNAMIC_PROPERTIES_BUILD_PLUGIN=ON" in source
    assert "-DENDSTONE_DYNAMIC_PROPERTIES_BUILD_LIVE_PYTHON=ON" in source
    assert "scripts/build_test_wheel.py" in source
    assert "endstone_dynamic_properties_api.so" in source
    assert "scripts/package_native_release.py" in source
    assert "inputs.source_date_epoch || '315532800'" in source
    assert "ELF 64-bit LSB shared object, x86-64" in source
    assert "dpkg --compare-versions" in source
    assert "GLIBC_2.35 ceiling" in source


def test_linux_push_and_release_run_disposable_two_boot_acceptance() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "python -m pip install 'endstone==0.11.6'" in source
    assert "scripts/run_live_server_acceptance.py" in source
    assert '--server-dir "$RUNNER_TEMP/dynamic-properties-live-bds"' in source
    assert "if: github.event_name != 'pull_request'" in source
    assert "name: linux-live-acceptance" in source


def test_linux_workflow_cannot_label_an_incomplete_gate_verified() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    verification = source.index("python tools/verify_native_manifest.py")
    verified_mode = source.index('echo "mode=verified"')
    experimental_mode = source.index('echo "mode=experimental-live"')
    closed_mode = source.index('echo "mode=gate-closed"')
    assert verification < verified_mode < experimental_mode < closed_mode
    assert "test -s src/verified_bds_26_30_adapter.cpp" in source
    assert "python tools/verify_fail_closed.py" in source
    assert "GATE CLOSED:" in source
    assert "EXPERIMENTAL LIVE:" in source
    assert "linux-native-${{ steps.gate.outputs.mode }}" in source


def test_draft_release_includes_the_native_plugin_and_bound_wheel() -> None:
    source = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "uses: ./.github/workflows/linux-native.yml" in source
    assert "release_assets_only: true" in source
    assert "portable-sdk, linux-native" in source
