#include "endstone_dynamic_properties/bds_26_30_adapter.h"
#include "endstone_dynamic_properties/generated/native_manifest_data.h"
#include "endstone_dynamic_properties/live_service.h"

#include <endstone/plugin/service_manager.h>
#include <endstone/server.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <cmath>
#include <cstdint>
#include <deque>
#include <initializer_list>
#include <limits>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>
#include <variant>
#include <vector>

#ifndef ENDSTONE_DYNAMIC_PROPERTIES_PYTHON_VERSION
#error "ENDSTONE_DYNAMIC_PROPERTIES_PYTHON_VERSION must be supplied by CMake"
#endif

namespace py = pybind11;

namespace endstone_dynamic_properties {
namespace {

std::shared_ptr<LiveDynamicPropertyService> loadService(endstone::Server &server) noexcept {
    try {
        return server.getServiceManager().load<LiveDynamicPropertyService>(
            std::string(DynamicPropertyServiceName));
    } catch (...) {
        return {};
    }
}

AccessContext testerContext() {
    AccessContext context;
    context.plugin_id = "dynamic-properties-tester";
    context.actor_id = "dynamic-properties-tester";
    context.raw_admin = false;
    context.origin = MutationOrigin::Command;
    context.reason = "in-game dynamic-properties acceptance test";
    return context;
}

void rejectUnknownFields(
    const py::dict &input,
    std::initializer_list<std::string_view> allowed,
    std::string_view description) {
    for (const auto &[raw_key, raw_value] : input) {
        static_cast<void>(raw_value);
        if (!py::isinstance<py::str>(raw_key)) {
            throw py::value_error(
                std::string(description) + " keys must be strings");
        }
        const auto key = py::cast<std::string>(raw_key);
        bool found = false;
        for (const auto allowed_key : allowed) {
            if (key == allowed_key) {
                found = true;
                break;
            }
        }
        if (!found) {
            throw py::value_error(
                std::string(description) + " contains unsupported field '" + key + "'");
        }
    }
}

std::string requireString(
    const py::dict &input,
    std::string_view key,
    std::string_view description) {
    const auto python_key = py::str(std::string(key));
    if (!input.contains(python_key)) {
        throw py::value_error(
            std::string(description) + " requires '" + std::string(key) + "'");
    }
    const auto raw_value = input[python_key];
    if (!py::isinstance<py::str>(raw_value)) {
        throw py::value_error(
            std::string(description) + " field '" + std::string(key) +
            "' must be a string");
    }
    auto value = py::cast<std::string>(raw_value);
    if (value.empty()) {
        throw py::value_error(
            std::string(description) + " field '" + std::string(key) +
            "' must not be empty");
    }
    return value;
}

std::string optionalString(
    const py::dict &input,
    std::string_view key,
    std::string default_value,
    std::string_view description) {
    if (!input.contains(py::str(std::string(key)))) return default_value;
    return requireString(input, key, description);
}

std::string requireIdentity(
    const py::dict &input,
    std::string_view primary_key,
    std::string_view description) {
    const bool has_primary = input.contains(py::str(std::string(primary_key)));
    const bool has_alias = input.contains(py::str("identity"));
    if (has_primary && has_alias) {
        throw py::value_error(
            std::string(description) + " must not provide both '" +
            std::string(primary_key) + "' and 'identity'");
    }
    if (has_primary) return requireString(input, primary_key, description);
    if (has_alias) return requireString(input, "identity", description);
    throw py::value_error(
        std::string(description) + " requires '" + std::string(primary_key) +
        "' (or the 'identity' alias)");
}

std::int32_t requireInt32(
    const py::dict &input,
    std::string_view key,
    std::string_view description,
    bool require_non_negative = false) {
    const auto python_key = py::str(std::string(key));
    if (!input.contains(python_key)) {
        throw py::value_error(
            std::string(description) + " requires '" + std::string(key) + "'");
    }
    const auto raw_value = input[python_key];
    if (py::isinstance<py::bool_>(raw_value) || !py::isinstance<py::int_>(raw_value)) {
        throw py::value_error(
            std::string(description) + " field '" + std::string(key) +
            "' must be an integer");
    }
    const auto value = py::cast<std::int64_t>(raw_value);
    if (value < std::numeric_limits<std::int32_t>::min() ||
        value > std::numeric_limits<std::int32_t>::max()) {
        throw py::value_error(
            std::string(description) + " field '" + std::string(key) +
            "' exceeds the signed 32-bit range");
    }
    if (require_non_negative && value < 0) {
        throw py::value_error(
            std::string(description) + " field '" + std::string(key) +
            "' must be non-negative");
    }
    return static_cast<std::int32_t>(value);
}

BlockLocation requireBlockLocation(const py::handle &raw_location) {
    if (!py::isinstance<py::dict>(raw_location)) {
        throw py::value_error("target field 'block' must be a mapping");
    }
    const auto location = py::reinterpret_borrow<py::dict>(raw_location);
    rejectUnknownFields(location, {"dimension", "x", "y", "z"}, "block location");
    BlockLocation result;
    result.dimension = optionalString(location, "dimension", "overworld", "block location");
    result.x = requireInt32(location, "x", "block location");
    result.y = requireInt32(location, "y", "block location");
    result.z = requireInt32(location, "z", "block location");
    return result;
}

DynamicPropertyTarget parseTarget(const py::dict &input) {
    const auto kind = requireString(input, "kind", "target");
    const auto world_id = optionalString(input, "world_id", "default", "target");

    if (kind == "world") {
        rejectUnknownFields(input, {"kind", "world_id"}, "world target");
        return DynamicPropertyTarget::world(world_id);
    }
    if (kind == "online_player") {
        rejectUnknownFields(
            input, {"kind", "world_id", "xuid", "identity"}, "online-player target");
        return DynamicPropertyTarget::onlinePlayer(
            requireIdentity(input, "xuid", "online-player target"), world_id);
    }
    if (kind == "offline_player") {
        rejectUnknownFields(
            input, {"kind", "world_id", "xuid", "identity"}, "offline-player target");
        return DynamicPropertyTarget::offlinePlayer(
            requireIdentity(input, "xuid", "offline-player target"), world_id);
    }
    if (kind == "loaded_entity") {
        rejectUnknownFields(
            input, {"kind", "world_id", "entity_id", "identity"},
            "loaded-entity target");
        return DynamicPropertyTarget::loadedEntity(
            requireIdentity(input, "entity_id", "loaded-entity target"), world_id);
    }
    if (kind == "stored_entity") {
        rejectUnknownFields(
            input, {"kind", "world_id", "entity_id", "identity"},
            "stored-entity target");
        return DynamicPropertyTarget::storedEntity(
            requireIdentity(input, "entity_id", "stored-entity target"), world_id);
    }

    InventorySection section = InventorySection::None;
    if (kind == "player_inventory_slot") section = InventorySection::Main;
    else if (kind == "player_armor_slot") section = InventorySection::Armor;
    else if (kind == "player_offhand_slot") section = InventorySection::Offhand;
    else if (kind == "player_ender_chest_slot") section = InventorySection::EnderChest;
    if (section != InventorySection::None) {
        rejectUnknownFields(
            input, {"kind", "world_id", "xuid", "identity", "slot"},
            "player-item target");
        return DynamicPropertyTarget::playerItem(
            requireIdentity(input, "xuid", "player-item target"), section,
            requireInt32(input, "slot", "player-item target", true), world_id);
    }

    if (kind == "block_container_slot") {
        rejectUnknownFields(
            input, {"kind", "world_id", "block", "slot"},
            "block-container target");
        if (!input.contains(py::str("block"))) {
            throw py::value_error("block-container target requires 'block'");
        }
        return DynamicPropertyTarget::blockContainerItem(
            requireBlockLocation(input[py::str("block")]),
            requireInt32(input, "slot", "block-container target", true), world_id);
    }
    if (kind == "dropped_item") {
        rejectUnknownFields(
            input, {"kind", "world_id", "item_entity_id", "identity"},
            "dropped-item target");
        return DynamicPropertyTarget::droppedItem(
            requireIdentity(input, "item_entity_id", "dropped-item target"), world_id);
    }
    if (kind == "block_entity") {
        rejectUnknownFields(
            input, {"kind", "world_id", "block"}, "block-entity target");
        if (!input.contains(py::str("block"))) {
            throw py::value_error("block-entity target requires 'block'");
        }
        return DynamicPropertyTarget::blockEntity(
            requireBlockLocation(input[py::str("block")]), world_id);
    }

    throw py::value_error("unsupported target kind '" + kind + "'");
}

double requireFiniteNumber(
    const py::handle &raw_value,
    std::string_view description) {
    if (py::isinstance<py::bool_>(raw_value) ||
        (!py::isinstance<py::int_>(raw_value) &&
         !py::isinstance<py::float_>(raw_value))) {
        throw py::value_error(std::string(description) + " must be numeric");
    }
    const auto value = py::cast<double>(raw_value);
    if (!std::isfinite(value)) {
        throw py::value_error(std::string(description) + " must be finite");
    }
    return value;
}

DynamicPropertyValue parseValue(const py::handle &raw_value) {
    if (py::isinstance<py::bool_>(raw_value)) {
        return py::cast<bool>(raw_value);
    }
    if (py::isinstance<py::int_>(raw_value) ||
        py::isinstance<py::float_>(raw_value)) {
        return requireFiniteNumber(raw_value, "numeric dynamic-property value");
    }
    if (py::isinstance<py::str>(raw_value)) {
        return py::cast<std::string>(raw_value);
    }
    if (py::isinstance<py::dict>(raw_value)) {
        const auto vector = py::reinterpret_borrow<py::dict>(raw_value);
        rejectUnknownFields(vector, {"x", "y", "z"}, "vector value");
        if (!vector.contains(py::str("x")) || !vector.contains(py::str("y")) ||
            !vector.contains(py::str("z"))) {
            throw py::value_error("vector value requires exactly 'x', 'y', and 'z'");
        }
        return Vector3{
            requireFiniteNumber(vector[py::str("x")], "vector x"),
            requireFiniteNumber(vector[py::str("y")], "vector y"),
            requireFiniteNumber(vector[py::str("z")], "vector z")};
    }
    throw py::value_error(
        "dynamic-property value must be bool, finite number, string, or an x/y/z mapping");
}

py::object valueToObject(const DynamicPropertyValue &value) {
    return std::visit(
        [](const auto &entry) -> py::object {
            using Value = std::decay_t<decltype(entry)>;
            if constexpr (std::is_same_v<Value, bool>) {
                return py::bool_(entry);
            } else if constexpr (std::is_same_v<Value, double>) {
                return py::float_(entry);
            } else if constexpr (std::is_same_v<Value, std::string>) {
                return py::str(entry);
            } else {
                py::dict out;
                out["x"] = entry.x;
                out["y"] = entry.y;
                out["z"] = entry.z;
                return std::move(out);
            }
        },
        value);
}

py::dict targetToDict(const DynamicPropertyTarget &target) {
    py::dict out;
    out["kind"] = std::string(targetKindName(target.kind));
    out["world_id"] = target.world_id;
    if (!target.xuid.empty()) out["xuid"] = target.xuid;
    if (!target.entity_id.empty()) out["entity_id"] = target.entity_id;
    if (!target.item_entity_id.empty()) out["item_entity_id"] = target.item_entity_id;
    if (target.block) {
        py::dict block;
        block["dimension"] = target.block->dimension;
        block["x"] = target.block->x;
        block["y"] = target.block->y;
        block["z"] = target.block->z;
        out["block"] = std::move(block);
    }
    if (target.slot >= 0) out["slot"] = target.slot;
    return out;
}

py::dict snapshotToDict(const CollectionSnapshot &snapshot) {
    py::dict properties;
    for (const auto &[key, value] : snapshot.properties) {
        properties[py::str(key)] = valueToObject(value);
    }

    py::dict out;
    out["target"] = targetToDict(snapshot.ref.target);
    out["collection"] = snapshot.ref.collection;
    out["properties"] = std::move(properties);
    out["byte_count"] = snapshot.byte_count;
    out["revision"] = snapshot.revision;
    out["exists"] = snapshot.exists;
    out["loaded"] = snapshot.loaded;
    out["persistent"] = snapshot.persistent;
    out["writable"] = snapshot.writable;
    return out;
}

py::dict resultDict(
    DynamicPropertyStatus status,
    const std::string &message,
    std::uint64_t revision,
    const CollectionSnapshot *snapshot = nullptr) {
    py::dict out;
    out["ok"] = status == DynamicPropertyStatus::Applied ||
                status == DynamicPropertyStatus::Captured;
    out["status"] = std::string(statusName(status));
    out["message"] = message;
    out["revision"] = revision;
    if (snapshot) out["snapshot"] = snapshotToDict(*snapshot);
    else out["snapshot"] = py::none();
    return out;
}

py::dict operationToDict(const OperationResult &result) {
    const CollectionSnapshot *snapshot = result.after.empty() ? nullptr : &result.after.back();
    return resultDict(result.status, result.message, result.resulting_revision, snapshot);
}

py::dict capabilitiesToDict(const DynamicPropertyCapabilities &caps) {
    py::dict out;
#define ENDSTONE_DYNAMIC_PROPERTIES_CAP(name) out[#name] = caps.name
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(world);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(online_players);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(offline_players);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(loaded_entities);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(stored_entities);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(player_inventory_items);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(player_armor_items);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(player_offhand_items);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(player_ender_chest_items);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(block_container_items);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(dropped_items);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(block_entities);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(block_dynamic_properties);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(read);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(write);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(remove);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(clear);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(list_ids);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(list_collections);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(byte_count);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(bulk_set);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(collection_rename);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(property_copy_move);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(collection_copy_move);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(collection_migration);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(export_import);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(atomic_transactions);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(rollback);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(audit);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(watches);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(external_change_observation);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(external_change_cancellation);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(persistence_flush);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(exact_build_match);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(exact_binary_hash_match);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(symbols_validated);
    ENDSTONE_DYNAMIC_PROPERTIES_CAP(stage_probe_passed);
#undef ENDSTONE_DYNAMIC_PROPERTIES_CAP
    return out;
}

std::string_view eventKindName(DynamicPropertyEventKind kind) noexcept {
    switch (kind) {
    case DynamicPropertyEventKind::BeforeMutation: return "before_mutation";
    case DynamicPropertyEventKind::AfterMutation: return "after_mutation";
    case DynamicPropertyEventKind::BeforeTransaction: return "before_transaction";
    case DynamicPropertyEventKind::AfterTransaction: return "after_transaction";
    case DynamicPropertyEventKind::BeforeExternalMutation:
        return "before_external_mutation";
    case DynamicPropertyEventKind::AfterExternalMutation:
        return "after_external_mutation";
    case DynamicPropertyEventKind::CollectionMigrated: return "collection_migrated";
    }
    return "unknown";
}

std::string_view mutationOriginName(MutationOrigin origin) noexcept {
    switch (origin) {
    case MutationOrigin::Api: return "api";
    case MutationOrigin::Command: return "command";
    case MutationOrigin::ScriptApi: return "script_api";
    case MutationOrigin::Player: return "player";
    case MutationOrigin::WorldLoad: return "world_load";
    case MutationOrigin::StorageLoad: return "storage_load";
    case MutationOrigin::Migration: return "migration";
    case MutationOrigin::Rollback: return "rollback";
    case MutationOrigin::NativeHook: return "native_hook";
    case MutationOrigin::Unknown: return "unknown";
    }
    return "unknown";
}

py::dict eventToDict(const DynamicPropertyEvent &event) {
    py::list collections;
    for (const auto &ref : event.collections) {
        py::dict collection;
        collection["target"] = targetToDict(ref.target);
        collection["collection"] = ref.collection;
        collections.append(std::move(collection));
    }
    py::list before;
    for (const auto &snapshot : event.before) before.append(snapshotToDict(snapshot));
    py::list after;
    for (const auto &snapshot : event.after) after.append(snapshotToDict(snapshot));

    py::dict actor;
    actor["plugin_id"] = event.actor.plugin_id;
    actor["actor_id"] = event.actor.actor_id;
    actor["raw_admin"] = event.actor.raw_admin;
    actor["origin"] = std::string(mutationOriginName(event.actor.origin));
    actor["reason"] = event.actor.reason;

    py::dict out;
    out["kind"] = std::string(eventKindName(event.kind));
    out["transaction_id"] = event.transaction_id;
    out["operation"] = event.operation_name;
    out["actor"] = std::move(actor);
    out["collections"] = std::move(collections);
    if (event.key) out["key"] = *event.key;
    else out["key"] = py::none();
    out["before"] = std::move(before);
    out["after"] = std::move(after);
    out["cancellable"] = event.cancellable;
    out["cancelled"] = event.cancelled;
    out["cancellation_reason"] = event.cancellation_reason;
    return out;
}

struct ExternalWatchState {
    std::mutex mutex;
    endstone::Server *server{};
    std::shared_ptr<DynamicPropertyEventBus> event_bus;
    std::vector<std::uint64_t> subscriptions;
    std::deque<DynamicPropertyEvent> events;
    std::uint64_t dropped{};
    bool active{};
};

ExternalWatchState &externalWatchState() {
    static ExternalWatchState State;
    return State;
}

constexpr std::size_t ExternalWatchLimit = 1024;

py::dict externalWatchStatus(endstone::Server &server) {
    auto &state = externalWatchState();
    std::lock_guard lock(state.mutex);
    py::dict out;
    out["ok"] = true;
    out["status"] = "captured";
    out["active"] = state.active && state.server == &server;
    out["queued"] = state.server == &server ? state.events.size() : 0;
    out["dropped"] = state.server == &server ? state.dropped : 0;
    out["capacity"] = ExternalWatchLimit;
    return out;
}

py::dict stopExternalWatch(endstone::Server &server) {
    auto &state = externalWatchState();
    std::shared_ptr<DynamicPropertyEventBus> event_bus;
    std::vector<std::uint64_t> subscriptions;
    {
        std::lock_guard lock(state.mutex);
        if (state.server == &server) {
            state.active = false;
            event_bus = std::move(state.event_bus);
            subscriptions = std::move(state.subscriptions);
        }
    }
    if (event_bus) {
        for (const auto subscription : subscriptions) {
            event_bus->unsubscribe(subscription);
        }
    }
    return externalWatchStatus(server);
}

py::dict startExternalWatch(endstone::Server &server) {
    const auto service = loadService(server);
    if (!service) {
        py::dict out;
        out["ok"] = false;
        out["status"] = "adapter_unavailable";
        out["message"] = "service unavailable";
        out["active"] = false;
        return out;
    }
    const auto event_bus = service->eventBus();
    if (!event_bus) {
        py::dict out;
        out["ok"] = false;
        out["status"] = "unsupported";
        out["message"] = "service has no event bus";
        out["active"] = false;
        return out;
    }

    auto &state = externalWatchState();
    stopExternalWatch(server);
    {
        std::lock_guard lock(state.mutex);
        state.server = &server;
        state.event_bus = event_bus;
        state.events.clear();
        state.dropped = 0;
        state.active = true;
    }
    const auto capture = [&state, expected_server = &server](DynamicPropertyEvent &event) {
        std::lock_guard lock(state.mutex);
        if (!state.active || state.server != expected_server) return;
        if (state.events.size() == ExternalWatchLimit) {
            state.events.pop_front();
            ++state.dropped;
        }
        state.events.push_back(event);
    };
    std::vector<std::uint64_t> subscriptions;
    subscriptions.push_back(event_bus->subscribe(
        EventFilter{DynamicPropertyEventKind::BeforeExternalMutation, {}, {}, {}, {}},
        capture));
    subscriptions.push_back(event_bus->subscribe(
        EventFilter{DynamicPropertyEventKind::AfterExternalMutation, {}, {}, {}, {}},
        capture));
    {
        std::lock_guard lock(state.mutex);
        state.subscriptions = std::move(subscriptions);
    }
    return externalWatchStatus(server);
}

py::dict drainExternalEvents(endstone::Server &server) {
    auto &state = externalWatchState();
    std::deque<DynamicPropertyEvent> events;
    std::uint64_t dropped = 0;
    bool active = false;
    {
        std::lock_guard lock(state.mutex);
        if (state.server == &server) {
            events.swap(state.events);
            dropped = state.dropped;
            state.dropped = 0;
            active = state.active;
        }
    }
    py::list encoded;
    for (const auto &event : events) encoded.append(eventToDict(event));
    py::dict out;
    out["ok"] = true;
    out["status"] = "captured";
    out["active"] = active;
    out["events"] = std::move(encoded);
    out["dropped"] = dropped;
    out["capacity"] = ExternalWatchLimit;
    return out;
}

bool available(endstone::Server &server) noexcept {
    return static_cast<bool>(loadService(server));
}

py::dict status(endstone::Server &server) {
    py::dict out;
    const auto service = loadService(server);
    const auto activation = inspectBds2633DynamicPropertyActivation(server);
    out["available"] = static_cast<bool>(service);
    out["adapter"] = py::none();
    out["complete_control"] = false;
    out["capabilities"] = py::dict();
    out["runtime_version_match"] = activation.runtime_version_match;
    out["endstone_version_match"] = activation.endstone_version_match;
    out["manifest_activated"] = activation.manifest_activated;
    out["executable_hash_match"] = activation.executable_hash_match;
    out["symbols_validated"] = activation.symbols_validated;
    out["storage_contracts_validated"] = activation.storage_contracts_validated;
    out["external_hooks_validated"] = activation.external_hooks_validated;
    out["stage_probe_passed"] = activation.stage_probe_passed;
    out["verified_bridge_compiled"] = activation.verified_bridge_compiled;
    out["failures"] = activation.failures;
    out["expected_platform"] = std::string(generated::Platform);
    out["expected_bds_package"] = std::string(generated::BdsPackageVersion);
    out["expected_bds_runtime"] = std::string(generated::RuntimeBds);
    out["expected_endstone"] = std::string(generated::EndstoneVersion);
    if (!service) return out;

    const auto caps = service->capabilities();
    out["adapter"] = service->adapterName();
    out["complete_control"] = caps.completeControl();
    out["capabilities"] = capabilitiesToDict(caps);
    return out;
}

py::dict capture(
    endstone::Server &server,
    const py::dict &target,
    const std::string &collection) {
    const auto service = loadService(server);
    if (!service) {
        return resultDict(
            DynamicPropertyStatus::AdapterUnavailable, "service unavailable", 0);
    }
    const CollectionRef ref{parseTarget(target), collection};
    const auto result = service->capture(ref, testerContext());
    const auto *snapshot = result.snapshot ? &*result.snapshot : nullptr;
    return resultDict(
        result.status, result.message, snapshot ? snapshot->revision : 0, snapshot);
}

py::dict listCollections(endstone::Server &server, const py::dict &target) {
    const auto service = loadService(server);
    py::dict out;
    if (!service) {
        out["ok"] = false;
        out["status"] = "adapter_unavailable";
        out["message"] = "service unavailable";
        out["collections"] = py::list();
        return out;
    }
    const auto result = service->listCollections(parseTarget(target), testerContext());
    out["ok"] = result.ok();
    out["status"] = std::string(statusName(result.status));
    out["message"] = result.message;
    out["collections"] = result.collections;
    return out;
}

py::dict setValue(
    endstone::Server &server,
    const py::dict &target,
    const std::string &collection,
    const std::string &key,
    const py::object &value,
    std::optional<std::uint64_t> expected_revision) {
    const auto service = loadService(server);
    if (!service) {
        return resultDict(
            DynamicPropertyStatus::AdapterUnavailable, "service unavailable", 0);
    }
    SetPropertyOperation operation{
        CollectionRef{parseTarget(target), collection}, key, parseValue(value),
        expected_revision};
    return operationToDict(
        service->apply(DynamicPropertyOperation{std::move(operation)}, testerContext()));
}

py::dict removeValue(
    endstone::Server &server,
    const py::dict &target,
    const std::string &collection,
    const std::string &key,
    std::optional<std::uint64_t> expected_revision) {
    const auto service = loadService(server);
    if (!service) {
        return resultDict(
            DynamicPropertyStatus::AdapterUnavailable, "service unavailable", 0);
    }
    RemovePropertyOperation operation{
        CollectionRef{parseTarget(target), collection}, key, expected_revision, false};
    return operationToDict(
        service->apply(DynamicPropertyOperation{std::move(operation)}, testerContext()));
}

py::dict clearCollection(
    endstone::Server &server,
    const py::dict &target,
    const std::string &collection,
    std::optional<std::uint64_t> expected_revision) {
    const auto service = loadService(server);
    if (!service) {
        return resultDict(
            DynamicPropertyStatus::AdapterUnavailable, "service unavailable", 0);
    }
    ClearCollectionOperation operation{
        CollectionRef{parseTarget(target), collection}, expected_revision, false};
    return operationToDict(
        service->apply(DynamicPropertyOperation{std::move(operation)}, testerContext()));
}

py::dict flush(endstone::Server &server, const py::dict &target) {
    const auto service = loadService(server);
    if (!service) {
        return resultDict(
            DynamicPropertyStatus::AdapterUnavailable, "service unavailable", 0);
    }
    return operationToDict(service->flush(parseTarget(target), testerContext()));
}

} // namespace
} // namespace endstone_dynamic_properties

