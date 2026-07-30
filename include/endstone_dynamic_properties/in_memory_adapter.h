#pragma once

#include "endstone_dynamic_properties/adapter.h"

#include <map>
#include <mutex>

namespace endstone_dynamic_properties {

class InMemoryDynamicPropertyAdapter final : public IDynamicPropertyAdapter {
public:
    [[nodiscard]] std::string_view name() const noexcept override {
        return "in-memory-complete-reference";
    }
    [[nodiscard]] DynamicPropertyCapabilities capabilities() const noexcept override;
    [[nodiscard]] CaptureResult capture(const CollectionRef &ref) override;
    [[nodiscard]] ListCollectionsResult listCollections(
        const DynamicPropertyTarget &target) override;
    OperationResult apply(const DynamicPropertyOperation &operation, bool force) override;
    TransactionResult transact(const DynamicPropertyTransaction &transaction) override;
    OperationResult flush(const DynamicPropertyTarget &target) override;

    void setTargetAvailable(DynamicPropertyTarget target, bool available);
    [[nodiscard]] std::size_t collectionCount() const;

private:
    using Store = std::map<CollectionRef, DynamicPropertyMap>;

    [[nodiscard]] CaptureResult captureUnlocked(
        const Store &store,
        const CollectionRef &ref) const;
    [[nodiscard]] OperationResult applyUnlocked(
        Store &store,
        const DynamicPropertyOperation &operation,
        bool force) const;
    [[nodiscard]] bool targetAvailableUnlocked(const DynamicPropertyTarget &target) const;

    mutable std::mutex mutex_;
    Store store_;
    std::map<DynamicPropertyTarget, bool> availability_;
};

std::shared_ptr<InMemoryDynamicPropertyAdapter> makeInMemoryDynamicPropertyAdapter();

} // namespace endstone_dynamic_properties
