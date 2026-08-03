from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (
    ROOT
    / "examples"
    / "python"
    / "dynamic_properties_tester_plugin"
    / "src"
    / "endstone_dynamic_properties_tester"
    / "targets.py"
)
SPEC = importlib.util.spec_from_file_location(
    "_dynamic_properties_tester_target_tests", SOURCE
)
assert SPEC is not None and SPEC.loader is not None
TARGETS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TARGETS)


def _write(path: Path, document: object) -> None:
    path.write_text(json.dumps(document), encoding="utf-8")


def test_template_contains_every_target_family_and_starts_disabled(
    tmp_path: Path,
) -> None:
    path = TARGETS.ensure_target_template(tmp_path)
    document = json.loads(path.read_text(encoding="utf-8"))

    assert document["schema"] == 1
    assert {entry["target"]["kind"] for entry in document["targets"]} == (
        TARGETS.TARGET_KINDS
    )
    assert all(entry["enabled"] is False for entry in document["targets"])
    assert TARGETS.load_configured_targets(tmp_path) == []


def test_loads_and_normalizes_enabled_targets_only(tmp_path: Path) -> None:
    path = TARGETS.ensure_target_template(tmp_path)
    document = {
        "schema": 1,
        "targets": [
            {
                "label": "offline",
                "enabled": True,
                "target": {"kind": "offline_player", "xuid": "1234"},
            },
            {
                "label": "ignored-placeholder",
                "enabled": False,
                "target": {
                    "kind": "stored_entity",
                    "entity_id": "REPLACE_WITH_ENTITY_ID",
                },
            },
        ],
    }
    _write(path, document)

    assert TARGETS.load_configured_targets(tmp_path) == [
        (
            "offline",
            {"kind": "offline_player", "xuid": "1234", "world_id": "default"},
        )
    ]


@pytest.mark.parametrize(
    ("target", "message"),
    [
        (
            {"kind": "offline_player", "xuid": "REPLACE_WITH_XUID"},
            "placeholder",
        ),
        ({"kind": "world", "unexpected": True}, "unsupported fields"),
        (
            {
                "kind": "block_container_slot",
                "slot": -1,
                "block": {"dimension": "overworld", "x": 0, "y": 64, "z": 0},
            },
            "non-negative",
        ),
    ],
)
def test_rejects_unsafe_or_ambiguous_enabled_targets(
    tmp_path: Path, target: dict[str, object], message: str
) -> None:
    path = TARGETS.ensure_target_template(tmp_path)
    _write(
        path,
        {
            "schema": 1,
            "targets": [{"label": "bad", "enabled": True, "target": target}],
        },
    )

    with pytest.raises(ValueError, match=message):
        TARGETS.load_configured_targets(tmp_path)


def test_rejects_duplicate_enabled_target_identity(tmp_path: Path) -> None:
    path = TARGETS.ensure_target_template(tmp_path)
    target = {"kind": "world", "world_id": "default"}
    _write(
        path,
        {
            "schema": 1,
            "targets": [
                {"label": "one", "enabled": True, "target": target},
                {"label": "two", "enabled": True, "target": target},
            ],
        },
    )

    with pytest.raises(ValueError, match="duplicate enabled target"):
        TARGETS.load_configured_targets(tmp_path)
