#pragma once

#include "endstone_dynamic_properties/adapter.h"

#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace endstone {
class Server;
}

namespace endstone_dynamic_properties {

class DynamicPropertyService;

struct ExperimentalExternalHookProbeResult {
    bool available{};
    bool set_intercepted{};
    bool remove_intercepted{};
    bool clear_intercepted{};
    bool cancellation_blocked{};
    bool cleanup_confirmed{};
    std::string message;

    [[nodiscard]] bool ok() const noexcept {
        return available && set_intercepted && remove_intercepted &&
               clear_intercepted && cancellation_blocked && cleanup_confirmed;
    }
};

inline constexpr char ExperimentalExternalHookProbeSymbol[] =
    "endstone_dynamic_properties_probe_external_hooks_v1";

struct ExperimentalExternalHookProbeWireResult {
    std::uint32_t struct_size{};
    std::uint32_t available{};
    std::uint32_t set_intercepted{};
    std::uint32_t remove_intercepted{};
    std::uint32_t clear_intercepted{};
    std::uint32_t cancellation_blocked{};
    std::uint32_t cleanup_confirmed{};
    char message[256]{};
};

using ExperimentalExternalHookProbeFunction = int (*)(
    const char *world_id,
    const char *collection,
    const char *key_prefix,
    ExperimentalExternalHookProbeWireResult *result);

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

// The experimental adapter deliberately exposes only capabilities backed by
// the exact 1.26.33.1 Linux binary. A world-only subset is operational live;
// callers must still inspect every target capability before dispatch. It is
// never constructed on an identity/runtime mismatch and never makes the
// complete-control claim used by a verified release.
[[nodiscard]] bool hasExperimentalLiveControl(
    const DynamicPropertyCapabilities &capabilities) noexcept;
void bindExperimentalLiveBds2633Service(
    std::shared_ptr<DynamicPropertyService> service);
void unbindExperimentalLiveBds2633Service() noexcept;
[[nodiscard]] ExperimentalExternalHookProbeResult
probeExperimentalLiveBds2633ExternalHooks(
    const CollectionRef &ref,
    std::string key_prefix);

} // namespace endstone_dynamic_properties
