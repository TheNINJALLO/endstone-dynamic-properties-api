#pragma once

#include "endstone_dynamic_properties/events.h"

#include <memory>
#include <mutex>
#include <string>
#include <vector>

namespace endstone_dynamic_properties {

struct DynamicPropertyAuditRecord {
    std::string transaction_id;
    std::string operation_name;
    AccessContext actor;
    DynamicPropertyStatus status{DynamicPropertyStatus::AdapterError};
    std::string message;
    std::vector<CollectionSnapshot> before;
    std::vector<CollectionSnapshot> after;
    bool external{};
    bool rolled_back{};
};

class IDynamicPropertyAuditSink {
public:
    virtual ~IDynamicPropertyAuditSink() = default;
    virtual void record(DynamicPropertyAuditRecord record) = 0;
};

class VectorAuditSink final : public IDynamicPropertyAuditSink {
public:
    void record(DynamicPropertyAuditRecord record) override;
    [[nodiscard]] std::vector<DynamicPropertyAuditRecord> records() const;
    void clear();

private:
    mutable std::mutex mutex_;
    std::vector<DynamicPropertyAuditRecord> records_;
};

} // namespace endstone_dynamic_properties
