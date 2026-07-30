#ifdef NDEBUG
#undef NDEBUG
#endif

#include "endstone_dynamic_properties/dynamic_properties_api.h"
#include "endstone_dynamic_properties/native_manifest.h"

#include <algorithm>
#include <array>
#include <cassert>
#include <barrier>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <thread>

using namespace endstone_dynamic_properties;

namespace {

class NoExternalCancellationAdapter final : public IDynamicPropertyAdapter {
public:
    explicit NoExternalCancellationAdapter(
        std::shared_ptr<IDynamicPropertyAdapter> inner,
        bool fail_capture = false)
        : inner_(std::move(inner)), fail_capture_(fail_capture) {}

    [[nodiscard]] std::string_view name() const noexcept override { return inner_->name(); }
    [[nodiscard]] DynamicPropertyCapabilities capabilities() const noexcept override {
        auto value = inner_->capabilities();
        value.external_change_cancellation = false;
        return value;
    }
    [[nodiscard]] CaptureResult capture(const CollectionRef &ref) override {
        if (fail_capture_)
            return {DynamicPropertyStatus::AdapterError,
                    "capture failed for test", std::nullopt};
        return inner_->capture(ref);
    }
    [[nodiscard]] ListCollectionsResult listCollections(
        const DynamicPropertyTarget &target) override {
        return inner_->listCollections(target);
    }
    OperationResult apply(const DynamicPropertyOperation &operation, bool force) override {
        return inner_->apply(operation, force);
    }
    TransactionResult transact(const DynamicPropertyTransaction &transaction) override {
        return inner_->transact(transaction);
    }
    OperationResult flush(const DynamicPropertyTarget &target) override {
        return inner_->flush(target);
    }

private:
    std::shared_ptr<IDynamicPropertyAdapter> inner_;
    bool fail_capture_{};
};

class ThrowingAuditSink final : public IDynamicPropertyAuditSink {
public:
    void record(DynamicPropertyAuditRecord) override {
        throw std::runtime_error("audit unavailable");
    }
};

} // namespace

