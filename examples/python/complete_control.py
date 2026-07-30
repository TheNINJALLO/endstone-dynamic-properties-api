from endstone_dynamic_properties import (
    AccessContext, CollectionRef, DynamicPropertyService, DynamicPropertyTarget,
    ImportPolicy, SetPropertyOperation, Transaction, Vector3,
)

api = DynamicPropertyService()
plugin = AccessContext("ninjos_landclaims", "console")
collection = api.access_policy.plugin_collection(plugin.plugin_id, "claims")
world = CollectionRef(DynamicPropertyTarget.world(), collection)
offline = CollectionRef(DynamicPropertyTarget.offline_player("2533274790000000"), collection)

api.set(world, "enabled", True, plugin)
api.set(world, "spawn", Vector3(0.5, 64, 0.5), plugin)
result = api.transact(Transaction((
    SetPropertyOperation(offline, "claim_limit", 12.0),
    SetPropertyOperation(world, "last_migration", "complete"),
)), plugin)
print(result.status.value)
print(api.export_collection(world, plugin).document)
