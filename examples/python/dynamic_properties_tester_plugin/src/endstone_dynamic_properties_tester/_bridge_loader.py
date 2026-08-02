"""Load only the exact native bridge bundled in this tester package."""

from __future__ import annotations

import importlib
from types import ModuleType


BRIDGE_MODULE = "_endstone_dynamic_properties_live"
BUNDLED_BRIDGE_MODULE = f"{__package__}.{BRIDGE_MODULE}"
REQUIRED_FUNCTIONS = (
    "available",
    "status",
    "capture",
    "list_collections",
    "set_value",
    "remove_value",
    "clear_collection",
    "flush",
    "start_external_watch",
    "drain_external_events",
    "external_watch_status",
    "stop_external_watch",
)


def import_live_bridge(expected_version: str) -> ModuleType:
    """Import and validate the package-local, version-matched live bridge."""

    try:
        bridge = importlib.import_module(BUNDLED_BRIDGE_MODULE)
    except ModuleNotFoundError as error:
        if error.name != BUNDLED_BRIDGE_MODULE:
            raise
        raise ModuleNotFoundError(
            "Dynamic Properties API's package-local live bridge is missing. "
            f"Install the matching {expected_version} CPython 3.14 tester wheel "
            "for this server platform.",
            name=BUNDLED_BRIDGE_MODULE,
        ) from error

    bridge_version = getattr(bridge, "__version__", None)
    if bridge_version != expected_version:
        raise RuntimeError(
            f"Dynamic Properties bridge version {bridge_version!r} does not match "
            f"tester version {expected_version!r}. Remove older tester wheels and "
            "install the wheel shipped with this exact native plugin."
        )
    missing = [
        name for name in REQUIRED_FUNCTIONS if not callable(getattr(bridge, name, None))
    ]
    if missing:
        raise RuntimeError(
            "Dynamic Properties bridge is incomplete; missing callable exports: "
            + ", ".join(missing)
        )
    return bridge