PYBIND11_MODULE(_endstone_dynamic_properties_live, module) {
    module.doc() = "Live tester bridge to endstone:dynamic-properties:v1";
    module.attr("__version__") = ENDSTONE_DYNAMIC_PROPERTIES_PYTHON_VERSION;
    module.def(
        "available", &endstone_dynamic_properties::available, py::arg("server"));
    module.def("status", &endstone_dynamic_properties::status, py::arg("server"));
    module.def(
        "capture", &endstone_dynamic_properties::capture, py::arg("server"),
        py::arg("target"), py::arg("collection"));
    module.def(
        "list_collections", &endstone_dynamic_properties::listCollections,
        py::arg("server"), py::arg("target"));
    module.def(
        "set_value", &endstone_dynamic_properties::setValue, py::arg("server"),
        py::arg("target"), py::arg("collection"), py::arg("key"), py::arg("value"),
        py::arg("expected_revision") = py::none());
    module.def(
        "remove_value", &endstone_dynamic_properties::removeValue, py::arg("server"),
        py::arg("target"), py::arg("collection"), py::arg("key"),
        py::arg("expected_revision") = py::none());
    module.def(
        "clear_collection", &endstone_dynamic_properties::clearCollection,
        py::arg("server"), py::arg("target"), py::arg("collection"),
        py::arg("expected_revision") = py::none());
    module.def(
        "flush", &endstone_dynamic_properties::flush, py::arg("server"),
        py::arg("target"));
    module.def(
        "start_external_watch", &endstone_dynamic_properties::startExternalWatch,
        py::arg("server"));
    module.def(
        "drain_external_events", &endstone_dynamic_properties::drainExternalEvents,
        py::arg("server"));
    module.def(
        "external_watch_status", &endstone_dynamic_properties::externalWatchStatus,
        py::arg("server"));
    module.def(
        "stop_external_watch", &endstone_dynamic_properties::stopExternalWatch,
        py::arg("server"));
}
