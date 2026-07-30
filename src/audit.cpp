#include "endstone_dynamic_properties/audit.h"

namespace endstone_dynamic_properties {

void VectorAuditSink::record(DynamicPropertyAuditRecord record) {
    std::lock_guard lock(mutex_);
    records_.push_back(std::move(record));
}

std::vector<DynamicPropertyAuditRecord> VectorAuditSink::records() const {
    std::lock_guard lock(mutex_);
    return records_;
}

void VectorAuditSink::clear() {
    std::lock_guard lock(mutex_);
    records_.clear();
}

} // namespace endstone_dynamic_properties
