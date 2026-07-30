#include "endstone_dynamic_properties/in_memory_adapter.h"

#include <algorithm>
#include <atomic>
#include <set>
#include <type_traits>

namespace endstone_dynamic_properties {
namespace {
std::atomic<std::uint64_t> transaction_counter{1};

std::string nextTransactionId() {
    return "memtx-" + std::to_string(transaction_counter.fetch_add(1));
}

std::optional<std::uint64_t> expectedRevision(const DynamicPropertyOperation &operation, const CollectionRef &ref) {
    return std::visit([&](const auto &entry) -> std::optional<std::uint64_t> {
        using T = std::decay_t<decltype(entry)>;
        if constexpr (std::is_same_v<T, SetPropertyOperation> ||
                      std::is_same_v<T, SetManyOperation> ||
                      std::is_same_v<T, RemovePropertyOperation> ||
                      std::is_same_v<T, RemoveManyOperation> ||
                      std::is_same_v<T, ClearCollectionOperation>) {
            return entry.ref == ref ? entry.expected_revision : std::nullopt;
        } else if constexpr (std::is_same_v<T, RenameCollectionOperation>) {
            const CollectionRef source{entry.target, entry.from};
            const CollectionRef destination{entry.target, entry.to};
            if (source == ref) return entry.expected_source_revision;
            if (destination == ref) return entry.expected_destination_revision;
            return std::nullopt;
        } else if constexpr (std::is_same_v<T, TransferPropertyOperation>) {
            if (entry.source == ref && entry.destination == ref) {
                return entry.expected_source_revision
                    ? entry.expected_source_revision
                    : entry.expected_destination_revision;
            }
            if (entry.source == ref) return entry.expected_source_revision;
            if (entry.destination == ref) return entry.expected_destination_revision;
            return std::nullopt;
        } else if constexpr (std::is_same_v<T, TransferCollectionOperation>) {
            if (entry.source == ref) return entry.expected_source_revision;
            if (entry.destination == ref) return entry.expected_destination_revision;
            return std::nullopt;
        } else {
            return entry.destination == ref ? entry.expected_destination_revision : std::nullopt;
        }
    }, operation);
}

OperationResult failure(
    DynamicPropertyStatus status,
    std::string message,
    std::vector<CollectionSnapshot> before = {}) {
    OperationResult out;
    out.status = status;
    out.message = std::move(message);
    out.before = std::move(before);
    return out;
}
} // namespace

DynamicPropertyCapabilities InMemoryDynamicPropertyAdapter::capabilities() const noexcept {
    DynamicPropertyCapabilities out;
    out.world = true;
    out.online_players = true;
    out.offline_players = true;
    out.loaded_entities = true;
    out.stored_entities = true;
    out.player_inventory_items = true;
    out.player_armor_items = true;
    out.player_offhand_items = true;
    out.player_ender_chest_items = true;
    out.block_container_items = true;
    out.dropped_items = true;
    out.block_entities = true;
    out.block_dynamic_properties = true;
    out.read = true;
    out.write = true;
    out.remove = true;
    out.clear = true;
    out.list_ids = true;
    out.list_collections = true;
    out.byte_count = true;
    out.bulk_set = true;
    out.collection_rename = true;
    out.property_copy_move = true;
    out.collection_copy_move = true;
    out.collection_migration = true;
    out.export_import = true;
    out.atomic_transactions = true;
    out.rollback = true;
    out.audit = true;
    out.watches = true;
    out.external_change_observation = true;
    out.external_change_cancellation = true;
    out.persistence_flush = true;
    return out;
}

bool InMemoryDynamicPropertyAdapter::targetAvailableUnlocked(const DynamicPropertyTarget &target) const {
    const auto it = availability_.find(target);
    return it == availability_.end() || it->second;
}

CaptureResult InMemoryDynamicPropertyAdapter::captureUnlocked(
    const Store &store,
    const CollectionRef &ref) const {
    if (!targetAvailableUnlocked(ref.target)) {
        return {DynamicPropertyStatus::TargetUnavailable, "target is unavailable", std::nullopt};
    }
    const auto it = store.find(ref);
    if (it == store.end()) {
        return {DynamicPropertyStatus::Captured, "collection does not exist",
                makeSnapshot(ref, {}, false, true, true, true)};
    }
    return {DynamicPropertyStatus::Captured, "captured", makeSnapshot(ref, it->second)};
}

CaptureResult InMemoryDynamicPropertyAdapter::capture(const CollectionRef &ref) {
    std::lock_guard lock(mutex_);
    return captureUnlocked(store_, ref);
}

ListCollectionsResult InMemoryDynamicPropertyAdapter::listCollections(
    const DynamicPropertyTarget &target) {
    std::lock_guard lock(mutex_);
    if (!targetAvailableUnlocked(target)) {
        return {DynamicPropertyStatus::TargetUnavailable, "target is unavailable", {}};
    }
    std::vector<std::string> out;
    for (const auto &[ref, _] : store_) if (ref.target == target) out.push_back(ref.collection);
    return {DynamicPropertyStatus::Captured, "captured", std::move(out)};
}

OperationResult InMemoryDynamicPropertyAdapter::applyUnlocked(
    Store &store,
    const DynamicPropertyOperation &operation,
    bool force) const {
    if (const auto *transfer = std::get_if<TransferPropertyOperation>(&operation);
        transfer && transfer->source == transfer->destination &&
        transfer->expected_source_revision && transfer->expected_destination_revision &&
        transfer->expected_source_revision != transfer->expected_destination_revision) {
        return failure(
            DynamicPropertyStatus::InvalidValue,
            "same-collection transfer has conflicting revision expectations");
    }

    const auto refs = operationCollections(operation);
    std::vector<CollectionSnapshot> before;
    before.reserve(refs.size());
    std::set<CollectionRef> seen;
    for (const auto &ref : refs) {
        if (!seen.insert(ref).second) continue;
        auto captured = captureUnlocked(store, ref);
        if (!captured.ok()) return failure(captured.status, captured.message, std::move(before));
        before.push_back(*captured.snapshot);
        const auto expected = expectedRevision(operation, ref);
        if (!force && expected && *expected != captured.snapshot->revision) {
            return failure(DynamicPropertyStatus::Conflict, "collection revision changed", std::move(before));
        }
    }

    auto mergeInto = [](DynamicPropertyMap &destination, const DynamicPropertyMap &source) {
        for (const auto &[key, value] : source) destination.insert_or_assign(key, value);
    };

    auto result = std::visit([&](const auto &entry) -> OperationResult {
        using T = std::decay_t<decltype(entry)>;
        if constexpr (std::is_same_v<T, SetPropertyOperation>) {
            store[entry.ref].insert_or_assign(entry.key, entry.value);
        } else if constexpr (std::is_same_v<T, SetManyOperation>) {
            auto &destination = store[entry.ref];
            mergeInto(destination, entry.values);
        } else if constexpr (std::is_same_v<T, RemovePropertyOperation>) {
            const auto it = store.find(entry.ref);
            if (it == store.end() || !it->second.contains(entry.key)) {
                if (entry.require_existing)
                    return failure(DynamicPropertyStatus::NotFound, "property does not exist", before);
            } else {
                it->second.erase(entry.key);
            }
        } else if constexpr (std::is_same_v<T, RemoveManyOperation>) {
            auto it = store.find(entry.ref);
            if (entry.require_all_existing) {
                for (const auto &key : entry.keys) {
                    if (it == store.end() || !it->second.contains(key))
                        return failure(DynamicPropertyStatus::NotFound, "one or more properties do not exist", before);
                }
            }
            if (it != store.end()) for (const auto &key : entry.keys) it->second.erase(key);
        } else if constexpr (std::is_same_v<T, ClearCollectionOperation>) {
            if (entry.remove_collection) store.erase(entry.ref);
            else store[entry.ref].clear();
        } else if constexpr (std::is_same_v<T, RenameCollectionOperation>) {
            const CollectionRef source{entry.target, entry.from};
            const CollectionRef destination{entry.target, entry.to};
            const auto source_it = store.find(source);
            if (source_it == store.end())
                return failure(DynamicPropertyStatus::NotFound, "source collection does not exist", before);
            auto source_values = source_it->second;
            const auto destination_it = store.find(destination);
            if (entry.destination_policy == ImportPolicy::FailIfDestinationExists && destination_it != store.end())
                return failure(DynamicPropertyStatus::Conflict, "destination collection already exists", before);
            if (entry.destination_policy == ImportPolicy::Merge && destination_it != store.end()) {
                auto merged = destination_it->second;
                mergeInto(merged, source_values);
                store[destination] = std::move(merged);
            } else {
                store[destination] = std::move(source_values);
            }
            store.erase(source);
        } else if constexpr (std::is_same_v<T, TransferPropertyOperation>) {
            const auto source_it = store.find(entry.source);
            if (source_it == store.end() || !source_it->second.contains(entry.source_key))
                return failure(DynamicPropertyStatus::NotFound, "source property does not exist", before);
            auto &destination = store[entry.destination];
            if (!entry.overwrite && destination.contains(entry.destination_key))
                return failure(DynamicPropertyStatus::Conflict, "destination property already exists", before);
            const auto value = source_it->second.at(entry.source_key);
            destination.insert_or_assign(entry.destination_key, value);
            if (entry.remove_source) {
                auto mutable_source = store.find(entry.source);
                if (mutable_source != store.end()) mutable_source->second.erase(entry.source_key);
            }
        } else if constexpr (std::is_same_v<T, TransferCollectionOperation>) {
            const auto source_it = store.find(entry.source);
            if (source_it == store.end())
                return failure(DynamicPropertyStatus::NotFound, "source collection does not exist", before);
            const auto destination_it = store.find(entry.destination);
            if (entry.destination_policy == ImportPolicy::FailIfDestinationExists && destination_it != store.end())
                return failure(DynamicPropertyStatus::Conflict, "destination collection already exists", before);
            if (entry.destination_policy == ImportPolicy::Merge && destination_it != store.end()) {
                auto merged = destination_it->second;
                mergeInto(merged, source_it->second);
                store[entry.destination] = std::move(merged);
            } else {
                store[entry.destination] = source_it->second;
            }
            if (entry.remove_source && entry.source != entry.destination) store.erase(entry.source);
        } else if constexpr (std::is_same_v<T, ImportCollectionOperation>) {
            const auto destination_it = store.find(entry.destination);
            if (entry.policy == ImportPolicy::FailIfDestinationExists && destination_it != store.end())
                return failure(DynamicPropertyStatus::Conflict, "destination collection already exists", before);
            if (entry.policy == ImportPolicy::Merge && destination_it != store.end()) {
                auto merged = destination_it->second;
                mergeInto(merged, entry.properties);
                store[entry.destination] = std::move(merged);
            } else {
                store[entry.destination] = entry.properties;
            }
        }
        OperationResult success;
        success.status = DynamicPropertyStatus::Applied;
        success.message = "applied";
        return success;
    }, operation);

    if (!result.ok()) return result;
    result.before = std::move(before);
    seen.clear();
    for (const auto &ref : refs) {
        if (!seen.insert(ref).second) continue;
        auto captured = captureUnlocked(store, ref);
        if (captured.snapshot) {
            result.after.push_back(*captured.snapshot);
            result.resulting_revision = captured.snapshot->revision;
        }
    }
    return result;
}

OperationResult InMemoryDynamicPropertyAdapter::apply(
    const DynamicPropertyOperation &operation,
    bool force) {
    std::lock_guard lock(mutex_);
    return applyUnlocked(store_, operation, force);
}

TransactionResult InMemoryDynamicPropertyAdapter::transact(
    const DynamicPropertyTransaction &transaction) {
    std::lock_guard lock(mutex_);
    TransactionResult out;
    out.transaction_id = nextTransactionId();
    Store candidate = store_;
    out.operation_results.reserve(transaction.operations.size());
    for (const auto &operation : transaction.operations) {
        auto result = applyUnlocked(candidate, operation, transaction.force);
        out.operation_results.push_back(result);
        if (!result.ok()) {
            out.status = DynamicPropertyStatus::TransactionFailed;
            out.message = result.message;
            out.rolled_back = transaction.rollback_on_failure;
            return out;
        }
    }
    store_.swap(candidate);
    out.status = DynamicPropertyStatus::Applied;
    out.message = "transaction applied atomically";
    return out;
}

OperationResult InMemoryDynamicPropertyAdapter::flush(const DynamicPropertyTarget &target) {
    std::lock_guard lock(mutex_);
    if (!targetAvailableUnlocked(target))
        return failure(DynamicPropertyStatus::TargetUnavailable, "target is unavailable");
    return {DynamicPropertyStatus::Applied, "persistence flush completed", {}, {}, 0};
}

void InMemoryDynamicPropertyAdapter::setTargetAvailable(
    DynamicPropertyTarget target,
    bool available) {
    std::lock_guard lock(mutex_);
    availability_.insert_or_assign(std::move(target), available);
}

std::size_t InMemoryDynamicPropertyAdapter::collectionCount() const {
    std::lock_guard lock(mutex_);
    return store_.size();
}

std::shared_ptr<InMemoryDynamicPropertyAdapter> makeInMemoryDynamicPropertyAdapter() {
    return std::make_shared<InMemoryDynamicPropertyAdapter>();
}

} // namespace endstone_dynamic_properties
