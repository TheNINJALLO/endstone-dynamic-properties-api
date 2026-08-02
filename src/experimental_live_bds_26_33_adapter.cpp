#if defined(__linux__)

#include "endstone_dynamic_properties/bds_26_30_adapter.h"

#include "endstone_dynamic_properties/in_memory_adapter.h"
#include "endstone_dynamic_properties/service.h"

#include <bedrock/world/actor/actor_unique_id.h>
#include <bedrock/world/level/level.h>
#include <endstone/actor/actor.h>
#include <endstone/level/level.h>
#include <endstone/player.h>
#include <endstone/server.h>

#include <link.h>
#include <funchook.h>

#include <algorithm>
#include <atomic>
#include <charconv>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <stdexcept>
#include <string>
#include <string_view>
#include <type_traits>
#include <unordered_map>
#include <utility>
#include <variant>
#include <vector>

namespace endstone_dynamic_properties {
namespace {

// Exact Linux BDS 1.26.33.1 contracts recovered from the official executable.
// The adapter is unreachable unless the full executable SHA-256 and size match
// include/endstone_dynamic_properties/generated/native_manifest_data.h.
constexpr std::uintptr_t SetPropertyRva = 0x0C094EF0;
constexpr std::uintptr_t RemovePropertyRva = 0x0C0950A0;
constexpr std::uintptr_t ClearCollectionRva = 0x0C0952C0;
constexpr std::uintptr_t ManagerGetOrAddLevelPropertiesRva = 0x0C096C10;
constexpr std::uintptr_t ActorGetOrAddPropertiesRva = 0x09C71920;
constexpr std::size_t EndstoneLevelHandleWord = 2;
constexpr std::size_t ServerLevelDynamicPropertiesManagerOffset = 0x7A0;
constexpr std::size_t ActorEntityContextOffset = 0x8;

struct NativeVec3 {
    float x{};
    float y{};
    float z{};
};

using NativePropertyValue =
    std::variant<double, float, bool, std::string, NativeVec3>;

struct NativePropertyCollection {
    std::uint64_t byte_count{};
    std::unordered_map<std::string, NativePropertyValue> properties;
};

struct NativeDynamicProperties {
    std::unordered_map<std::string, NativePropertyCollection> collections;
};

// BDS and Endstone both use libc++ on Linux. These guards turn a toolchain ABI
// drift into a compile failure instead of corrupting a live server object.
static_assert(sizeof(std::unordered_map<std::string, NativePropertyCollection>) == 0x28);
static_assert(sizeof(NativeDynamicProperties) == 0x28);

using SetPropertyFunction = void (*)(
    NativeDynamicProperties *,
    const std::string &,
    const NativePropertyValue &,
    const std::string &);
using RemovePropertyFunction = bool (*)(
    NativeDynamicProperties *, const std::string &, const std::string &);
using ClearCollectionFunction = void (*)(
    NativeDynamicProperties *, const std::string &);
using ManagerGetOrAddFunction = NativeDynamicProperties *(*)(void *);
using ActorGetOrAddFunction = NativeDynamicProperties *(*)(void *);

struct NativeFunctions {
    SetPropertyFunction set{};
    RemovePropertyFunction remove{};
    ClearCollectionFunction clear{};
    ManagerGetOrAddFunction get_or_add_level{};
    ActorGetOrAddFunction get_or_add_actor{};

