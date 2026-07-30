#include "endstone_dynamic_properties/service.h"

#include <algorithm>
#include <atomic>
#include <map>
#include <set>
#include <type_traits>
#include <unordered_map>

namespace endstone_dynamic_properties {
namespace {
std::atomic<std::uint64_t> service_transaction_counter{1};

OperationResult makeFailure(DynamicPropertyStatus status, std::string message) {
    OperationResult out;
    out.status = status;
    out.message = std::move(message);
    return out;
}

bool targetCapability(const DynamicPropertyCapabilities &capabilities, TargetKind kind) {
    switch (kind) {
    case TargetKind::World: return capabilities.world;
    case TargetKind::OnlinePlayer: return capabilities.online_players;
    case TargetKind::OfflinePlayer: return capabilities.offline_players;
    case TargetKind::LoadedEntity: return capabilities.loaded_entities;
    case TargetKind::StoredEntity: return capabilities.stored_entities;
    case TargetKind::PlayerInventorySlot: return capabilities.player_inventory_items;
    case TargetKind::PlayerArmorSlot: return capabilities.player_armor_items;
    case TargetKind::PlayerOffhandSlot: return capabilities.player_offhand_items;
    case TargetKind::PlayerEnderChestSlot: return capabilities.player_ender_chest_items;
    case TargetKind::BlockContainerSlot: return capabilities.block_container_items;
    case TargetKind::DroppedItem: return capabilities.dropped_items;
    case TargetKind::BlockEntity: return capabilities.block_entities && capabilities.block_dynamic_properties;
    }
    return false;
}

std::shared_ptr<std::recursive_mutex> mutationMutexFor(
    const IDynamicPropertyAdapter *adapter) {
    static std::mutex registry_mutex;
    static std::unordered_map<
        const IDynamicPropertyAdapter *, std::weak_ptr<std::recursive_mutex>> registry;
    std::lock_guard lock(registry_mutex);
    for (auto it = registry.begin(); it != registry.end();) {
        if (it->second.expired()) it = registry.erase(it);
        else ++it;
    }
    if (const auto it = registry.find(adapter); it != registry.end()) {
        if (auto existing = it->second.lock()) return existing;
    }
    auto created = std::make_shared<std::recursive_mutex>();
    registry.insert_or_assign(adapter, created);
    return created;
}

} // namespace

DynamicPropertyService::DynamicPropertyService(
    std::shared_ptr<IDynamicPropertyAdapter> adapter,
    ValidationLimits limits,
    std::shared_ptr<DynamicPropertyEventBus> event_bus,
    std::shared_ptr<IDynamicPropertyAuditSink> audit_sink,
    DynamicPropertyAccessPolicy access_policy)
    : adapter_(std::move(adapter)),
      limits_(limits),
      event_bus_(event_bus ? std::move(event_bus) : std::make_shared<DynamicPropertyEventBus>()),
      audit_sink_(audit_sink ? std::move(audit_sink) : std::make_shared<VectorAuditSink>()),
      access_policy_(std::move(access_policy)) {
    if (!adapter_) throw std::invalid_argument("dynamic-property adapter must not be null");
    mutation_mutex_ = mutationMutexFor(adapter_.get());
}

std::optional<OperationResult> DynamicPropertyService::validateCapability(
    const DynamicPropertyTarget &target) const {
    if (const auto error = validateTarget(target))
        return makeFailure(DynamicPropertyStatus::InvalidTarget, *error);
    if (!targetCapability(adapter_->capabilities(), target.kind))
        return makeFailure(DynamicPropertyStatus::Unsupported,
                           "adapter does not support target kind " + std::string(targetKindName(target.kind)));
    return std::nullopt;
}

CaptureResult DynamicPropertyService::capture(
    const CollectionRef &ref,
    const AccessContext &context) const {
    if (const auto error = validateCapability(ref.target))
        return {error->status, error->message, std::nullopt};
    if (const auto validation = validateCollectionName(ref.collection, limits_); !validation.valid)
        return {DynamicPropertyStatus::InvalidCollection, validation.message, std::nullopt};
    if (!access_policy_.canAccess(context, ref))
        return {DynamicPropertyStatus::PermissionDenied, "collection access denied", std::nullopt};
    if (!adapter_->capabilities().read)
        return {DynamicPropertyStatus::Unsupported, "adapter does not support reads", std::nullopt};
    return adapter_->capture(ref);
}

PropertyReadResult DynamicPropertyService::get(
    const CollectionRef &ref,
    std::string_view key,
    const AccessContext &context) const {
    if (const auto validation = validateKey(key, limits_); !validation.valid)
        return {DynamicPropertyStatus::InvalidKey, validation.message, std::nullopt, 0};
    auto captured = capture(ref, context);
    if (!captured.ok() || !captured.snapshot)
        return {captured.status, captured.message, std::nullopt, 0};
    const auto it = captured.snapshot->properties.find(std::string(key));
    if (it == captured.snapshot->properties.end())
        return {DynamicPropertyStatus::NotFound, "property does not exist", std::nullopt,
                captured.snapshot->revision};
    return {DynamicPropertyStatus::Captured, "captured", it->second, captured.snapshot->revision};
}

ListCollectionsResult DynamicPropertyService::listCollections(
    const DynamicPropertyTarget &target,
    const AccessContext &context) const {
    if (const auto error = validateCapability(target))
        return {error->status, error->message, {}};
    if (!adapter_->capabilities().list_collections)
        return {DynamicPropertyStatus::Unsupported, "adapter does not support collection listing", {}};
    auto result = adapter_->listCollections(target);
    if (!result.ok() || access_policy_.canListRawCollections(context)) return result;
    const auto prefix = access_policy_.pluginPrefix(context.plugin_id);
    if (prefix.empty()) return {DynamicPropertyStatus::PermissionDenied, "plugin identity is required", {}};
    std::erase_if(result.collections, [&](const std::string &collection) {
        return !collection.starts_with(prefix);
    });
    return result;
}

std::optional<OperationResult> DynamicPropertyService::validateOperation(
    const DynamicPropertyOperation &operation,
    const AccessContext &context) const {
    for (const auto &ref : operationCollections(operation)) {
        if (const auto error = validateCapability(ref.target)) return error;
        if (const auto validation = validateCollectionName(ref.collection, limits_); !validation.valid)
            return makeFailure(DynamicPropertyStatus::InvalidCollection, validation.message);
        if (!access_policy_.canAccess(context, ref))
            return makeFailure(DynamicPropertyStatus::PermissionDenied,
                               "collection access denied: " + ref.collection);
    }

    return std::visit([&](const auto &entry) -> std::optional<OperationResult> {
        using T = std::decay_t<decltype(entry)>;
        auto validateEntry = [&](std::string_view key, const DynamicPropertyValue *value = nullptr)
            -> std::optional<OperationResult> {
            if (const auto key_result = validateKey(key, limits_); !key_result.valid)
                return makeFailure(DynamicPropertyStatus::InvalidKey, key_result.message);
            if (value) {
                if (const auto value_result = validateValue(*value, limits_); !value_result.valid)
                    return makeFailure(DynamicPropertyStatus::InvalidValue, value_result.message);
            }
            return std::nullopt;
        };

        if constexpr (std::is_same_v<T, SetPropertyOperation>) {
            if (!adapter_->capabilities().write)
                return makeFailure(DynamicPropertyStatus::Unsupported, "adapter does not support writes");
            return validateEntry(entry.key, &entry.value);
        } else if constexpr (std::is_same_v<T, SetManyOperation>) {
            if (!adapter_->capabilities().bulk_set)
                return makeFailure(DynamicPropertyStatus::Unsupported, "adapter does not support bulk writes");
            if (entry.values.size() > limits_.max_properties_per_collection)
                return makeFailure(DynamicPropertyStatus::InvalidValue, "bulk write exceeds property-count limit");
            for (const auto &[key, value] : entry.values)
                if (auto error = validateEntry(key, &value)) return error;
            return std::nullopt;
        } else if constexpr (std::is_same_v<T, RemovePropertyOperation>) {
            if (!adapter_->capabilities().remove)
                return makeFailure(DynamicPropertyStatus::Unsupported, "adapter does not support removals");
            return validateEntry(entry.key);
        } else if constexpr (std::is_same_v<T, RemoveManyOperation>) {
            if (!adapter_->capabilities().remove)
                return makeFailure(DynamicPropertyStatus::Unsupported, "adapter does not support removals");
            if (entry.keys.size() > limits_.max_properties_per_collection)
                return makeFailure(DynamicPropertyStatus::InvalidValue,
                                   "bulk removal exceeds property-count limit");
            for (const auto &key : entry.keys) if (auto error = validateEntry(key)) return error;
            return std::nullopt;
        } else if constexpr (std::is_same_v<T, ClearCollectionOperation>) {
            if (!adapter_->capabilities().clear)
                return makeFailure(DynamicPropertyStatus::Unsupported, "adapter does not support collection clearing");
            return std::nullopt;
        } else if constexpr (std::is_same_v<T, RenameCollectionOperation>) {
            if (!adapter_->capabilities().collection_rename)
                return makeFailure(DynamicPropertyStatus::Unsupported, "adapter does not support collection renaming");
            if (entry.from == entry.to)
                return makeFailure(DynamicPropertyStatus::InvalidCollection,
                                   "source and destination collections must differ");
            return std::nullopt;
        } else if constexpr (std::is_same_v<T, TransferPropertyOperation>) {
            if (!adapter_->capabilities().property_copy_move)
                return makeFailure(DynamicPropertyStatus::Unsupported, "adapter does not support property transfer");
            if (auto error = validateEntry(entry.source_key)) return error;
            if (auto error = validateEntry(entry.destination_key)) return error;
            if (entry.source == entry.destination &&
                entry.expected_source_revision && entry.expected_destination_revision &&
                entry.expected_source_revision != entry.expected_destination_revision)
                return makeFailure(
                    DynamicPropertyStatus::InvalidValue,
                    "same-collection transfer has conflicting revision expectations");
            if (entry.remove_source && entry.source == entry.destination &&
                entry.source_key == entry.destination_key)
                return makeFailure(DynamicPropertyStatus::InvalidKey,
                                   "source and destination properties must differ for a move");
            return std::nullopt;
        } else if constexpr (std::is_same_v<T, TransferCollectionOperation>) {
            if (!adapter_->capabilities().collection_copy_move)
                return makeFailure(DynamicPropertyStatus::Unsupported, "adapter does not support collection transfer");
            if (entry.remove_source && entry.source == entry.destination)
                return makeFailure(DynamicPropertyStatus::InvalidCollection,
                                   "source and destination collections must differ for a move");
            return std::nullopt;
        } else {
            if (!adapter_->capabilities().export_import)
                return makeFailure(DynamicPropertyStatus::Unsupported, "adapter does not support import");
            if (entry.properties.size() > limits_.max_properties_per_collection)
                return makeFailure(DynamicPropertyStatus::InvalidValue, "import exceeds property-count limit");
            for (const auto &[key, value] : entry.properties)
                if (auto error = validateEntry(key, &value)) return error;
            return std::nullopt;
        }
    }, operation);
}

std::optional<OperationResult> DynamicPropertyService::validatePropertyLimits(
    const std::vector<DynamicPropertyOperation> &operations) const {
    std::set<CollectionRef> refs;
    for (const auto &operation : operations) {
        const auto operation_refs = operationCollections(operation);
        refs.insert(operation_refs.begin(), operation_refs.end());
    }

    std::map<CollectionRef, std::set<std::string>> keys;
    std::map<CollectionRef, bool> exists;
    for (const auto &ref : refs) {
        const auto captured = adapter_->capture(ref);
        if (!captured.ok() || !captured.snapshot) {
            const auto status = captured.ok()
                ? DynamicPropertyStatus::AdapterError : captured.status;
            return makeFailure(
                status,
                captured.message.empty()
                    ? "adapter capture failed during commit validation"
                    : captured.message);
        }
        exists[ref] = captured.snapshot->exists;
        for (const auto &[key, value] : captured.snapshot->properties) {
            static_cast<void>(value);
            keys[ref].insert(key);
        }
    }

    for (const auto &operation : operations) {
        const bool can_apply = std::visit([&](const auto &entry) {
            using T = std::decay_t<decltype(entry)>;
            if constexpr (std::is_same_v<T, SetPropertyOperation>) {
                keys[entry.ref].insert(entry.key);
                exists[entry.ref] = true;
                return true;
            } else if constexpr (std::is_same_v<T, SetManyOperation>) {
                for (const auto &[key, value] : entry.values) {
                    static_cast<void>(value);
                    keys[entry.ref].insert(key);
                }
                exists[entry.ref] = true;
                return true;
            } else if constexpr (std::is_same_v<T, RemovePropertyOperation>) {
                if (entry.require_existing && !keys[entry.ref].contains(entry.key)) return false;
                keys[entry.ref].erase(entry.key);
                return true;
            } else if constexpr (std::is_same_v<T, RemoveManyOperation>) {
                if (entry.require_all_existing && std::any_of(
                        entry.keys.begin(), entry.keys.end(),
                        [&](const std::string &key) { return !keys[entry.ref].contains(key); }))
                    return false;
                for (const auto &key : entry.keys) keys[entry.ref].erase(key);
                return true;
            } else if constexpr (std::is_same_v<T, ClearCollectionOperation>) {
                keys[entry.ref].clear();
                exists[entry.ref] = !entry.remove_collection;
                return true;
            } else if constexpr (std::is_same_v<T, RenameCollectionOperation>) {
                const CollectionRef source{entry.target, entry.from};
                const CollectionRef destination{entry.target, entry.to};
                if (!exists[source]) return false;
                if (entry.destination_policy == ImportPolicy::FailIfDestinationExists &&
                    exists[destination]) return false;
                auto destination_keys = entry.destination_policy == ImportPolicy::Merge &&
                                                exists[destination]
                    ? keys[destination]
                    : std::set<std::string>{};
                destination_keys.insert(keys[source].begin(), keys[source].end());
                keys[destination] = std::move(destination_keys);
                exists[destination] = true;
                keys[source].clear();
                exists[source] = false;
                return true;
            } else if constexpr (std::is_same_v<T, TransferPropertyOperation>) {
                if (!keys[entry.source].contains(entry.source_key)) return false;
                if (keys[entry.destination].contains(entry.destination_key) && !entry.overwrite)
                    return false;
                keys[entry.destination].insert(entry.destination_key);
                exists[entry.destination] = true;
                if (entry.remove_source) keys[entry.source].erase(entry.source_key);
                return true;
            } else if constexpr (std::is_same_v<T, TransferCollectionOperation>) {
                if (!exists[entry.source]) return false;
                if (entry.destination_policy == ImportPolicy::FailIfDestinationExists &&
                    exists[entry.destination]) return false;
                auto destination_keys = entry.destination_policy == ImportPolicy::Merge &&
                                                exists[entry.destination]
                    ? keys[entry.destination]
                    : std::set<std::string>{};
                destination_keys.insert(keys[entry.source].begin(), keys[entry.source].end());
                keys[entry.destination] = std::move(destination_keys);
                exists[entry.destination] = true;
                if (entry.remove_source) {
                    keys[entry.source].clear();
                    exists[entry.source] = false;
                }
                return true;
            } else {
                if (entry.policy == ImportPolicy::FailIfDestinationExists &&
                    exists[entry.destination]) return false;
                auto destination_keys = entry.policy == ImportPolicy::Merge &&
                                                exists[entry.destination]
                    ? keys[entry.destination]
                    : std::set<std::string>{};
                for (const auto &[key, value] : entry.properties) {
                    static_cast<void>(value);
                    destination_keys.insert(key);
                }
                keys[entry.destination] = std::move(destination_keys);
                exists[entry.destination] = true;
                return true;
            }
        }, operation);
        if (!can_apply) return std::nullopt;
        if (std::any_of(keys.begin(), keys.end(), [&](const auto &entry) {
                return entry.second.size() > limits_.max_properties_per_collection;
            }))
            return makeFailure(DynamicPropertyStatus::InvalidValue,
                               "resulting collection exceeds property-count limit");
    }
    return std::nullopt;
}

bool DynamicPropertyService::publishBefore(
    DynamicPropertyEventKind kind,
    const DynamicPropertyOperation &operation,
    const AccessContext &context,
    std::string transaction_id,
    bool cancellable,
    std::string &reason) const {
    DynamicPropertyEvent event;
    event.kind = kind;
    event.transaction_id = std::move(transaction_id);
    event.operation_name = std::string(operationName(operation));
    event.actor = context;
    event.collections = operationCollections(operation);
    event.key = operationPrimaryKey(operation);
    event.cancellable = cancellable;
    for (const auto &ref : event.collections) {
        const auto captured = adapter_->capture(ref);
        if (captured.snapshot) event.before.push_back(*captured.snapshot);
    }
    const auto listener_failures = event_bus_->publish(event);
    if (!listener_failures.empty() && cancellable) {
        event.cancelled = true;
        if (event.cancellation_reason.empty())
            event.cancellation_reason = "before-event listener failed";
    }
    reason = event.cancellation_reason;
    return event.cancelled && cancellable;
}

void DynamicPropertyService::publishAfter(
    DynamicPropertyEventKind kind,
    const DynamicPropertyOperation &operation,
    const AccessContext &context,
    const OperationResult &result,
    std::string transaction_id) const {
    DynamicPropertyEvent event;
    event.kind = kind;
    event.transaction_id = std::move(transaction_id);
    event.operation_name = std::string(operationName(operation));
    event.actor = context;
    event.collections = operationCollections(operation);
    event.key = operationPrimaryKey(operation);
    event.before = result.before;
    event.after = result.after;
    static_cast<void>(event_bus_->publish(event));
    if (result.ok() && std::holds_alternative<TransferCollectionOperation>(operation)) {
        const auto &transfer = std::get<TransferCollectionOperation>(operation);
        if (transfer.remove_source) {
            auto migration_event = event;
            migration_event.kind = DynamicPropertyEventKind::CollectionMigrated;
            static_cast<void>(event_bus_->publish(migration_event));
        }
    }
}

void DynamicPropertyService::audit(
    const DynamicPropertyOperation &operation,
    const AccessContext &context,
    const OperationResult &result,
    std::string transaction_id,
    bool external,
    bool rolled_back) const noexcept {
    try {
        DynamicPropertyAuditRecord record;
        record.transaction_id = std::move(transaction_id);
        record.operation_name = std::string(operationName(operation));
        record.actor = context;
        record.status = result.status;
        record.message = result.message;
        record.before = result.before;
        record.after = result.after;
        record.external = external;
        record.rolled_back = rolled_back;
        audit_sink_->record(std::move(record));
    } catch (...) {
        reportAuditFailure(std::current_exception());
    }
}

void DynamicPropertyService::setAuditFailureHandler(AuditFailureHandler handler) {
    std::lock_guard lock(audit_failure_mutex_);
    audit_failure_handler_ = std::move(handler);
}

void DynamicPropertyService::reportAuditFailure(std::exception_ptr failure) const noexcept {
    AuditFailureHandler handler;
    try {
        {
            std::lock_guard lock(audit_failure_mutex_);
            handler = audit_failure_handler_;
        }
        if (handler) handler(std::move(failure));
    } catch (...) {
        // Reporting must never replace a committed mutation result.
    }
}

OperationResult DynamicPropertyService::apply(
    const DynamicPropertyOperation &operation,
    const AccessContext &context,
    bool force) {
    const DynamicPropertyOperation operation_copy = operation;
    const AccessContext context_copy = context;
    if (force && !context_copy.raw_admin)
        return makeFailure(DynamicPropertyStatus::PermissionDenied,
                           "force requires raw administrative access");
    if (const auto error = validateOperation(operation_copy, context_copy)) return *error;
    if (const auto error = validatePropertyLimits({operation_copy})) return *error;
    const auto transaction_id = makeTransactionId();
    std::string reason;
    if (publishBefore(DynamicPropertyEventKind::BeforeMutation, operation_copy, context_copy,
                      transaction_id, true, reason)) {
        auto result = makeFailure(DynamicPropertyStatus::Cancelled,
                                  reason.empty() ? "mutation cancelled" : reason);
        audit(operation_copy, context_copy, result, transaction_id);
        return result;
    }
    OperationResult result;
    bool commit_attempted = false;
    {
        // Callbacks run outside this lock. Commit-time revalidation serializes
        // concurrent and synchronously reentrant writes through this service.
        std::lock_guard lock(*mutation_mutex_);
        if (const auto error = validateOperation(operation_copy, context_copy)) {
            result = *error;
        } else if (const auto limit_error = validatePropertyLimits({operation_copy})) {
            result = *limit_error;
        } else {
            result = adapter_->apply(operation_copy, force);
            commit_attempted = true;
        }
    }
    if (commit_attempted)
        publishAfter(DynamicPropertyEventKind::AfterMutation, operation_copy, context_copy,
                     result, transaction_id);
    audit(operation_copy, context_copy, result, transaction_id);
    return result;
}

TransactionResult DynamicPropertyService::transact(
    const DynamicPropertyTransaction &transaction,
    const AccessContext &context) {
    const DynamicPropertyTransaction transaction_copy = transaction;
    const AccessContext context_copy = context;
    TransactionResult out;
    out.transaction_id = makeTransactionId();
    if (transaction_copy.operations.empty()) {
        out.status = DynamicPropertyStatus::Applied;
        out.message = "empty transaction";
        return out;
    }
    if (transaction_copy.operations.size() > limits_.max_transaction_operations) {
        out.status = DynamicPropertyStatus::InvalidValue;
        out.message = "transaction exceeds operation limit";
        return out;
    }
    if (transaction_copy.require_atomic && !adapter_->capabilities().atomic_transactions) {
        out.status = DynamicPropertyStatus::Unsupported;
        out.message = "adapter does not provide atomic transactions";
        return out;
    }
    if (transaction_copy.force && !context_copy.raw_admin) {
        out.status = DynamicPropertyStatus::PermissionDenied;
        out.message = "force requires raw administrative access";
        return out;
    }
    auto transaction_context = context_copy;
    if (!transaction_copy.audit_reason.empty())
        transaction_context.reason = transaction_copy.audit_reason;
    for (const auto &operation : transaction_copy.operations) {
        if (const auto error = validateOperation(operation, transaction_context)) {
            out.status = error->status;
            out.message = error->message;
            return out;
        }
    }
    if (const auto error = validatePropertyLimits(transaction_copy.operations)) {
        out.status = error->status;
        out.message = error->message;
        return out;
    }

    DynamicPropertyEvent before_event;
    before_event.kind = DynamicPropertyEventKind::BeforeTransaction;
    before_event.transaction_id = out.transaction_id;
    before_event.operation_name = "transaction";
    before_event.actor = transaction_context;
    before_event.cancellable = true;
    std::set<CollectionRef> refs;
    for (const auto &operation : transaction_copy.operations) {
        for (const auto &ref : operationCollections(operation)) refs.insert(ref);
    }
    before_event.collections.assign(refs.begin(), refs.end());
    for (const auto &ref : before_event.collections) {
        auto captured = adapter_->capture(ref);
        if (captured.snapshot) before_event.before.push_back(*captured.snapshot);
    }
    const auto event_collections = before_event.collections;
    const auto listener_failures = event_bus_->publish(before_event);
    if (!listener_failures.empty()) {
        before_event.cancelled = true;
        if (before_event.cancellation_reason.empty())
            before_event.cancellation_reason = "before-transaction listener failed";
    }
    if (before_event.cancelled) {
        out.status = DynamicPropertyStatus::Cancelled;
        out.message = before_event.cancellation_reason.empty()
            ? "transaction cancelled" : before_event.cancellation_reason;
        const auto cancelled = makeFailure(out.status, out.message);
        out.operation_results.assign(transaction_copy.operations.size(), cancelled);
        for (const auto &operation : transaction_copy.operations)
            audit(operation, transaction_context, cancelled, out.transaction_id);
        return out;
    }

    const auto transaction_id = out.transaction_id;
    DynamicPropertyEvent after_event;
    after_event.kind = DynamicPropertyEventKind::AfterTransaction;
    after_event.transaction_id = transaction_id;
    after_event.operation_name = "transaction";
    after_event.actor = transaction_context;
    after_event.collections = event_collections;
    bool commit_attempted = false;
    {
        std::lock_guard lock(*mutation_mutex_);
        for (const auto &ref : after_event.collections) {
            auto captured = adapter_->capture(ref);
            if (captured.snapshot) after_event.before.push_back(*captured.snapshot);
        }

        std::optional<OperationResult> commit_error;
        for (const auto &operation : transaction_copy.operations) {
            if (const auto error = validateOperation(operation, transaction_context)) {
                commit_error = *error;
                break;
            }
        }
        if (!commit_error)
            commit_error = validatePropertyLimits(transaction_copy.operations);

        if (commit_error) {
            out.status = commit_error->status;
            out.message = commit_error->message;
            out.operation_results.assign(
                transaction_copy.operations.size(), *commit_error);
        } else {
            out = adapter_->transact(transaction_copy);
            out.transaction_id = transaction_id;
            commit_attempted = true;
        }
        for (const auto &ref : after_event.collections) {
            auto captured = adapter_->capture(ref);
            if (captured.snapshot) after_event.after.push_back(*captured.snapshot);
        }
    }
    out.transaction_id = transaction_id;
    if (!commit_attempted) {
        for (std::size_t i = 0; i < transaction_copy.operations.size(); ++i)
            audit(transaction_copy.operations[i], transaction_context,
                  out.operation_results[i], out.transaction_id);
        return out;
    }
    static_cast<void>(event_bus_->publish(after_event));

    const auto count = std::min(transaction_copy.operations.size(), out.operation_results.size());
    for (std::size_t i = 0; i < count; ++i)
        audit(transaction_copy.operations[i], transaction_context, out.operation_results[i],
              out.transaction_id,
              false, out.rolled_back);
    return out;
}

OperationResult DynamicPropertyService::flush(
    const DynamicPropertyTarget &target,
    const AccessContext &) {
    std::lock_guard lock(*mutation_mutex_);
    if (const auto error = validateCapability(target)) return *error;
    if (!adapter_->capabilities().persistence_flush)
        return makeFailure(DynamicPropertyStatus::Unsupported, "adapter does not support persistence flush");
    return adapter_->flush(target);
}

OperationResult DynamicPropertyService::set(
    CollectionRef ref,
    std::string key,
    DynamicPropertyValue value,
    const AccessContext &context,
    std::optional<std::uint64_t> expected_revision) {
    return apply(SetPropertyOperation{std::move(ref), std::move(key), std::move(value), expected_revision}, context);
}

OperationResult DynamicPropertyService::setMany(
    CollectionRef ref,
    DynamicPropertyMap values,
    const AccessContext &context,
    std::optional<std::uint64_t> expected_revision) {
    return apply(SetManyOperation{std::move(ref), std::move(values), expected_revision}, context);
}

OperationResult DynamicPropertyService::remove(
    CollectionRef ref,
    std::string key,
    const AccessContext &context,
    std::optional<std::uint64_t> expected_revision,
    bool require_existing) {
    return apply(RemovePropertyOperation{std::move(ref), std::move(key), expected_revision, require_existing}, context);
}

OperationResult DynamicPropertyService::clear(
    CollectionRef ref,
    const AccessContext &context,
    std::optional<std::uint64_t> expected_revision,
    bool remove_collection) {
    return apply(ClearCollectionOperation{std::move(ref), expected_revision, remove_collection}, context);
}

OperationResult DynamicPropertyService::migrateCollection(
    CollectionRef source,
    CollectionRef destination,
    const AccessContext &context,
    ImportPolicy policy,
    bool remove_source,
    std::optional<std::uint64_t> expected_source_revision,
    std::optional<std::uint64_t> expected_destination_revision) {
    return apply(TransferCollectionOperation{
        std::move(source), std::move(destination), expected_source_revision,
        expected_destination_revision, policy, remove_source}, context);
}

ExportResult DynamicPropertyService::exportCollection(
    const CollectionRef &ref,
    const AccessContext &context) const {
    if (!adapter_->capabilities().export_import)
        return {DynamicPropertyStatus::Unsupported, "adapter does not support export", {}, 0};
    auto captured = capture(ref, context);
    if (!captured.ok() || !captured.snapshot)
        return {captured.status, captured.message, {}, 0};
    return {DynamicPropertyStatus::Captured, "exported",
            encodeCollectionJson(ref, captured.snapshot->properties, captured.snapshot->revision),
            captured.snapshot->revision};
}

OperationResult DynamicPropertyService::importCollection(
    CollectionRef destination,
    std::string_view document,
    const AccessContext &context,
    ImportPolicy policy,
    std::optional<std::uint64_t> expected_revision) {
    if (document.size() > limits_.max_import_bytes)
        return makeFailure(DynamicPropertyStatus::InvalidValue, "import document exceeds byte limit");
    std::string error;
    auto properties = decodeCollectionJson(document, &error);
    if (!properties)
        return makeFailure(DynamicPropertyStatus::InvalidValue, "invalid import document: " + error);
    return apply(ImportCollectionOperation{
        std::move(destination), std::move(*properties), expected_revision, policy}, context);
}

ExternalMutationGateResult DynamicPropertyService::beforeExternalMutation(
    const DynamicPropertyOperation &operation,
    AccessContext context,
    bool cancellable) {
    const DynamicPropertyOperation operation_copy = operation;
    if (context.origin == MutationOrigin::Api) context.origin = MutationOrigin::NativeHook;
    ExternalMutationGateResult out;
    out.transaction_id = makeTransactionId();
    if (!adapter_->capabilities().external_change_observation) {
        out.decision = ExternalMutationDecision::ObserveOnly;
        out.status = DynamicPropertyStatus::Unsupported;
        out.message = "external change observation is unavailable";
        return out;
    }
    const bool can_cancel = cancellable &&
        adapter_->capabilities().external_change_cancellation;
    if (const auto error = validateOperation(operation_copy, context)) {
        out.decision = can_cancel ? ExternalMutationDecision::Cancel
                                  : ExternalMutationDecision::ObserveOnly;
        out.status = error->status;
        out.message = error->message;
        return out;
    }
    if (const auto error = validatePropertyLimits({operation_copy})) {
        out.decision = can_cancel ? ExternalMutationDecision::Cancel
                                  : ExternalMutationDecision::ObserveOnly;
        out.status = error->status;
        out.message = error->message;
        return out;
    }
    std::string reason;
    const bool cancelled = publishBefore(
        DynamicPropertyEventKind::BeforeExternalMutation,
        operation_copy,
        context,
        out.transaction_id,
        can_cancel,
        reason);
    std::optional<OperationResult> post_event_error;
    if (!cancelled) {
        std::lock_guard lock(*mutation_mutex_);
        post_event_error = validateOperation(operation_copy, context);
        if (!post_event_error)
            post_event_error = validatePropertyLimits({operation_copy});
    }
    if (cancelled) {
        out.decision = ExternalMutationDecision::Cancel;
        out.status = DynamicPropertyStatus::Cancelled;
        out.message = reason.empty() ? "external mutation cancelled" : reason;
    } else if (post_event_error) {
        out.decision = can_cancel ? ExternalMutationDecision::Cancel
                                  : ExternalMutationDecision::ObserveOnly;
        out.status = post_event_error->status;
        out.message = post_event_error->message;
    } else if (cancellable && !can_cancel) {
        out.decision = ExternalMutationDecision::ObserveOnly;
        out.status = DynamicPropertyStatus::Unsupported;
        out.message = "external mutation can be observed but not cancelled";
    } else {
        out.decision = ExternalMutationDecision::Allow;
        out.status = DynamicPropertyStatus::Applied;
        out.message = "external mutation allowed";
    }
    return out;
}

void DynamicPropertyService::afterExternalMutation(
    const DynamicPropertyOperation &operation,
    const OperationResult &result,
    AccessContext context,
    std::string transaction_id) {
    const DynamicPropertyOperation operation_copy = operation;
    const OperationResult result_copy = result;
    if (context.origin == MutationOrigin::Api) context.origin = MutationOrigin::NativeHook;
    if (transaction_id.empty()) transaction_id = makeTransactionId();
    publishAfter(DynamicPropertyEventKind::AfterExternalMutation,
                 operation_copy, context, result_copy, transaction_id);
    audit(operation_copy, context, result_copy, transaction_id, true, false);
}

DynamicPropertyCapabilities DynamicPropertyService::capabilities() const noexcept {
    auto out = adapter_->capabilities();
    out.audit = static_cast<bool>(audit_sink_);
    out.watches = static_cast<bool>(event_bus_);
    return out;
}

std::string DynamicPropertyService::adapterName() const {
    return std::string(adapter_->name());
}

std::string DynamicPropertyService::makeTransactionId() {
    return "dptx-" + std::to_string(service_transaction_counter.fetch_add(1));
}

} // namespace endstone_dynamic_properties
