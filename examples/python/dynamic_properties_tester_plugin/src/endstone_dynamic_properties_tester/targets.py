"""Strict operator-managed target configuration for live acceptance runs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4


SCHEMA = 1
TARGETS_FILE = "targets.json"
TARGET_KINDS = {
    "world",
    "online_player",
    "offline_player",
    "loaded_entity",
    "stored_entity",
    "player_inventory_slot",
    "player_armor_slot",
    "player_offhand_slot",
    "player_ender_chest_slot",
    "block_container_slot",
    "dropped_item",
    "block_entity",
}


def targets_path(data_folder: Path) -> Path:
    return data_folder / TARGETS_FILE


def _block_target(kind: str, *, slot: bool = False) -> dict[str, Any]:
    target: dict[str, Any] = {
        "kind": kind,
        "world_id": "default",
        "block": {"dimension": "overworld", "x": 0, "y": 64, "z": 0},
    }
    if slot:
        target["slot"] = 0
    return target


def target_template() -> dict[str, Any]:
    """Return a disabled example containing every supported target family."""

    return {
        "schema": SCHEMA,
        "targets": [
            {
                "label": "configured-world",
                "enabled": False,
                "target": {"kind": "world", "world_id": "default"},
            },
            {
                "label": "configured-online-player",
                "enabled": False,
                "target": {
                    "kind": "online_player",
                    "world_id": "default",
                    "xuid": "REPLACE_WITH_XUID",
                },
            },
            {
                "label": "offline-player",
                "enabled": False,
                "target": {
                    "kind": "offline_player",
                    "world_id": "default",
                    "xuid": "REPLACE_WITH_XUID",
                },
            },
            {
                "label": "loaded-entity",
                "enabled": False,
                "target": {
                    "kind": "loaded_entity",
                    "world_id": "default",
                    "entity_id": "REPLACE_WITH_ENTITY_ID",
                },
            },
            {
                "label": "stored-entity",
                "enabled": False,
                "target": {
                    "kind": "stored_entity",
                    "world_id": "default",
                    "entity_id": "REPLACE_WITH_ENTITY_ID",
                },
            },
            *(
                {
                    "label": label,
                    "enabled": False,
                    "target": {
                        "kind": kind,
                        "world_id": "default",
                        "xuid": "REPLACE_WITH_XUID",
                        "slot": slot,
                    },
                }
                for label, kind, slot in (
                    ("main-inventory-item", "player_inventory_slot", 0),
                    ("armor-item", "player_armor_slot", 0),
                    ("offhand-item", "player_offhand_slot", 0),
                    ("ender-chest-item", "player_ender_chest_slot", 0),
                )
            ),
            {
                "label": "block-container-item",
                "enabled": False,
                "target": _block_target("block_container_slot", slot=True),
            },
            {
                "label": "dropped-item",
                "enabled": False,
                "target": {
                    "kind": "dropped_item",
                    "world_id": "default",
                    "item_entity_id": "REPLACE_WITH_ITEM_ENTITY_ID",
                },
            },
            {
                "label": "block-entity",
                "enabled": False,
                "target": _block_target("block_entity"),
            },
        ],
    }


def ensure_target_template(data_folder: Path) -> Path:
    """Create the disabled template once without replacing operator edits."""

    path = targets_path(data_folder)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(target_template(), stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            # Another plugin lifecycle callback won the creation race. Preserve it.
            pass
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _require_string(target: dict[str, Any], name: str) -> None:
    value = target.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"target field {name!r} must be a non-empty string")
    if value.startswith("REPLACE_WITH_"):
        raise ValueError(f"target field {name!r} still contains a template placeholder")


def _require_slot(target: dict[str, Any]) -> None:
    value = target.get("slot")
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= 2**31 - 1
    ):
        raise ValueError(
            "target field 'slot' must be a non-negative signed 32-bit integer"
        )


def _require_block(target: dict[str, Any]) -> None:
    block = target.get("block")
    if not isinstance(block, dict) or set(block) != {"dimension", "x", "y", "z"}:
        raise ValueError(
            "target field 'block' must contain exactly dimension, x, y, and z"
        )
    _require_string(block, "dimension")
    for name in ("x", "y", "z"):
        value = block.get(name)
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not -(2**31) <= value <= 2**31 - 1
        ):
            raise ValueError(f"block field {name!r} must be a signed 32-bit integer")


def validate_target(value: object) -> dict[str, Any]:
    """Return a normalized target or raise on ambiguous/extra fields."""

    if not isinstance(value, dict):
        raise ValueError("target must be an object")
    target = dict(value)
    kind = target.get("kind")
    if kind not in TARGET_KINDS:
        raise ValueError(f"unsupported target kind {kind!r}")

    allowed = {"kind", "world_id"}
    required_strings: tuple[str, ...] = ()
    if kind in {"online_player", "offline_player"}:
        allowed.add("xuid")
        required_strings = ("xuid",)
    elif kind in {"loaded_entity", "stored_entity"}:
        allowed.add("entity_id")
        required_strings = ("entity_id",)
    elif kind in {
        "player_inventory_slot",
        "player_armor_slot",
        "player_offhand_slot",
        "player_ender_chest_slot",
    }:
        allowed.update(("xuid", "slot"))
        required_strings = ("xuid",)
        _require_slot(target)
    elif kind == "block_container_slot":
        allowed.update(("block", "slot"))
        _require_block(target)
        _require_slot(target)
    elif kind == "dropped_item":
        allowed.add("item_entity_id")
        required_strings = ("item_entity_id",)
    elif kind == "block_entity":
        allowed.add("block")
        _require_block(target)

    unexpected = sorted(set(target) - allowed)
    if unexpected:
        raise ValueError("target contains unsupported fields: " + ", ".join(unexpected))
    if "world_id" not in target:
        target["world_id"] = "default"
    _require_string(target, "world_id")
    for name in required_strings:
        _require_string(target, name)
    return target


def load_configured_targets(data_folder: Path) -> list[tuple[str, dict[str, Any]]]:
    """Load enabled, uniquely labelled targets from the operator template."""

    path = ensure_target_template(data_folder)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"could not read {path}: {error}") from error
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise ValueError(f"{path} must be a schema-{SCHEMA} target document")
    if set(document) != {"schema", "targets"}:
        raise ValueError(f"{path} must contain exactly 'schema' and 'targets'")
    entries = document.get("targets")
    if not isinstance(entries, list):
        raise ValueError(f"{path} field 'targets' must be an array")

    configured: list[tuple[str, dict[str, Any]]] = []
    labels: set[str] = set()
    identities: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != {"label", "enabled", "target"}:
            raise ValueError(
                f"{path} target {index} must contain exactly label, enabled, and target"
            )
        if entry.get("enabled") is not True:
            if entry.get("enabled") is not False:
                raise ValueError(
                    f"{path} target {index} field 'enabled' must be boolean"
                )
            continue
        label = entry.get("label")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"{path} target {index} has no non-empty label")
        label = label.strip()
        if label in labels:
            raise ValueError(f"{path} contains duplicate enabled label {label!r}")
        target = validate_target(entry.get("target"))
        identity = json.dumps(target, sort_keys=True, separators=(",", ":"))
        if identity in identities:
            raise ValueError(f"{path} contains duplicate enabled target {label!r}")
        labels.add(label)
        identities.add(identity)
        configured.append((label, target))
    return configured