    [[nodiscard]] bool complete() const noexcept {
        return set && remove && clear && get_or_add_level && get_or_add_actor;
    }
};

int executableBaseCallback(dl_phdr_info *info, std::size_t, void *data) {
    if (!info || !data) return 0;
    const std::string_view name = info->dlpi_name ? info->dlpi_name : "";
    if (!name.empty() && !name.ends_with("/bedrock_server") &&
        name != "bedrock_server") {
        return 0;
    }
    *static_cast<std::uintptr_t *>(data) =
        static_cast<std::uintptr_t>(info->dlpi_addr);
    return 1;
}

std::uintptr_t executableBase() noexcept {
    std::uintptr_t base = 0;
    dl_iterate_phdr(executableBaseCallback, &base);
    return base;
}

template <typename Function>
Function atRva(std::uintptr_t base, std::uintptr_t rva) noexcept {
    return reinterpret_cast<Function>(base + rva);
}

NativeFunctions resolveFunctions() noexcept {
    const auto base = executableBase();
    if (base == 0) return {};
    return {
        atRva<SetPropertyFunction>(base, SetPropertyRva),
        atRva<RemovePropertyFunction>(base, RemovePropertyRva),
        atRva<ClearCollectionFunction>(base, ClearCollectionRva),
        atRva<ManagerGetOrAddFunction>(base, ManagerGetOrAddLevelPropertiesRva),
        atRva<ActorGetOrAddFunction>(base, ActorGetOrAddPropertiesRva),
    };
}

OperationResult failure(DynamicPropertyStatus status, std::string message) {
    return {status, std::move(message), {}, {}, 0};
}

std::optional<std::int64_t> parseActorId(std::string_view value) noexcept {
    std::int64_t result{};
    const auto [end, error] =
        std::from_chars(value.data(), value.data() + value.size(), result);
    if (error != std::errc{} || end != value.data() + value.size()) return std::nullopt;
    return result;
}

DynamicPropertyValue fromNative(const NativePropertyValue &value) {
    return std::visit([](const auto &entry) -> DynamicPropertyValue {
        using T = std::decay_t<decltype(entry)>;
        if constexpr (std::is_same_v<T, float>) {
            return static_cast<double>(entry);
        } else if constexpr (std::is_same_v<T, NativeVec3>) {
            return Vector3{entry.x, entry.y, entry.z};
        } else {
            return entry;
        }
    }, value);
}

NativePropertyValue toNative(const DynamicPropertyValue &value) {
    return std::visit([](const auto &entry) -> NativePropertyValue {
        using T = std::decay_t<decltype(entry)>;
        if constexpr (std::is_same_v<T, Vector3>) {
            constexpr auto Maximum = static_cast<double>(std::numeric_limits<float>::max());
            if (std::abs(entry.x) > Maximum || std::abs(entry.y) > Maximum ||
                std::abs(entry.z) > Maximum) {
                throw std::out_of_range("vector coordinate exceeds Bedrock float range");
            }
            return NativeVec3{
                static_cast<float>(entry.x),
                static_cast<float>(entry.y),
                static_cast<float>(entry.z),
            };
        } else {
            return entry;
        }
    }, value);
}

struct ResolvedTarget {
    NativeDynamicProperties *properties{};
    DynamicPropertyStatus status{DynamicPropertyStatus::TargetUnavailable};
    std::string message;

    [[nodiscard]] bool ok() const noexcept { return properties != nullptr; }
};

std::atomic<std::uint64_t> TransactionCounter{1};

class ExperimentalLiveBds2633Adapter;

struct NativeHookState {
    std::mutex mutex;
    funchook_t *handle{};
    ExperimentalLiveBds2633Adapter *adapter{};
    std::weak_ptr<DynamicPropertyService> service;
    SetPropertyFunction set{};
    RemovePropertyFunction remove{};
    ClearCollectionFunction clear{};
};

NativeHookState &nativeHookState() {
    static NativeHookState State;
    return State;
}

thread_local bool InNativeApiMutation = false;

void hookedSetProperty(
    NativeDynamicProperties *properties,
    const std::string &key,
    const NativePropertyValue &value,
    const std::string &collection);
bool hookedRemoveProperty(
    NativeDynamicProperties *properties,
    const std::string &key,
    const std::string &collection);
void hookedClearCollection(
    NativeDynamicProperties *properties,
    const std::string &collection);

class ExperimentalLiveBds2633Adapter final : public IDynamicPropertyAdapter {
public:
    explicit ExperimentalLiveBds2633Adapter(endstone::Server &server)
        : server_(server), functions_(resolveFunctions()) {}

    [[nodiscard]] bool ready() const noexcept { return functions_.complete(); }

    ~ExperimentalLiveBds2633Adapter() override { uninstallHooks(); }

    [[nodiscard]] std::string_view name() const noexcept override {
        return hooks_installed_
            ? "bds-1.26.33.1-experimental-live-world-player-entity-hooks"
            : "bds-1.26.33.1-experimental-live-world-player-entity";
    }

