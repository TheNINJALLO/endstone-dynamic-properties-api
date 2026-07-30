#include "endstone_dynamic_properties/events.h"

#include <algorithm>
#include <type_traits>

namespace endstone_dynamic_properties {

bool EventFilter::matches(const DynamicPropertyEvent &event) const {
    if (kind && *kind != event.kind) return false;
    if (key && (!event.key || *key != *event.key)) return false;
    if (!target_kind && !target && !collection) return true;
    return std::any_of(event.collections.begin(), event.collections.end(), [&](const CollectionRef &ref) {
        if (target_kind && ref.target.kind != *target_kind) return false;
        if (target && ref.target != *target) return false;
        if (collection && ref.collection != *collection) return false;
        return true;
    });
}

std::uint64_t DynamicPropertyEventBus::subscribe(EventFilter filter, Listener listener) {
    if (!listener) return 0;
    std::lock_guard lock(mutex_);
    const auto id = next_subscription_id_++;
    subscriptions_.emplace(id, Subscription{std::move(filter), std::move(listener)});
    return id;
}

bool DynamicPropertyEventBus::unsubscribe(std::uint64_t subscription_id) {
    std::lock_guard lock(mutex_);
    return subscriptions_.erase(subscription_id) > 0;
}

void DynamicPropertyEventBus::setListenerFailureHandler(
    ListenerFailureHandler handler) {
    std::lock_guard lock(mutex_);
    failure_handler_ = std::move(handler);
}

std::vector<std::exception_ptr> DynamicPropertyEventBus::publish(
    DynamicPropertyEvent &event) const {
    std::vector<std::pair<std::uint64_t, Subscription>> listeners;
    ListenerFailureHandler failure_handler;
    {
        std::lock_guard lock(mutex_);
        listeners.reserve(subscriptions_.size());
        for (const auto &[id, subscription] : subscriptions_) {
            if (subscription.filter.matches(event))
                listeners.emplace_back(id, subscription);
        }
        failure_handler = failure_handler_;
    }
    std::vector<std::exception_ptr> failures;
    for (auto &[id, subscription] : listeners) {
        try {
            subscription.listener(event);
        } catch (...) {
            // A faulty observer must not escape after a mutation committed,
            // suppress later observers, or prevent the service audit record.
            auto failure = std::current_exception();
            failures.push_back(failure);
            if (failure_handler) {
                try {
                    failure_handler(id, failure);
                } catch (...) {
                    // Failure reporting is isolated for the same reason as listeners.
                }
            }
        }
    }
    return failures;
}

std::optional<std::string> operationPrimaryKey(const DynamicPropertyOperation &operation) {
    return std::visit([](const auto &entry) -> std::optional<std::string> {
        using T = std::decay_t<decltype(entry)>;
        if constexpr (std::is_same_v<T, SetPropertyOperation> ||
                      std::is_same_v<T, RemovePropertyOperation>) {
            return entry.key;
        } else if constexpr (std::is_same_v<T, TransferPropertyOperation>) {
            return entry.destination_key;
        } else {
            return std::nullopt;
        }
    }, operation);
}

} // namespace endstone_dynamic_properties
