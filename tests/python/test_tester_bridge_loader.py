from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (
    ROOT
    / "examples"
    / "python"
    / "dynamic_properties_tester_plugin"
    / "src"
    / "endstone_dynamic_properties_tester"
    / "_bridge_loader.py"
)


def load_loader():
    package_name = "_dynamic_properties_tester_loader_tests"
    package = ModuleType(package_name)
    package.__path__ = [str(SOURCE.parent)]  # type: ignore[attr-defined]
    sys.modules[package_name] = package
    name = f"{package_name}._bridge_loader"
    spec = importlib.util.spec_from_file_location(name, SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


LOADER = load_loader()


def complete_bridge(version: str = "0.1.0a3") -> ModuleType:
    bridge = ModuleType("fake_live_bridge")
    bridge.__version__ = version
    for name in LOADER.REQUIRED_FUNCTIONS:
        setattr(bridge, name, lambda *args, **kwargs: None)
    return bridge


def test_loader_imports_only_the_package_local_extension() -> None:
    bridge = complete_bridge()
    with patch.object(
        LOADER.importlib, "import_module", return_value=bridge
    ) as importer:
        assert LOADER.import_live_bridge("0.1.0a3") is bridge
    importer.assert_called_once_with(LOADER.BUNDLED_BRIDGE_MODULE)
    assert (
        LOADER.BUNDLED_BRIDGE_MODULE.endswith(
            ".endstone_dynamic_properties_tester._endstone_dynamic_properties_live"
        )
        is False
    )  # the synthetic test package is still package-local
    assert LOADER.BUNDLED_BRIDGE_MODULE.endswith("._endstone_dynamic_properties_live")


def test_loader_rejects_missing_bridge_without_trying_a_global_fallback() -> None:
    missing = ModuleNotFoundError("missing", name=LOADER.BUNDLED_BRIDGE_MODULE)
    with patch.object(
        LOADER.importlib, "import_module", side_effect=missing
    ) as importer:
        with pytest.raises(
            ModuleNotFoundError, match="package-local live bridge is missing"
        ):
            LOADER.import_live_bridge("0.1.0a3")
    assert importer.call_count == 1


def test_loader_rejects_version_mismatch_and_incomplete_exports() -> None:
    with patch.object(
        LOADER.importlib, "import_module", return_value=complete_bridge("old")
    ):
        with pytest.raises(RuntimeError, match="does not match tester version"):
            LOADER.import_live_bridge("0.1.0a3")
    incomplete = complete_bridge()
    del incomplete.flush
    with patch.object(LOADER.importlib, "import_module", return_value=incomplete):
        with pytest.raises(RuntimeError, match="missing callable exports: flush"):
            LOADER.import_live_bridge("0.1.0a3")