    [[nodiscard]] DynamicPropertyCapabilities capabilities() const noexcept override {
        DynamicPropertyCapabilities out;
        if (!ready()) return out;
        out.world = true;
        out.online_players = true;
        out.loaded_entities = true;
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
        out.external_change_observation = hooks_installed_;
        out.external_change_cancellation = hooks_installed_;
        // Live objects are serialized by BDS's normal level/player/entity save
        // lifecycle. The tester verifies the durable result across a restart.
        out.persistence_flush = true;
        out.exact_build_match = true;
        out.exact_binary_hash_match = true;
        out.symbols_validated = true;
        return out;
    }

    bool installHooks() {
        auto &state = nativeHookState();
        std::lock_guard state_lock(state.mutex);
        if (state.handle || state.adapter) return false;

        state.handle = funchook_create();
        if (!state.handle) return false;
        state.adapter = this;
        state.set = functions_.set;
        state.remove = functions_.remove;
        state.clear = functions_.clear;
        const auto prepare = [&](auto &target, auto hook) {
            return funchook_prepare(
                state.handle,
                reinterpret_cast<void **>(&target),
                reinterpret_cast<void *>(hook)) == 0;
        };
        if (!prepare(state.set, hookedSetProperty) ||
            !prepare(state.remove, hookedRemoveProperty) ||
            !prepare(state.clear, hookedClearCollection) ||
            funchook_install(state.handle, 0) != 0) {
            funchook_destroy(state.handle);
            state.handle = nullptr;
            state.adapter = nullptr;
            state.set = nullptr;
            state.remove = nullptr;
            state.clear = nullptr;
            return false;
        }

        // funchook rewrites these pointers to trampolines. Adapter-originated
        // operations use them directly and therefore do not self-report as
        // external Script API mutations.
        functions_.set = state.set;
        functions_.remove = state.remove;
        functions_.clear = state.clear;
        hooks_installed_ = true;
        return true;
    }

    void primeTargets() {
        std::lock_guard lock(mutex_);
        auto world = DynamicPropertyTarget::world(
            server_.getLevel() ? server_.getLevel()->getName() : "default");
        static_cast<void>(resolveTarget(world));
        if (auto *level = server_.getLevel()) {
            for (auto *actor : level->getActors()) {
                if (actor) {
                    static_cast<void>(resolveTarget(DynamicPropertyTarget::loadedEntity(
                        std::to_string(actor->getId()), world.world_id)));
                }
            }
        }
        for (auto *player : server_.getOnlinePlayers()) {
            if (player) {
                static_cast<void>(resolveTarget(DynamicPropertyTarget::onlinePlayer(
                    player->getXuid(), world.world_id)));
            }
        }
    }

    [[nodiscard]] std::optional<DynamicPropertyTarget> targetFor(
        NativeDynamicProperties *properties) const {
        std::lock_guard lock(target_mutex_);
        const auto found = known_targets_.find(properties);
        if (found == known_targets_.end()) return std::nullopt;
        return found->second;
    }

    [[nodiscard]] CaptureResult capture(const CollectionRef &ref) override {
        std::lock_guard lock(mutex_);
        return captureUnlocked(ref);
    }

    [[nodiscard]] ListCollectionsResult listCollections(
        const DynamicPropertyTarget &target) override {
        std::lock_guard lock(mutex_);
        const auto resolved = resolveTarget(target);
        if (!resolved.ok()) return {resolved.status, resolved.message, {}};
        std::vector<std::string> collections;
        collections.reserve(resolved.properties->collections.size());
        for (const auto &[name, unused] : resolved.properties->collections) {
            static_cast<void>(unused);
            collections.push_back(name);
        }
        std::ranges::sort(collections);
        return {DynamicPropertyStatus::Captured, "captured live collection inventory",
                std::move(collections)};
    }

    OperationResult apply(const DynamicPropertyOperation &operation, bool force) override {
        std::lock_guard lock(mutex_);
        return applyUnlocked(operation, force);
    }

