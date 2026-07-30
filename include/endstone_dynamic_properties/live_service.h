#pragma once

#include "endstone_dynamic_properties/service.h"

#include <endstone/plugin/service.h>

#include <cstdint>
#include <memory>
#include <string_view>

namespace endstone_dynamic_properties {

inline constexpr std::uint32_t DynamicPropertyServiceAbiVersion = 1;
inline constexpr std::string_view DynamicPropertyServiceName =
    "endstone:dynamic-properties:v1";

class LiveDynamicPropertyService : public endstone::Service {
public:
    ~LiveDynamicPropertyService() override = default;

    [[nodiscard]] virtual CaptureResult capture(
        const CollectionRef &ref,
        const AccessContext &context) const = 0;
    [[nodiscard]] virtual PropertyReadResult get(
        const CollectionRef &ref,
        std::string_view key,
        const AccessContext &context) const = 0;
    [[nodiscard]] virtual ListCollectionsResult listCollections(
        const DynamicPropertyTarget &target,
        const AccessContext &context) const = 0;
    virtual OperationResult apply(
        const DynamicPropertyOperation &operation,
        const AccessContext &context,
        bool force = false) = 0;
    virtual TransactionResult transact(
        const DynamicPropertyTransaction &transaction,
        const AccessContext &context) = 0;
    virtual OperationResult flush(
        const DynamicPropertyTarget &target,
        const AccessContext &context) = 0;
    virtual OperationResult migrateCollection(
        CollectionRef source,
        CollectionRef destination,
        const AccessContext &context,
        ImportPolicy policy = ImportPolicy::FailIfDestinationExists,
        bool remove_source = true,
        std::optional<std::uint64_t> expected_source_revision = {},
        std::optional<std::uint64_t> expected_destination_revision = {}) = 0;
    [[nodiscard]] virtual ExportResult exportCollection(
        const CollectionRef &ref,
        const AccessContext &context) const = 0;
    virtual OperationResult importCollection(
        CollectionRef destination,
        std::string_view document,
        const AccessContext &context,
        ImportPolicy policy = ImportPolicy::Merge,
        std::optional<std::uint64_t> expected_revision = {}) = 0;
    [[nodiscard]] virtual ExternalMutationGateResult beforeExternalMutation(
        const DynamicPropertyOperation &operation,
        AccessContext context,
        bool cancellable) = 0;
    virtual void afterExternalMutation(
        const DynamicPropertyOperation &operation,
        const OperationResult &result,
        AccessContext context,
        std::string transaction_id = {}) = 0;
    [[nodiscard]] virtual DynamicPropertyCapabilities capabilities() const noexcept = 0;
    [[nodiscard]] virtual std::string adapterName() const = 0;
    [[nodiscard]] virtual std::shared_ptr<DynamicPropertyEventBus> eventBus() const noexcept = 0;
    [[nodiscard]] virtual std::shared_ptr<IDynamicPropertyAuditSink> auditSink() const noexcept = 0;
};

class LiveDynamicPropertyServiceProvider final : public LiveDynamicPropertyService {
public:
    explicit LiveDynamicPropertyServiceProvider(
        std::shared_ptr<DynamicPropertyService> service)
        : service_(std::move(service)) {}

    [[nodiscard]] CaptureResult capture(
        const CollectionRef &ref,
        const AccessContext &context) const override {
        return service_->capture(ref, context);
    }
    [[nodiscard]] PropertyReadResult get(
        const CollectionRef &ref,
        std::string_view key,
        const AccessContext &context) const override {
        return service_->get(ref, key, context);
    }
    [[nodiscard]] ListCollectionsResult listCollections(
        const DynamicPropertyTarget &target,
        const AccessContext &context) const override {
        return service_->listCollections(target, context);
    }
    OperationResult apply(
        const DynamicPropertyOperation &operation,
        const AccessContext &context,
        bool force) override {
        return service_->apply(operation, context, force);
    }
    TransactionResult transact(
        const DynamicPropertyTransaction &transaction,
        const AccessContext &context) override {
        return service_->transact(transaction, context);
    }
    OperationResult flush(
        const DynamicPropertyTarget &target,
        const AccessContext &context) override {
        return service_->flush(target, context);
    }
    OperationResult migrateCollection(
        CollectionRef source,
        CollectionRef destination,
        const AccessContext &context,
        ImportPolicy policy,
        bool remove_source,
        std::optional<std::uint64_t> expected_source_revision,
        std::optional<std::uint64_t> expected_destination_revision) override {
        return service_->migrateCollection(
            std::move(source), std::move(destination), context, policy, remove_source,
            expected_source_revision, expected_destination_revision);
    }
    [[nodiscard]] ExportResult exportCollection(
        const CollectionRef &ref,
        const AccessContext &context) const override {
        return service_->exportCollection(ref, context);
    }
    OperationResult importCollection(
        CollectionRef destination,
        std::string_view document,
        const AccessContext &context,
        ImportPolicy policy,
        std::optional<std::uint64_t> expected_revision) override {
        return service_->importCollection(
            std::move(destination), document, context, policy, expected_revision);
    }
    [[nodiscard]] ExternalMutationGateResult beforeExternalMutation(
        const DynamicPropertyOperation &operation,
        AccessContext context,
        bool cancellable) override {
        return service_->beforeExternalMutation(operation, std::move(context), cancellable);
    }
    void afterExternalMutation(
        const DynamicPropertyOperation &operation,
        const OperationResult &result,
        AccessContext context,
        std::string transaction_id) override {
        service_->afterExternalMutation(
            operation, result, std::move(context), std::move(transaction_id));
    }
    [[nodiscard]] DynamicPropertyCapabilities capabilities() const noexcept override {
        return service_->capabilities();
    }
    [[nodiscard]] std::string adapterName() const override {
        return service_->adapterName();
    }
    [[nodiscard]] std::shared_ptr<DynamicPropertyEventBus> eventBus() const noexcept override {
        return service_->eventBus();
    }
    [[nodiscard]] std::shared_ptr<IDynamicPropertyAuditSink> auditSink() const noexcept override {
        return service_->auditSink();
    }

private:
    std::shared_ptr<DynamicPropertyService> service_;
};

} // namespace endstone_dynamic_properties
