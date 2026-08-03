from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "src" / "experimental_live_bds_26_33_adapter.cpp"


def test_actor_targets_are_fail_closed_before_native_resolution() -> None:
    source = ADAPTER.read_text(encoding="utf-8")

    assert "out.online_players = false;" in source
    assert "out.loaded_entities = false;" in source
    assert "ActorGetOrAddPropertiesRva" not in source
    assert "ILevelFetchEntityVtableSlot" not in source
    assert "minecraftActor(" not in source

    resolver = source.split("ResolvedTarget resolveTarget(", 1)[1].split(
        "CaptureResult captureUnlocked", 1
    )[0]
    assert "TargetKind::World" in resolver
    assert "DynamicPropertyStatus::Unsupported" in resolver
    assert "implements only world targets" in resolver
    assert "get_or_add_actor" not in resolver