    TransactionResult transact(
        const DynamicPropertyTransaction &transaction) override {
        std::lock_guard lock(mutex_);
        TransactionResult out;
        out.transaction_id =
            "bds-live-tx-" + std::to_string(TransactionCounter.fetch_add(1));

        const auto refs = uniqueRefs(transaction.operations);
        std::vector<CollectionSnapshot> originals;
        originals.reserve(refs.size());
        for (const auto &ref : refs) {
            auto captured = captureUnlocked(ref);
            if (!captured.ok() || !captured.snapshot) {
                out.status = captured.status;
                out.message = captured.message;
                return out;
            }
            originals.push_back(*captured.snapshot);
        }

        out.operation_results.reserve(transaction.operations.size());
        for (const auto &operation : transaction.operations) {
            auto result = applyUnlocked(operation, transaction.force);
            out.operation_results.push_back(result);
            if (result.ok()) continue;
            out.status = DynamicPropertyStatus::TransactionFailed;
            out.message = result.message;
            if (transaction.rollback_on_failure) {
                out.rolled_back = restore(originals);
                if (!out.rolled_back) {
                    out.status = DynamicPropertyStatus::RollbackFailed;
                    out.message += "; rollback did not fully restore the native state";
                }
            }
            return out;
        }
        out.status = DynamicPropertyStatus::Applied;
        out.message = "live transaction applied";
        return out;
    }

    OperationResult flush(const DynamicPropertyTarget &target) override {
        std::lock_guard lock(mutex_);
        const auto resolved = resolveTarget(target);
        if (!resolved.ok()) return failure(resolved.status, resolved.message);
        return {
            DynamicPropertyStatus::Applied,
            "live state handed to the BDS persistence lifecycle",
            {},
            {},
            0,
        };
    }

private:
    void uninstallHooks() noexcept {
        if (!hooks_installed_) return;
        auto &state = nativeHookState();
        std::lock_guard state_lock(state.mutex);
        if (state.adapter != this) return;
        if (state.handle) {
            static_cast<void>(funchook_uninstall(state.handle, 0));
            funchook_destroy(state.handle);
        }
        state.handle = nullptr;
        state.adapter = nullptr;
        state.set = nullptr;
        state.remove = nullptr;
        state.clear = nullptr;
        state.service.reset();
        hooks_installed_ = false;
    }

    void rememberTarget(
        NativeDynamicProperties *properties,
        const DynamicPropertyTarget &target) const {
        if (!properties) return;
        std::lock_guard lock(target_mutex_);
        known_targets_.insert_or_assign(properties, target);
    }

    [[nodiscard]] ::Level *minecraftLevel() const noexcept {
        auto *level = server_.getLevel();
        if (!level) return nullptr;
        // Endstone v0.11.6 EndstoneLevel has one polymorphic base followed by
        // server_ and level_ reference data members. Reading the exact private
        // handle avoids relying on a non-public exported C++ symbol.
        ::Level *handle = nullptr;
        const auto *address = reinterpret_cast<const std::byte *>(level) +
                              EndstoneLevelHandleWord * sizeof(void *);
        std::memcpy(&handle, address, sizeof(handle));
        return handle;
    }

    [[nodiscard]] ::Actor *minecraftActor(std::int64_t unique_id) const noexcept {
        auto *level = minecraftLevel();
        return level ? level->fetchEntity(ActorUniqueID{unique_id}, false) : nullptr;
    }

