#include "endstone_dynamic_properties/operations.h"

#include <type_traits>

namespace endstone_dynamic_properties {

std::string_view operationName(const DynamicPropertyOperation &operation) noexcept {
    return std::visit([](const auto &entry) -> std::string_view {
        using T = std::decay_t<decltype(entry)>;
        if constexpr (std::is_same_v<T, SetPropertyOperation>) {
            return "set_property";
        } else if constexpr (std::is_same_v<T, SetManyOperation>) {
            return "set_many";
        } else if constexpr (std::is_same_v<T, RemovePropertyOperation>) {
            return "remove_property";
        } else if constexpr (std::is_same_v<T, RemoveManyOperation>) {
            return "remove_many";
        } else if constexpr (std::is_same_v<T, ClearCollectionOperation>) {
            return "clear_collection";
        } else if constexpr (std::is_same_v<T, RenameCollectionOperation>) {
            return "rename_collection";
        } else if constexpr (std::is_same_v<T, TransferPropertyOperation>) {
            return "transfer_property";
        } else if constexpr (std::is_same_v<T, TransferCollectionOperation>) {
            return "transfer_collection";
        } else {
            return "import_collection";
        }
    }, operation);
}

std::vector<CollectionRef> operationCollections(const DynamicPropertyOperation &operation) {
    return std::visit([](const auto &entry) -> std::vector<CollectionRef> {
        using T = std::decay_t<decltype(entry)>;
        if constexpr (std::is_same_v<T, RenameCollectionOperation>) {
            return {{entry.target, entry.from}, {entry.target, entry.to}};
        } else if constexpr (std::is_same_v<T, TransferPropertyOperation> ||
                             std::is_same_v<T, TransferCollectionOperation>) {
            return {entry.source, entry.destination};
        } else if constexpr (std::is_same_v<T, ImportCollectionOperation>) {
            return {entry.destination};
        } else {
            return {entry.ref};
        }
    }, operation);
}

} // namespace endstone_dynamic_properties
