#pragma once

#include "endstone_dynamic_properties/adapter.h"

#include <memory>
#include <string>
#include <vector>

namespace endstone {
class Server;
}

namespace endstone_dynamic_properties {

struct NativeActivationReport {
    bool runtime_version_match{};
    bool endstone_version_match{};
    bool executable_hash_match{};
    bool manifest_activated{};
    bool symbols_validated{};
    bool storage_contracts_validated{};
    bool external_hooks_validated{};
    bool stage_probe_passed{};
    bool verified_bridge_compiled{};
    std::vector<std::string> failures;

    [[nodiscard]] bool complete() const noexcept {
        return runtime_version_match && endstone_version_match && executable_hash_match &&
               manifest_activated && symbols_validated && storage_contracts_validated &&
               external_hooks_validated && stage_probe_passed && verified_bridge_compiled &&
               failures.empty();
    }
};

// Returns a guarded exact-build adapter. The service is never registered unless
// the complete live, stored, block and external-hook feature set has passed the
// exact-binary manifest and disposable-world validation matrix.
std::shared_ptr<IDynamicPropertyAdapter> makeBds2633DynamicPropertyAdapter(
    endstone::Server &server);
[[nodiscard]] NativeActivationReport inspectBds2633DynamicPropertyActivation(
    endstone::Server &server);

} // namespace endstone_dynamic_properties
