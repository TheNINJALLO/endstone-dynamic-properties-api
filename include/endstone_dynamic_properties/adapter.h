#pragma once

#include "endstone_dynamic_properties/operations.h"

#include <memory>
#include <string_view>

namespace endstone_dynamic_properties {

class IDynamicPropertyAdapter {
public:
    virtual ~IDynamicPropertyAdapter() = default;
    [[nodiscard]] virtual std::string_view name() const noexcept = 0;
    [[nodiscard]] virtual DynamicPropertyCapabilities capabilities() const noexcept = 0;
    [[nodiscard]] virtual CaptureResult capture(const CollectionRef &ref) = 0;
    [[nodiscard]] virtual ListCollectionsResult listCollections(
        const DynamicPropertyTarget &target) = 0;
    virtual OperationResult apply(const DynamicPropertyOperation &operation, bool force) = 0;
    virtual TransactionResult transact(const DynamicPropertyTransaction &transaction) = 0;
    virtual OperationResult flush(const DynamicPropertyTarget &target) = 0;
};

} // namespace endstone_dynamic_properties
