#include "endstone_dynamic_properties/dynamic_properties_api.h"

#include <iostream>

using namespace endstone_dynamic_properties;

int main() {
    auto adapter = makeInMemoryDynamicPropertyAdapter();
    auto audit = std::make_shared<VectorAuditSink>();
    DynamicPropertyService api(adapter, {}, {}, audit);

    AccessContext plugin{"ninjos_landclaims", "console", false, MutationOrigin::Command, "example"};
    const auto collection = api.accessPolicy().pluginCollection(plugin.plugin_id, "claims");
    CollectionRef world{DynamicPropertyTarget::world(), collection};
    CollectionRef offline{DynamicPropertyTarget::offlinePlayer("2533274790000000"), collection};

    api.set(world, "enabled", true, plugin);
    api.set(world, "spawn", Vector3{0.5, 64.0, 0.5}, plugin);

    DynamicPropertyTransaction tx;
    tx.audit_reason = "grant offline claim quota";
    tx.operations.push_back(SetPropertyOperation{offline, "claim_limit", 12.0, {}});
    tx.operations.push_back(SetPropertyOperation{world, "last_migration", std::string("complete"), {}});
    const auto result = api.transact(tx, plugin);

    std::cout << "transaction: " << statusName(result.status) << '\n';
    const auto exported = api.exportCollection(world, plugin);
    if (exported.ok()) std::cout << exported.document << '\n';
    return result.ok() ? 0 : 1;
}