    [[nodiscard]] ResolvedTarget resolveTarget(
        const DynamicPropertyTarget &target) const {
        if (!ready()) {
            return {nullptr, DynamicPropertyStatus::SymbolValidationFailed,
                    "exact native function table is unavailable"};
        }

        if (target.kind == TargetKind::World) {
            auto *level = minecraftLevel();
            if (!level) {
                return {nullptr, DynamicPropertyStatus::TargetUnavailable,
                        "Endstone has no live server level"};
            }
            void *manager = nullptr;
            std::memcpy(
                &manager,
                reinterpret_cast<const std::byte *>(level) +
                    ServerLevelDynamicPropertiesManagerOffset,
                sizeof(manager));
            if (!manager) {
                return {nullptr, DynamicPropertyStatus::TargetUnavailable,
                        "BDS dynamic-properties manager is unavailable"};
            }
            auto *properties = functions_.get_or_add_level(manager);
            rememberTarget(properties, target);
            return properties
                ? ResolvedTarget{properties, DynamicPropertyStatus::Captured, {}}
                : ResolvedTarget{nullptr, DynamicPropertyStatus::TargetUnavailable,
                                 "BDS did not return world dynamic properties"};
        }

        std::optional<std::int64_t> actor_id;
        if (target.kind == TargetKind::OnlinePlayer) {
            for (auto *player : server_.getOnlinePlayers()) {
                if (player && player->getXuid() == target.xuid) {
                    actor_id = player->getId();
                    break;
                }
            }
            if (!actor_id) {
                return {nullptr, DynamicPropertyStatus::TargetUnavailable,
                        "online player XUID is not loaded"};
            }
        } else if (target.kind == TargetKind::LoadedEntity) {
            actor_id = parseActorId(target.entity_id);
            if (!actor_id) {
                return {nullptr, DynamicPropertyStatus::InvalidTarget,
                        "loaded entity identifier must be a signed ActorUniqueID"};
            }
            bool exposed_by_endstone = false;
            if (auto *level = server_.getLevel()) {
                for (auto *actor : level->getActors()) {
                    if (actor && actor->getId() == *actor_id) {
                        exposed_by_endstone = true;
                        break;
                    }
                }
            }
            if (!exposed_by_endstone) {
                return {nullptr, DynamicPropertyStatus::TargetUnavailable,
                        "loaded entity is not present in Endstone's actor registry"};
            }
        } else {
            return {nullptr, DynamicPropertyStatus::Unsupported,
                    "experimental adapter does not implement target kind " +
                        std::string(targetKindName(target.kind))};
        }

        auto *actor = minecraftActor(*actor_id);
        if (!actor) {
            return {nullptr, DynamicPropertyStatus::TargetUnavailable,
                    "BDS actor is no longer loaded"};
        }
        auto *entity_context =
            reinterpret_cast<std::byte *>(actor) + ActorEntityContextOffset;
        auto *properties = functions_.get_or_add_actor(entity_context);
        rememberTarget(properties, target);
        return properties
            ? ResolvedTarget{properties, DynamicPropertyStatus::Captured, {}}
            : ResolvedTarget{nullptr, DynamicPropertyStatus::TargetUnavailable,
                             "BDS actor dynamic-properties component is unavailable"};
    }

    [[nodiscard]] CaptureResult captureUnlocked(const CollectionRef &ref) const {
        const auto resolved = resolveTarget(ref.target);
        if (!resolved.ok()) return {resolved.status, resolved.message, std::nullopt};
        const auto collection = resolved.properties->collections.find(ref.collection);
        if (collection == resolved.properties->collections.end()) {
            return {
                DynamicPropertyStatus::Captured,
                "live collection does not exist",
                makeSnapshot(ref, {}, false, true, true, true),
            };
        }

        DynamicPropertyMap values;
        for (const auto &[key, value] : collection->second.properties) {
            values.emplace(key, fromNative(value));
        }
        auto snapshot = makeSnapshot(ref, std::move(values), true, true, true, true);
        snapshot.byte_count = collection->second.byte_count;
        return {DynamicPropertyStatus::Captured, "captured live BDS collection",
                std::move(snapshot)};
    }

    [[nodiscard]] static std::vector<CollectionRef> uniqueRefs(
        const std::vector<DynamicPropertyOperation> &operations) {
        std::set<CollectionRef> refs;
        for (const auto &operation : operations) {
            const auto operation_refs = operationCollections(operation);
            refs.insert(operation_refs.begin(), operation_refs.end());
        }
        return {refs.begin(), refs.end()};
    }

    bool writeSnapshot(const CollectionSnapshot &snapshot) const {
        const auto resolved = resolveTarget(snapshot.ref.target);
        if (!resolved.ok()) return false;
        const bool previous = std::exchange(InNativeApiMutation, true);
        struct MutationGuard {
            bool previous;
            ~MutationGuard() { InNativeApiMutation = previous; }
        } guard{previous};
        functions_.clear(resolved.properties, snapshot.ref.collection);
        if (!snapshot.exists) return true;
        for (const auto &[key, value] : snapshot.properties) {
            const auto native = toNative(value);
            functions_.set(
                resolved.properties, key, native, snapshot.ref.collection);
        }
        return true;
    }

