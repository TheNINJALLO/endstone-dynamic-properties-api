#pragma once

#include "endstone_dynamic_properties/operations.h"

#include <cstdint>
#include <exception>
#include <functional>
#include <map>
#include <mutex>
#include <optional>
#include <string>
#include <vector>

namespace endstone_dynamic_properties {

enum class DynamicPropertyEventKind {
    BeforeMutation,
    AfterMutation,
    BeforeTransaction,
    AfterTransaction,
    BeforeExternalMutation,
    AfterExternalMutation,
    CollectionMigrated,
};

struct DynamicPropertyEvent {
    DynamicPropertyEventKind kind{DynamicPropertyEventKind::BeforeMutation};
    std::string transaction_id;
    std::string operation_name;
    AccessContext actor;
    std::vector<CollectionRef> collections;
    std::optional<std::string> key;
    std::vector<CollectionSnapshot> before;
    std::vector<CollectionSnapshot> after;
    bool cancellable{};
    bool cancelled{};
    std::string cancellation_reason;
};

struct EventFilter {
    std::optional<DynamicPropertyEventKind> kind;
    std::optional<TargetKind> target_kind;
    std::optional<DynamicPropertyTarget> target;
    std::optional<std::string> collection;
    std::optional<std::string> key;

    [[nodiscard]] bool matches(const DynamicPropertyEvent &event) const;
};

class DynamicPropertyEventBus {
public:
    using Listener = std::function<void(DynamicPropertyEvent &)>;
    using ListenerFailureHandler =
        std::function<void(std::uint64_t, std::exception_ptr)>;

    std::uint64_t subscribe(EventFilter filter, Listener listener);
    bool unsubscribe(std::uint64_t subscription_id);
    void setListenerFailureHandler(ListenerFailureHandler handler);
    [[nodiscard]] std::vector<std::exception_ptr> publish(
        DynamicPropertyEvent &event) const;

private:
    struct Subscription {
        EventFilter filter;
        Listener listener;
    };
    mutable std::mutex mutex_;
    std::map<std::uint64_t, Subscription> subscriptions_;
    std::uint64_t next_subscription_id_{1};
    ListenerFailureHandler failure_handler_;
};

[[nodiscard]] std::optional<std::string> operationPrimaryKey(
    const DynamicPropertyOperation &operation);

} // namespace endstone_dynamic_properties
