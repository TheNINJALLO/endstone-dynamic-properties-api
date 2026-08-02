from __future__ import annotations

import ast
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = (
    ROOT
    / "examples"
    / "python"
    / "dynamic_properties_tester_plugin"
    / "src"
    / "endstone_dynamic_properties_tester"
    / "plugin.py"
)
PYPROJECT = PLUGIN.parents[2] / "pyproject.toml"
PARAMETER = re.compile(
    r"(?P<values>\([^()]*\))?"
    r"(?P<open><|\[)\s*(?P<name>[^:\]>]+)\s*:\s*"
    r"(?P<type>[A-Za-z_][A-Za-z0-9_]*)\s*(?P<close>>|\])"
)


def class_assignment(name: str):
    tree = ast.parse(PLUGIN.read_text(encoding="utf-8"), filename=str(PLUGIN))
    plugin_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "DynamicPropertiesTesterPlugin"
    )
    statement = next(
        statement
        for statement in plugin_class.body
        if isinstance(statement, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == name
            for target in statement.targets
        )
    )
    return ast.literal_eval(statement.value)


def test_exact_operator_only_command_surface() -> None:
    commands = class_assignment("commands")
    assert set(commands) == {"dptest"}
    command = commands["dptest"]
    assert command["permissions"] == ["dptest.admin"]
    usages = command["usages"]
    assert len(usages) == 8
    assert any(
        "(world|player|configured|all)<scope: DpTestRunScope>" in item
        for item in usages
    )
    assert any(
        "(world|player|configured|all)<scope: DpTestInventoryScope>" in item
        for item in usages
    )
    assert any(
        "(start|probe|drain|status|stop)<phase: DpTestWatchPhase>" in item
        for item in usages
    )
    assert any(
        "(prepare|verify)<phase: DpTestPersistencePhase>" in item for item in usages
    )
    assert any("(confirm)<confirmation: DpTestRunConfirm>" in item for item in usages)
    assert any(
        "(confirm)<confirmation: DpTestCleanupConfirm>" in item for item in usages
    )
    assert class_assignment("permissions")["dptest.admin"]["default"] == "op"


def test_each_endstone_enum_type_is_unique_and_nonempty() -> None:
    seen: set[str] = set()
    for usage in class_assignment("commands")["dptest"]["usages"]:
        matches = list(PARAMETER.finditer(usage))
        assert matches, usage
        for match in matches:
            values = match.group("values")
            assert values is not None, f"tester should expose only fixed enums: {usage}"
            assert match.group("type") not in seen, usage
            seen.add(match.group("type"))
            assert all(value.strip() for value in values[1:-1].split("|")), usage


def test_wheel_is_exact_cpython_endstone_and_has_no_identity_arguments() -> None:
    metadata = PYPROJECT.read_text(encoding="utf-8")
    assert 'version = "0.1.0a3"' in metadata
    assert 'requires-python = "==3.14.*"' in metadata
    assert '"endstone==0.11.6"' in metadata
    source = PLUGIN.read_text(encoding="utf-8")
    assert "plugin_id" not in source
    assert "raw_admin" not in source
    for unsafe in ("<xuid:", "<plugin:", "<collection:"):
        assert unsafe not in source