    bool restore(const std::vector<CollectionSnapshot> &snapshots) const noexcept {
        bool restored = true;
        for (const auto &snapshot : snapshots) {
            try {
                restored = writeSnapshot(snapshot) && restored;
            } catch (...) {
                restored = false;
            }
        }
        return restored;
    }

    OperationResult applyUnlocked(
        const DynamicPropertyOperation &operation,
        bool force) {
        const auto refs_raw = operationCollections(operation);
        const std::set<CollectionRef> refs(refs_raw.begin(), refs_raw.end());
        std::vector<CollectionSnapshot> before;
        before.reserve(refs.size());

        auto planner = makeInMemoryDynamicPropertyAdapter();
        for (const auto &ref : refs) {
            auto captured = captureUnlocked(ref);
            if (!captured.ok() || !captured.snapshot)
                return failure(captured.status, captured.message);
            before.push_back(*captured.snapshot);
            if (!captured.snapshot->exists) continue;
            const ImportCollectionOperation seed{
                ref,
                captured.snapshot->properties,
                std::nullopt,
                ImportPolicy::Replace,
            };
            const auto seeded = planner->apply(seed, true);
            if (!seeded.ok())
                return failure(DynamicPropertyStatus::AdapterError,
                               "could not prepare native mutation plan");
        }

        auto planned = planner->apply(operation, force);
        if (!planned.ok()) {
            planned.before = std::move(before);
            return planned;
        }

        std::vector<CollectionSnapshot> desired;
        desired.reserve(refs.size());
        for (const auto &ref : refs) {
            auto captured = planner->capture(ref);
            if (!captured.ok() || !captured.snapshot)
                return failure(DynamicPropertyStatus::AdapterError,
                               "native mutation plan produced no snapshot");
            desired.push_back(*captured.snapshot);
        }

        try {
            for (const auto &snapshot : desired) {
                if (!writeSnapshot(snapshot)) {
                    restore(before);
                    return failure(DynamicPropertyStatus::TargetUnavailable,
                                   "target became unavailable during native mutation");
                }
            }
        } catch (const std::out_of_range &error) {
            restore(before);
            return failure(DynamicPropertyStatus::InvalidValue, error.what());
        } catch (const std::exception &error) {
            restore(before);
            return failure(DynamicPropertyStatus::AdapterError,
                           std::string("BDS mutation failed: ") + error.what());
        } catch (...) {
            restore(before);
            return failure(DynamicPropertyStatus::AdapterError,
                           "BDS mutation failed with an unknown native exception");
        }

        OperationResult result;
        result.status = DynamicPropertyStatus::Applied;
        result.message = "applied to live BDS dynamic properties";
        result.before = std::move(before);
        for (const auto &ref : refs) {
            auto captured = captureUnlocked(ref);
            if (!captured.ok() || !captured.snapshot) {
                result.status = captured.status;
                result.message = captured.message;
                return result;
            }
            result.resulting_revision = captured.snapshot->revision;
            result.after.push_back(*captured.snapshot);
        }
        return result;
    }

