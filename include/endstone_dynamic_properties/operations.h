#pragma once

#include "endstone_dynamic_properties/snapshot.h"

#include <cstdint>
#include <optional>
#include <string>
#include <variant>
#include <vector>

namespace endstone_dynamic_properties {

struct SetPropertyOperation {
    CollectionRef ref;
    std::string key;
    DynamicPropertyValue value;
    std::optional<std::uint64_t> expected_revision;
};

struct SetManyOperation {
    CollectionRef ref;
    DynamicPropertyMap values;
    std::optional<std::uint64_t> expected_revision;
};

struct RemovePropertyOperation {
    CollectionRef ref;
    std::string key;
    std::optional<std::uint64_t> expected_revision;
    bool require_existing{};
};

struct RemoveManyOperation {
    CollectionRef ref;
    std::vector<std::string> keys;
    std::optional<std::uint64_t> expected_revision;
    bool require_all_existing{};
};

struct ClearCollectionOperation {
    CollectionRef ref;
    std::optional<std::uint64_t> expected_revision;
    bool remove_collection{};
};

struct RenameCollectionOperation {
    DynamicPropertyTarget target;
    std::string from;
    std::string to;
    std::optional<std::uint64_t> expected_source_revision;
    ImportPolicy destination_policy{ImportPolicy::FailIfDestinationExists};
    // Appended after destination_policy to preserve the original aggregate
    // initializer order for existing alpha consumers.
    std::optional<std::uint64_t> expected_destination_revision;
};

struct TransferPropertyOperation {
    CollectionRef source;
    std::string source_key;
    CollectionRef destination;
    std::string destination_key;
    std::optional<std::uint64_t> expected_source_revision;
    std::optional<std::uint64_t> expected_destination_revision;
    bool remove_source{};
    bool overwrite{};
};

struct TransferCollectionOperation {
    CollectionRef source;
    CollectionRef destination;
    std::optional<std::uint64_t> expected_source_revision;
    std::optional<std::uint64_t> expected_destination_revision;
    ImportPolicy destination_policy{ImportPolicy::FailIfDestinationExists};
    bool remove_source{};
};

struct ImportCollectionOperation {
    CollectionRef destination;
    DynamicPropertyMap properties;
    std::optional<std::uint64_t> expected_destination_revision;
    ImportPolicy policy{ImportPolicy::Merge};
};

using DynamicPropertyOperation = std::variant<
    SetPropertyOperation,
    SetManyOperation,
    RemovePropertyOperation,
    RemoveManyOperation,
    ClearCollectionOperation,
    RenameCollectionOperation,
    TransferPropertyOperation,
    TransferCollectionOperation,
    ImportCollectionOperation>;

struct OperationResult {
    DynamicPropertyStatus status{DynamicPropertyStatus::AdapterError};
    std::string message;
    std::vector<CollectionSnapshot> before;
    std::vector<CollectionSnapshot> after;
    std::uint64_t resulting_revision{};
    [[nodiscard]] bool ok() const noexcept {
        return status == DynamicPropertyStatus::Applied;
    }
};

struct DynamicPropertyTransaction {
    std::vector<DynamicPropertyOperation> operations;
    bool force{};
    bool rollback_on_failure{true};
    bool require_atomic{true};
    std::string audit_reason;
};

struct TransactionResult {
    DynamicPropertyStatus status{DynamicPropertyStatus::AdapterError};
    std::string message;
    std::vector<OperationResult> operation_results;
    bool rolled_back{};
    std::string transaction_id;
    [[nodiscard]] bool ok() const noexcept {
        return status == DynamicPropertyStatus::Applied;
    }
};

[[nodiscard]] std::string_view operationName(const DynamicPropertyOperation &operation) noexcept;
[[nodiscard]] std::vector<CollectionRef> operationCollections(
    const DynamicPropertyOperation &operation);

} // namespace endstone_dynamic_properties
