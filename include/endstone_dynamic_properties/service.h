#pragma once

#include "endstone_dynamic_properties/access_policy.h"
#include "endstone_dynamic_properties/adapter.h"
#include "endstone_dynamic_properties/audit.h"

#include <exception>
#include <functional>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <vector>

namespace endstone_dynamic_properties {

struct PropertyReadResult {
    DynamicPropertyStatus status{DynamicPropertyStatus::AdapterError};
    std::string message;
    std::optional<DynamicPropertyValue> value;
    std::uint64_t collection_revision{};
    [[nodiscard]] bool ok() const noexcept {
        return status == DynamicPropertyStatus::Captured;
    }
};

struct ExportResult {
    DynamicPropertyStatus status{DynamicPropertyStatus::AdapterError};
    std::string message;
    std::string document;
    std::uint64_t revision{};
    [[nodiscard]] bool ok() const noexcept {
        return status == DynamicPropertyStatus::Captured;
    }
};

struct ExternalMutationGateResult {
    ExternalMutationDecision decision{ExternalMutationDecision::ObserveOnly};
    DynamicPropertyStatus status{DynamicPropertyStatus::Applied};
    std::string message;
    std::string transaction_id;
};

class DynamicPropertyService {
public:
    using AuditFailureHandler = std::function<void(std::exception_ptr)>;

    explicit DynamicPropertyService(
        std::shared_ptr<IDynamicPropertyAdapter> adapter,
        ValidationLimits limits = {},
        std::shared_ptr<DynamicPropertyEventBus> event_bus = {},
        std::shared_ptr<IDynamicPropertyAuditSink> audit_sink = {},
        DynamicPropertyAccessPolicy access_policy = DynamicPropertyAccessPolicy{});

    [[nodiscard]] CaptureResult capture(
        const CollectionRef &ref,
        const AccessContext &context) const;
    [[nodiscard]] PropertyReadResult get(
        const CollectionRef &ref,
        std::string_view key,
        const AccessContext &context) const;
    [[nodiscard]] ListCollectionsResult listCollections(
        const DynamicPropertyTarget &target,
        const AccessContext &context) const;
    OperationResult apply(
        const DynamicPropertyOperation &operation,
        const AccessContext &context,
        bool force = false);
    TransactionResult transact(
        const DynamicPropertyTransaction &transaction,
        const AccessContext &context);
    OperationResult flush(
        const DynamicPropertyTarget &target,
        const AccessContext &context);

    OperationResult set(
        CollectionRef ref,
        std::string key,
        DynamicPropertyValue value,
        const AccessContext &context,
        std::optional<std::uint64_t> expected_revision = {});
    OperationResult setMany(
        CollectionRef ref,
        DynamicPropertyMap values,
        const AccessContext &context,
        std::optional<std::uint64_t> expected_revision = {});
    OperationResult remove(
        CollectionRef ref,
        std::string key,
        const AccessContext &context,
        std::optional<std::uint64_t> expected_revision = {},
        bool require_existing = false);
    OperationResult clear(
        CollectionRef ref,
        const AccessContext &context,
        std::optional<std::uint64_t> expected_revision = {},
        bool remove_collection = false);
    OperationResult migrateCollection(
        CollectionRef source,
        CollectionRef destination,
        const AccessContext &context,
        ImportPolicy policy = ImportPolicy::FailIfDestinationExists,
        bool remove_source = true,
        std::optional<std::uint64_t> expected_source_revision = {},
        std::optional<std::uint64_t> expected_destination_revision = {});
    [[nodiscard]] ExportResult exportCollection(
        const CollectionRef &ref,
        const AccessContext &context) const;
    OperationResult importCollection(
        CollectionRef destination,
        std::string_view document,
        const AccessContext &context,
        ImportPolicy policy = ImportPolicy::Merge,
        std::optional<std::uint64_t> expected_revision = {});

    [[nodiscard]] ExternalMutationGateResult beforeExternalMutation(
        const DynamicPropertyOperation &operation,
        AccessContext context,
        bool cancellable);
    void afterExternalMutation(
        const DynamicPropertyOperation &operation,
        const OperationResult &result,
        AccessContext context,
        std::string transaction_id = {});

    [[nodiscard]] DynamicPropertyCapabilities capabilities() const noexcept;
    [[nodiscard]] std::string adapterName() const;
    [[nodiscard]] std::shared_ptr<DynamicPropertyEventBus> eventBus() const noexcept {
        return event_bus_;
    }
    [[nodiscard]] std::shared_ptr<IDynamicPropertyAuditSink> auditSink() const noexcept {
        return audit_sink_;
    }
    void setAuditFailureHandler(AuditFailureHandler handler);
    [[nodiscard]] const DynamicPropertyAccessPolicy &accessPolicy() const noexcept {
        return access_policy_;
    }

private:
    [[nodiscard]] std::optional<OperationResult> validateOperation(
        const DynamicPropertyOperation &operation,
        const AccessContext &context) const;
    [[nodiscard]] std::optional<OperationResult> validateCapability(
        const DynamicPropertyTarget &target) const;
    [[nodiscard]] std::optional<OperationResult> validatePropertyLimits(
        const std::vector<DynamicPropertyOperation> &operations) const;
    [[nodiscard]] bool publishBefore(
        DynamicPropertyEventKind kind,
        const DynamicPropertyOperation &operation,
        const AccessContext &context,
        std::string transaction_id,
        bool cancellable,
        std::string &reason) const;
    void publishAfter(
        DynamicPropertyEventKind kind,
        const DynamicPropertyOperation &operation,
        const AccessContext &context,
        const OperationResult &result,
        std::string transaction_id) const;
    void audit(
        const DynamicPropertyOperation &operation,
        const AccessContext &context,
        const OperationResult &result,
        std::string transaction_id,
        bool external = false,
        bool rolled_back = false) const noexcept;
    void reportAuditFailure(std::exception_ptr failure) const noexcept;
    [[nodiscard]] static std::string makeTransactionId();

    std::shared_ptr<IDynamicPropertyAdapter> adapter_;
    ValidationLimits limits_;
    std::shared_ptr<DynamicPropertyEventBus> event_bus_;
    std::shared_ptr<IDynamicPropertyAuditSink> audit_sink_;
    mutable std::mutex audit_failure_mutex_;
    AuditFailureHandler audit_failure_handler_;
    DynamicPropertyAccessPolicy access_policy_;
    // Shared by services that wrap the same adapter instance. It serializes
    // commit-time revalidation and writes; callbacks always run outside it.
    std::shared_ptr<std::recursive_mutex> mutation_mutex_;
};

} // namespace endstone_dynamic_properties