int main() {
    auto adapter = makeInMemoryDynamicPropertyAdapter();
    auto events = std::make_shared<DynamicPropertyEventBus>();
    auto audit = std::make_shared<VectorAuditSink>();
    DynamicPropertyService service(adapter, {}, events, audit);

    AccessContext plugin{"Test.Plugin", "tester", false, MutationOrigin::Api, "unit test"};
    AccessContext admin{"admin", "console", true, MutationOrigin::Command, "migration"};
    const auto own = service.accessPolicy().pluginCollection(plugin.plugin_id, "main");
    assert(own == "endstone-plugin:test.plugin:main");

    CollectionRef world{DynamicPropertyTarget::world(), own};
    auto set_result = service.set(world, "enabled", true, plugin);
    assert(set_result.ok());
    assert(service.set(world, "score", 42.5, plugin).ok());
    assert(service.set(world, "name", std::string("Kingdom"), plugin).ok());
    assert(service.set(world, "spawn", Vector3{1.0, 64.0, -2.0}, plugin).ok());

    auto audit_failure_adapter = makeInMemoryDynamicPropertyAdapter();
    DynamicPropertyService audit_failure_service(
        audit_failure_adapter, {}, {}, std::make_shared<ThrowingAuditSink>());
    std::size_t audit_failure_count = 0;
    audit_failure_service.setAuditFailureHandler(
        [&](std::exception_ptr failure) {
            ++audit_failure_count;
            try {
                std::rethrow_exception(failure);
            } catch (const std::runtime_error &error) {
                assert(std::string_view(error.what()) == "audit unavailable");
            }
        });
    const auto audit_failure_result =
        audit_failure_service.set(world, "committed", true, plugin);
    assert(audit_failure_result.ok());
    assert(audit_failure_count == 1);
    assert(audit_failure_service.get(world, "committed", plugin).ok());

    auto read = service.get(world, "score", plugin);
    assert(read.ok());
    assert(std::get<double>(*read.value) == 42.5);

    auto captured = service.capture(world, plugin);
    assert(captured.ok() && captured.snapshot);
    assert(captured.snapshot->properties.size() == 4);
    assert(captured.snapshot->byte_count > 0);
    const auto revision = captured.snapshot->revision;

    auto stale = service.set(world, "score", 99.0, plugin, revision + 1);
    assert(stale.status == DynamicPropertyStatus::Conflict);
    assert(std::get<double>(*service.get(world, "score", plugin).value) == 42.5);
    auto forced_by_plugin = service.apply(
        SetPropertyOperation{world, "score", 99.0, revision + 1}, plugin, true);
    assert(forced_by_plugin.status == DynamicPropertyStatus::PermissionDenied);
    auto forced_by_admin = service.apply(
        SetPropertyOperation{world, "score", 99.0, revision + 1}, admin, true);
    assert(forced_by_admin.ok());

    const auto cancelled_id = events->subscribe(
        EventFilter{DynamicPropertyEventKind::BeforeMutation, {}, {}, own, std::string("blocked")},
        [](DynamicPropertyEvent &event) {
            event.cancelled = true;
            event.cancellation_reason = "blocked by policy test";
        });
    auto cancelled = service.set(world, "blocked", std::string("no"), plugin);
    assert(cancelled.status == DynamicPropertyStatus::Cancelled);
    assert(!service.get(world, "blocked", plugin).value);
    assert(events->unsubscribe(cancelled_id));

    std::size_t reported_listener_failures = 0;
    events->setListenerFailureHandler(
        [&](std::uint64_t, std::exception_ptr failure) {
            assert(failure);
            ++reported_listener_failures;
        });
    bool later_before_listener_ran = false;
    const auto throwing_before_listener_id = events->subscribe(
        EventFilter{DynamicPropertyEventKind::BeforeMutation, {}, {}, own,
                    std::string("before_listener_exception")},
        [](DynamicPropertyEvent &) { throw std::runtime_error("before listener failed"); });
    const auto later_before_listener_id = events->subscribe(
        EventFilter{DynamicPropertyEventKind::BeforeMutation, {}, {}, own,
                    std::string("before_listener_exception")},
        [&](DynamicPropertyEvent &) { later_before_listener_ran = true; });
    const auto before_listener_failure = service.set(
        world, "before_listener_exception", true, plugin);
    assert(before_listener_failure.status == DynamicPropertyStatus::Cancelled);
    assert(later_before_listener_ran);
    assert(reported_listener_failures == 1);
    assert(!service.get(world, "before_listener_exception", plugin).value);
    assert(events->unsubscribe(throwing_before_listener_id));
    assert(events->unsubscribe(later_before_listener_id));

    bool listener_after_exception_ran = false;
    const auto throwing_listener_id = events->subscribe(
        EventFilter{DynamicPropertyEventKind::AfterMutation, {}, {}, own,
                    std::string("listener_exception")},
        [](DynamicPropertyEvent &) { throw std::runtime_error("listener failed"); });
    const auto later_listener_id = events->subscribe(
        EventFilter{DynamicPropertyEventKind::AfterMutation, {}, {}, own,
                    std::string("listener_exception")},
        [&](DynamicPropertyEvent &) { listener_after_exception_ran = true; });
    const auto audit_count_before_listener_failure = audit->records().size();
    const auto listener_exception_result = service.set(
        world, "listener_exception", true, plugin);
    assert(listener_exception_result.ok());
    assert(listener_after_exception_ran);
    assert(reported_listener_failures == 2);
    assert(audit->records().size() == audit_count_before_listener_failure + 1);
    assert(events->unsubscribe(throwing_listener_id));
    assert(events->unsubscribe(later_listener_id));

    CollectionRef online_player{DynamicPropertyTarget::onlinePlayer("xuid-1"), own};
    CollectionRef offline_player{DynamicPropertyTarget::offlinePlayer("xuid-1"), own};
    CollectionRef stored_entity{DynamicPropertyTarget::storedEntity("entity-42"), own};
    CollectionRef item{DynamicPropertyTarget::playerItem("xuid-1", InventorySection::Main, 4), own};
    CollectionRef block{DynamicPropertyTarget::blockEntity({"overworld", 10, 64, 10}), own};
    assert(service.set(online_player, "rank", std::string("owner"), plugin).ok());
    assert(service.set(offline_player, "last_seen", 1234.0, plugin).ok());
    assert(service.set(stored_entity, "protected", true, plugin).ok());
    assert(service.set(item, "bound", std::string("xuid-1"), plugin).ok());
    assert(service.set(block, "network_id", std::string("alpha"), plugin).ok());
    CollectionRef invalid_item{
        DynamicPropertyTarget::playerItem("xuid-1", InventorySection::None, 0), own};
    assert(service.set(invalid_item, "invalid", true, plugin).status ==
           DynamicPropertyStatus::InvalidTarget);

    std::string before_transaction_id;
    std::string after_transaction_id;
    std::size_t after_transaction_collection_count = 0;
    const auto before_transaction_subscription = events->subscribe(
        EventFilter{DynamicPropertyEventKind::BeforeTransaction, {}, {}, {}, {}},
        [&](DynamicPropertyEvent &event) {
            before_transaction_id = event.transaction_id;
            event.transaction_id = "listener-forged-id";
            event.collections.clear();
            event.before.clear();
        });
    const auto after_transaction_subscription = events->subscribe(
        EventFilter{DynamicPropertyEventKind::AfterTransaction, {}, {}, {}, {}},
        [&](DynamicPropertyEvent &event) {
            after_transaction_id = event.transaction_id;
            after_transaction_collection_count = event.collections.size();
        });
    DynamicPropertyTransaction transaction;
    transaction.audit_reason = "atomic cross-target update";
    transaction.operations.push_back(SetPropertyOperation{world, "season", std::string("winter"), {}});
    transaction.operations.push_back(SetPropertyOperation{offline_player, "season", std::string("winter"), {}});
    auto tx_result = service.transact(transaction, plugin);
    assert(tx_result.ok());
    assert(tx_result.transaction_id == before_transaction_id);
    assert(tx_result.transaction_id == after_transaction_id);
    assert(after_transaction_collection_count == 2);
    assert(events->unsubscribe(before_transaction_subscription));
    assert(events->unsubscribe(after_transaction_subscription));
    assert(std::get<std::string>(*service.get(world, "season", plugin).value) == "winter");

    const auto before_failed_capture = service.capture(world, plugin);
    assert(before_failed_capture.snapshot);
    const auto before_failed_tx = before_failed_capture.snapshot->properties.at("season");
    DynamicPropertyTransaction failed_tx;
    failed_tx.operations.push_back(SetPropertyOperation{world, "season", std::string("spring"), {}});
    failed_tx.operations.push_back(SetPropertyOperation{offline_player, "season", std::string("spring"), 1});
    auto failed_result = service.transact(failed_tx, plugin);
    assert(!failed_result.ok());
    assert(failed_result.rolled_back);
    const auto after_failed_capture = service.capture(world, plugin);
    assert(after_failed_capture.snapshot);
    assert(after_failed_capture.snapshot->properties.at("season") == before_failed_tx);

    const CollectionRef old_pack{DynamicPropertyTarget::world(), "11111111-1111-1111-1111-111111111111"};
    const CollectionRef new_pack{DynamicPropertyTarget::world(), "22222222-2222-2222-2222-222222222222"};
    assert(service.set(old_pack, "legacy", std::string("data"), admin).ok());
    auto migrated = service.migrateCollection(old_pack, new_pack, admin);
    assert(migrated.ok());
    const auto old_after_migration = service.capture(old_pack, admin);
    assert(old_after_migration.snapshot && !old_after_migration.snapshot->exists);
    assert(std::get<std::string>(*service.get(new_pack, "legacy", admin).value) == "data");
    auto self_rename = service.apply(
        RenameCollectionOperation{DynamicPropertyTarget::world(), new_pack.collection,
                                  new_pack.collection, {}, ImportPolicy::Replace, {}}, admin);
    assert(self_rename.status == DynamicPropertyStatus::InvalidCollection);
    assert(std::get<std::string>(*service.get(new_pack, "legacy", admin).value) == "data");

    const CollectionRef rename_source{
        DynamicPropertyTarget::world(), "33333333-3333-3333-3333-333333333333"};
    const CollectionRef rename_destination{
        DynamicPropertyTarget::world(), "44444444-4444-4444-4444-444444444444"};
    assert(service.set(rename_source, "source_value", true, admin).ok());
    assert(service.set(rename_destination, "destination_value", true, admin).ok());
    const auto rename_source_before = service.capture(rename_source, admin);
    const auto rename_destination_before = service.capture(rename_destination, admin);
    assert(rename_source_before.snapshot && rename_destination_before.snapshot);
    auto stale_rename_destination = service.apply(
        RenameCollectionOperation{
            DynamicPropertyTarget::world(), rename_source.collection,
            rename_destination.collection, rename_source_before.snapshot->revision,
            ImportPolicy::Merge, rename_destination_before.snapshot->revision + 1},
        admin);
    assert(stale_rename_destination.status == DynamicPropertyStatus::Conflict);
    assert(service.get(rename_source, "source_value", admin).ok());
    assert(service.get(rename_destination, "destination_value", admin).ok());
    auto revision_checked_rename = service.apply(
        RenameCollectionOperation{
            DynamicPropertyTarget::world(), rename_source.collection,
            rename_destination.collection, rename_source_before.snapshot->revision,
            ImportPolicy::Merge, rename_destination_before.snapshot->revision},
        admin);
    assert(revision_checked_rename.ok());
    const auto rename_source_after = service.capture(rename_source, admin);
    assert(rename_source_after.snapshot && !rename_source_after.snapshot->exists);
    assert(service.get(rename_destination, "source_value", admin).ok());
    assert(service.get(rename_destination, "destination_value", admin).ok());

    const CollectionRef guarded_migration_source{
        DynamicPropertyTarget::world(), "55555555-5555-5555-5555-555555555555"};
    const CollectionRef guarded_migration_destination{
        DynamicPropertyTarget::world(), "66666666-6666-6666-6666-666666666666"};
    assert(service.set(guarded_migration_source, "source_value", true, admin).ok());
    assert(service.set(guarded_migration_destination, "destination_value", true, admin).ok());
    const auto guarded_source_before = service.capture(guarded_migration_source, admin);
    const auto guarded_destination_before = service.capture(guarded_migration_destination, admin);
    assert(guarded_source_before.snapshot && guarded_destination_before.snapshot);
    const auto stale_migration_source = service.migrateCollection(
        guarded_migration_source, guarded_migration_destination, admin,
        ImportPolicy::Merge, true, guarded_source_before.snapshot->revision + 1,
        guarded_destination_before.snapshot->revision);
    assert(stale_migration_source.status == DynamicPropertyStatus::Conflict);
    const auto stale_migration_destination = service.migrateCollection(
        guarded_migration_source, guarded_migration_destination, admin,
        ImportPolicy::Merge, true, guarded_source_before.snapshot->revision,
        guarded_destination_before.snapshot->revision + 1);
    assert(stale_migration_destination.status == DynamicPropertyStatus::Conflict);
    const auto guarded_migration = service.migrateCollection(
        guarded_migration_source, guarded_migration_destination, admin,
        ImportPolicy::Merge, true, guarded_source_before.snapshot->revision,
        guarded_destination_before.snapshot->revision);
    assert(guarded_migration.ok());
    const auto guarded_source_after = service.capture(guarded_migration_source, admin);
    assert(guarded_source_after.snapshot && !guarded_source_after.snapshot->exists);
    assert(service.get(guarded_migration_destination, "source_value", admin).ok());
    assert(service.get(guarded_migration_destination, "destination_value", admin).ok());

    auto exported = service.exportCollection(world, plugin);
    assert(exported.ok());
    CollectionRef imported{DynamicPropertyTarget::world("backup"), own};
    auto imported_result = service.importCollection(imported, exported.document, plugin, ImportPolicy::Replace);
    assert(imported_result.ok());
    const auto imported_capture = service.capture(imported, plugin);
    const auto world_capture = service.capture(world, plugin);
    assert(imported_capture.snapshot && world_capture.snapshot);
    assert(imported_capture.snapshot->properties == world_capture.snapshot->properties);

    TransferPropertyOperation move_property{
        world, "name", online_player, "server_name", {}, {}, true, false};
    auto moved = service.apply(move_property, plugin);
    assert(moved.ok());
    assert(service.get(world, "name", plugin).status == DynamicPropertyStatus::NotFound);
    assert(std::get<std::string>(*service.get(online_player, "server_name", plugin).value) == "Kingdom");
    auto self_move = service.apply(
        TransferPropertyOperation{online_player, "server_name", online_player, "server_name",
                                  {}, {}, true, true}, plugin);
    assert(self_move.status == DynamicPropertyStatus::InvalidKey);
    assert(std::get<std::string>(*service.get(online_player, "server_name", plugin).value) == "Kingdom");

    const auto same_collection_before = service.capture(online_player, plugin);
    assert(same_collection_before.snapshot);
    const auto same_collection_revision = same_collection_before.snapshot->revision;
    const auto same_collection_copy = service.apply(
        TransferPropertyOperation{
            online_player, "server_name", online_player, "server_name_copy",
            same_collection_revision, same_collection_revision, false, false},
        plugin);
    assert(same_collection_copy.ok());
    assert(std::get<std::string>(
               *service.get(online_player, "server_name_copy", plugin).value) == "Kingdom");
    const auto stale_destination_only = service.apply(
        TransferPropertyOperation{
            online_player, "server_name", online_player, "stale_destination_copy",
            {}, same_collection_revision, false, false},
        plugin);
    assert(stale_destination_only.status == DynamicPropertyStatus::Conflict);
    assert(!service.get(online_player, "stale_destination_copy", plugin).value);
    const auto same_collection_after = service.capture(online_player, plugin);
    assert(same_collection_after.snapshot);
    const auto conflicting_same_collection_revisions = service.apply(
        TransferPropertyOperation{
            online_player, "server_name", online_player, "conflicting_revision_copy",
            same_collection_after.snapshot->revision,
            same_collection_after.snapshot->revision + 1, false, false},
        plugin);
    assert(conflicting_same_collection_revisions.status ==
           DynamicPropertyStatus::InvalidValue);
    assert(!service.get(online_player, "conflicting_revision_copy", plugin).value);

    AccessContext external{"admin", "script-api", true, MutationOrigin::ScriptApi, "hook"};
    MutationOrigin observed_external_origin = MutationOrigin::Unknown;
    const auto external_subscription = events->subscribe(
        EventFilter{DynamicPropertyEventKind::BeforeExternalMutation, {}, {}, {}, {}},
        [&](DynamicPropertyEvent &event) { observed_external_origin = event.actor.origin; });
    SetPropertyOperation external_operation{world, "external", true, {}};
    auto gate = service.beforeExternalMutation(external_operation, external, true);
    assert(gate.decision == ExternalMutationDecision::Allow);
    assert(observed_external_origin == MutationOrigin::ScriptApi);
    assert(events->unsubscribe(external_subscription));
    auto native_result = adapter->apply(external_operation, false);
    service.afterExternalMutation(external_operation, native_result, external, gate.transaction_id);
    assert(service.get(world, "external", plugin).ok());

    const auto records = audit->records();
    assert(records.size() >= 15);
    assert(std::any_of(records.begin(), records.end(), [](const auto &record) { return record.external; }));

    auto listed = service.listCollections(DynamicPropertyTarget::world(), plugin);
    assert(listed.ok());
    for (const auto &collection : listed.collections)
        assert(collection.starts_with("endstone-plugin:test.plugin:"));
    auto listed_admin = service.listCollections(DynamicPropertyTarget::world(), admin);
    assert(listed_admin.ok());
    assert(std::find(listed_admin.collections.begin(), listed_admin.collections.end(), new_pack.collection) != listed_admin.collections.end());

    adapter->setTargetAvailable(DynamicPropertyTarget::offlinePlayer("missing"), false);
    CollectionRef missing{DynamicPropertyTarget::offlinePlayer("missing"), own};
    assert(service.capture(missing, plugin).status == DynamicPropertyStatus::TargetUnavailable);

    std::string json_error;
    assert(!decodeCollectionJson("{bad", &json_error));
    assert(!json_error.empty());
    assert(!decodeCollectionJson("{\"properties\":{}}", &json_error));
    assert(!decodeCollectionJson(
        "{\"schema\":1,\"properties\":{\"x\":{\"type\":\"bool\",\"value\":true,\"extra\":1}}}",
        &json_error));
    assert(!validateValue(std::numeric_limits<double>::infinity()).valid);

    const std::string utf8_key = "caf\xC3\xA9";
    const std::string utf8_collection = "plugin:\xE4\xB8\x96\xE7\x95\x8C";
    const std::string utf8_emoji = "\xF0\x9F\x98\x80";
    assert(validateKey(utf8_key).valid);
    assert(validateCollectionName(utf8_collection).valid);
    assert(validateValue(DynamicPropertyValue{utf8_emoji}).valid);

    const std::string invalid_utf8_values[] = {
        std::string("\x80", 1),
        std::string("\xC0\xAF", 2),
        std::string("\xE2\x82", 2),
        std::string("\xED\xA0\x80", 3),
        std::string("\xF4\x90\x80\x80", 4),
    };
    for (const auto &invalid_utf8 : invalid_utf8_values) {
        assert(!validateKey(invalid_utf8).valid);
        assert(!validateCollectionName(invalid_utf8).valid);
        assert(!validateValue(DynamicPropertyValue{invalid_utf8}).valid);
    }

    const std::string raw_utf8_document =
        "{\"schema\":1,\"properties\":{\"" + utf8_key +
        "\":{\"type\":\"string\",\"value\":\"" + utf8_emoji + "\"}}}";
    const auto raw_utf8_decoded = decodeCollectionJson(raw_utf8_document, &json_error);
    assert(raw_utf8_decoded);
    assert(std::get<std::string>(raw_utf8_decoded->at(utf8_key)) == utf8_emoji);

    const auto escaped_unicode_decoded = decodeCollectionJson(
        "{\"schema\":1,\"properties\":{\"caf\\u00e9\":{\"type\":\"string\","
        "\"value\":\"\\uD83D\\uDE00\"}}}",
        &json_error);
    assert(escaped_unicode_decoded);
    assert(std::get<std::string>(escaped_unicode_decoded->at(utf8_key)) == utf8_emoji);

    const std::string invalid_raw_utf8_document =
        "{\"schema\":1,\"properties\":{\"x\":{\"type\":\"string\",\"value\":\"" +
        std::string("\xED\xA0\x80", 3) + "\"}}}";
    assert(!decodeCollectionJson(invalid_raw_utf8_document, &json_error));
    const char *invalid_surrogate_documents[] = {
        "{\"schema\":1,\"properties\":{\"x\":{\"type\":\"string\",\"value\":\"\\uD83D\"}}}",
        "{\"schema\":1,\"properties\":{\"x\":{\"type\":\"string\",\"value\":\"\\uD83D\\u0041\"}}}",
        "{\"schema\":1,\"properties\":{\"x\":{\"type\":\"string\",\"value\":\"\\uDE00\"}}}",
    };
    for (const char *invalid_surrogate_document : invalid_surrogate_documents) {
        assert(!decodeCollectionJson(invalid_surrogate_document, &json_error));
        assert(!json_error.empty());
    }

    ValidationLimits one_property_limit;
    one_property_limit.max_properties_per_collection = 1;
    auto limited_adapter = makeInMemoryDynamicPropertyAdapter();
    DynamicPropertyService limited_service(limited_adapter, one_property_limit);
    AccessContext limited_plugin{"limit-test", "tester", false, MutationOrigin::Api, {}};
    const auto limited_collection = limited_service.accessPolicy().pluginCollection(
        limited_plugin.plugin_id, "main");
    CollectionRef limited_world{DynamicPropertyTarget::world(), limited_collection};
    CollectionRef limited_offline{
        DynamicPropertyTarget::offlinePlayer("limit-xuid"), limited_collection};
    assert(limited_service.set(limited_world, "first", true, limited_plugin).ok());
    assert(limited_service.set(limited_world, "second", true, limited_plugin).status ==
           DynamicPropertyStatus::InvalidValue);
    DynamicPropertyTransaction limited_transaction;
    limited_transaction.operations = {
        SetPropertyOperation{limited_offline, "first", true, {}},
        SetPropertyOperation{limited_offline, "second", true, {}},
    };
    assert(limited_service.transact(limited_transaction, limited_plugin).status ==
           DynamicPropertyStatus::InvalidValue);
    const auto limited_offline_capture = limited_service.capture(limited_offline, limited_plugin);
    assert(limited_offline_capture.snapshot && !limited_offline_capture.snapshot->exists);

    auto reentrant_adapter = makeInMemoryDynamicPropertyAdapter();
    auto reentrant_events = std::make_shared<DynamicPropertyEventBus>();
    DynamicPropertyService reentrant_service(
        reentrant_adapter, one_property_limit, reentrant_events);
    AccessContext reentrant_plugin{
        "reentrant-test", "tester", false, MutationOrigin::Api, {}};
    CollectionRef reentrant_world{
        DynamicPropertyTarget::world(),
        reentrant_service.accessPolicy().pluginCollection(
            reentrant_plugin.plugin_id, "main")};
    bool inner_mutation_ran = false;
    const auto reentrant_listener_id = reentrant_events->subscribe(
        EventFilter{DynamicPropertyEventKind::BeforeMutation, {}, {},
                    reentrant_world.collection, std::string("outer")},
        [&](DynamicPropertyEvent &) {
            inner_mutation_ran = true;
            assert(reentrant_service.set(
                reentrant_world, "inner", true, reentrant_plugin).ok());
        });
    const auto reentrant_outer = reentrant_service.set(
        reentrant_world, "outer", true, reentrant_plugin);
    assert(inner_mutation_ran);
    assert(reentrant_outer.status == DynamicPropertyStatus::InvalidValue);
    const auto reentrant_capture = reentrant_service.capture(
        reentrant_world, reentrant_plugin);
    assert(reentrant_capture.snapshot);
    assert(reentrant_capture.snapshot->properties.size() == 1);
    assert(reentrant_capture.snapshot->properties.contains("inner"));
    assert(reentrant_events->unsubscribe(reentrant_listener_id));

    auto shared_adapter = makeInMemoryDynamicPropertyAdapter();
    auto first_service_events = std::make_shared<DynamicPropertyEventBus>();
    auto second_service_events = std::make_shared<DynamicPropertyEventBus>();
    DynamicPropertyService first_shared_service(
        shared_adapter, one_property_limit, first_service_events);
    DynamicPropertyService second_shared_service(
        shared_adapter, one_property_limit, second_service_events);
    AccessContext shared_plugin{
        "shared-adapter-limit", "tester", false, MutationOrigin::Api, {}};
    CollectionRef shared_world{
        DynamicPropertyTarget::world(),
        first_shared_service.accessPolicy().pluginCollection(
            shared_plugin.plugin_id, "main")};
    std::barrier callbacks_ready(2);
    const auto align_callback = [&](DynamicPropertyEvent &) {
        callbacks_ready.arrive_and_wait();
    };
    const auto first_align_id = first_service_events->subscribe(
        EventFilter{DynamicPropertyEventKind::BeforeMutation, {}, {}, {}, {}}, align_callback);
    const auto second_align_id = second_service_events->subscribe(
        EventFilter{DynamicPropertyEventKind::BeforeMutation, {}, {}, {}, {}}, align_callback);
    std::array<OperationResult, 2> concurrent_results;
    std::thread first_writer([&] {
        concurrent_results[0] = first_shared_service.set(
            shared_world, "one", true, shared_plugin);
    });
    std::thread second_writer([&] {
        concurrent_results[1] = second_shared_service.set(
            shared_world, "two", true, shared_plugin);
    });
    first_writer.join();
    second_writer.join();
    assert(std::count_if(
        concurrent_results.begin(), concurrent_results.end(),
        [](const OperationResult &result) { return result.ok(); }) == 1);
    assert(std::count_if(
        concurrent_results.begin(), concurrent_results.end(),
        [](const OperationResult &result) {
            return result.status == DynamicPropertyStatus::InvalidValue;
        }) == 1);
    const auto shared_capture = first_shared_service.capture(
        shared_world, shared_plugin);
    assert(shared_capture.snapshot && shared_capture.snapshot->properties.size() == 1);
    assert(first_service_events->unsubscribe(first_align_id));
    assert(second_service_events->unsubscribe(second_align_id));

    auto copied_request_adapter = makeInMemoryDynamicPropertyAdapter();
    auto copied_request_events = std::make_shared<DynamicPropertyEventBus>();
    auto copied_request_audit = std::make_shared<VectorAuditSink>();
    DynamicPropertyService copied_request_service(
        copied_request_adapter, one_property_limit, copied_request_events,
        copied_request_audit);
    AccessContext mutable_context{
        "copy-test", "tester", false, MutationOrigin::Api, {}};
    CollectionRef copied_request_world{
        DynamicPropertyTarget::world(),
        copied_request_service.accessPolicy().pluginCollection(
            mutable_context.plugin_id, "main")};
    DynamicPropertyOperation mutable_operation = SetManyOperation{
        copied_request_world, {{"first", true}}, {}};
    const auto mutation_listener_id = copied_request_events->subscribe(
        EventFilter{DynamicPropertyEventKind::BeforeMutation, {}, {},
                    copied_request_world.collection, {}},
        [&](DynamicPropertyEvent &) {
            std::get<SetManyOperation>(mutable_operation).values.emplace("second", true);
            mutable_context.plugin_id = "listener-forged-plugin";
        });
    const auto copied_request_result = copied_request_service.apply(
        mutable_operation, mutable_context);
    assert(copied_request_result.ok());
    const auto copied_request_capture = copied_request_service.capture(
        copied_request_world, admin);
    assert(copied_request_capture.snapshot);
    assert(copied_request_capture.snapshot->properties.size() == 1);
    assert(copied_request_capture.snapshot->properties.contains("first"));
    const auto copied_request_records = copied_request_audit->records();
    assert(copied_request_records.size() == 1);
    assert(copied_request_records.front().actor.plugin_id == "copy-test");
    assert(copied_request_events->unsubscribe(mutation_listener_id));

    auto observe_only_adapter = std::make_shared<NoExternalCancellationAdapter>(
        makeInMemoryDynamicPropertyAdapter());
    DynamicPropertyService observe_only_service(observe_only_adapter);
    const auto invalid_external = observe_only_service.beforeExternalMutation(
        SetPropertyOperation{world, "", true, {}}, admin, true);
    assert(invalid_external.status == DynamicPropertyStatus::InvalidKey);
    assert(invalid_external.decision == ExternalMutationDecision::ObserveOnly);

    auto failing_capture_adapter = std::make_shared<NoExternalCancellationAdapter>(
        makeInMemoryDynamicPropertyAdapter(), true);
    DynamicPropertyService failing_capture_service(failing_capture_adapter);
    const auto capture_failure = failing_capture_service.set(
        world, "must-not-commit", true, admin);
    assert(capture_failure.status == DynamicPropertyStatus::AdapterError);

    const auto capabilities = service.capabilities();
    assert(capabilities.offline_players);
    assert(capabilities.stored_entities);
    assert(capabilities.external_change_cancellation);
    assert(!capabilities.completeControl()); // exact native gates intentionally remain closed.
    assert(requiredNativeDynamicPropertySymbols().size() == 28);
    assert(nativeDynamicPropertySymbolName(
        NativeDynamicPropertySymbol::OfflinePlayerStorageWrite) ==
        "offline_player_storage_write");
    assert(!nativeServiceCanRegister());

    std::cout << "dynamic properties tests passed\n";
    return 0;
}