    endstone::Server &server_;
    NativeFunctions functions_;
    mutable std::recursive_mutex mutex_;
    mutable std::mutex target_mutex_;
    mutable std::unordered_map<
        NativeDynamicProperties *, DynamicPropertyTarget> known_targets_;
    bool hooks_installed_{};
};

struct HookInvocation {
    ExperimentalLiveBds2633Adapter *adapter{};
    std::shared_ptr<DynamicPropertyService> service;
    SetPropertyFunction set{};
    RemovePropertyFunction remove{};
    ClearCollectionFunction clear{};
};

HookInvocation hookInvocation() {
    auto &state = nativeHookState();
    std::lock_guard lock(state.mutex);
    return {
        state.adapter,
        state.service.lock(),
        state.set,
        state.remove,
        state.clear,
    };
}

AccessContext nativeHookContext() {
    return {
        "native-hook",
        "bds-script-or-engine",
        true,
        MutationOrigin::NativeHook,
        "intercepted exact BDS DynamicProperties mutation",
    };
}

template <typename Operation, typename OriginalCall>
auto interceptMutation(
    NativeDynamicProperties *properties,
    Operation operation,
    OriginalCall original_call) -> decltype(original_call()) {
    using Result = decltype(original_call());
    const auto invocation = hookInvocation();
    if (InNativeApiMutation || !invocation.adapter || !invocation.service) {
        return original_call();
    }
    const auto target = invocation.adapter->targetFor(properties);
    if (!target) return original_call();
    operation.ref.target = *target;

    auto gate = invocation.service->beforeExternalMutation(
        operation, nativeHookContext(), true);
    if (gate.decision == ExternalMutationDecision::Cancel) {
        if constexpr (std::is_void_v<Result>) return;
        else return Result{};
    }

    if constexpr (std::is_void_v<Result>) {
        original_call();
        OperationResult applied{
            DynamicPropertyStatus::Applied,
            "external native mutation applied",
            {},
            {},
            0,
        };
        auto after = invocation.adapter->capture(operation.ref);
        if (after.snapshot) {
            applied.after.push_back(*after.snapshot);
            applied.resulting_revision = after.snapshot->revision;
        }
        invocation.service->afterExternalMutation(
            operation, applied, nativeHookContext(), std::move(gate.transaction_id));
        return;
    } else {
        const auto native_result = original_call();
        OperationResult applied{
            native_result ? DynamicPropertyStatus::Applied
                          : DynamicPropertyStatus::NotFound,
            native_result ? "external native mutation applied"
                          : "external native property did not exist",
            {},
            {},
            0,
        };
        auto after = invocation.adapter->capture(operation.ref);
        if (after.snapshot) {
            applied.after.push_back(*after.snapshot);
            applied.resulting_revision = after.snapshot->revision;
        }
        invocation.service->afterExternalMutation(
            operation, applied, nativeHookContext(), std::move(gate.transaction_id));
        return native_result;
    }
}

void hookedSetProperty(
    NativeDynamicProperties *properties,
    const std::string &key,
    const NativePropertyValue &value,
    const std::string &collection) {
    const auto invocation = hookInvocation();
    if (!invocation.set) return;
    SetPropertyOperation operation{
        CollectionRef{DynamicPropertyTarget::world(), collection},
        key,
        fromNative(value),
        std::nullopt,
    };
    interceptMutation(properties, std::move(operation), [&] {
        invocation.set(properties, key, value, collection);
    });
}

bool hookedRemoveProperty(
    NativeDynamicProperties *properties,
    const std::string &key,
    const std::string &collection) {
    const auto invocation = hookInvocation();
    if (!invocation.remove) return false;
    RemovePropertyOperation operation{
        CollectionRef{DynamicPropertyTarget::world(), collection},
        key,
        std::nullopt,
        false,
    };
    return interceptMutation(properties, std::move(operation), [&] {
        return invocation.remove(properties, key, collection);
    });
}

void hookedClearCollection(
    NativeDynamicProperties *properties,
    const std::string &collection) {
    const auto invocation = hookInvocation();
    if (!invocation.clear) return;
    ClearCollectionOperation operation{
        CollectionRef{DynamicPropertyTarget::world(), collection},
        std::nullopt,
        true,
    };
    interceptMutation(properties, std::move(operation), [&] {
        invocation.clear(properties, collection);
    });
}

} // namespace

std::shared_ptr<IDynamicPropertyAdapter>
makeExperimentalLiveBds2633DynamicPropertyAdapter(endstone::Server &server) {
    auto adapter = std::make_shared<ExperimentalLiveBds2633Adapter>(server);
    if (!adapter->ready()) return nullptr;
    static_cast<void>(adapter->installHooks());
    adapter->primeTargets();
    return adapter;
}

void bindExperimentalLiveBds2633Service(
    std::shared_ptr<DynamicPropertyService> service) {
    auto &state = nativeHookState();
    std::lock_guard lock(state.mutex);
    state.service = std::move(service);
}

void unbindExperimentalLiveBds2633Service() noexcept {
    auto &state = nativeHookState();
    std::lock_guard lock(state.mutex);
    state.service.reset();
}

} // namespace endstone_dynamic_properties

#endif
