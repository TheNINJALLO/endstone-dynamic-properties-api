#include "endstone_dynamic_properties/bds_26_30_adapter.h"

#include "endstone_dynamic_properties/generated/native_manifest_data.h"
#include "endstone_dynamic_properties/native_binary_identity.h"
#include "endstone_dynamic_properties/native_manifest.h"

#include <endstone/server.h>

#include <algorithm>
#include <cctype>
#include <memory>
#include <string>
#include <string_view>
#include <utility>

#ifndef ENDSTONE_DYNAMIC_PROPERTIES_VERIFIED_NATIVE_BRIDGE
#define ENDSTONE_DYNAMIC_PROPERTIES_VERIFIED_NATIVE_BRIDGE 0
#endif
#ifndef ENDSTONE_DYNAMIC_PROPERTIES_EXPERIMENTAL_LIVE_2633
#define ENDSTONE_DYNAMIC_PROPERTIES_EXPERIMENTAL_LIVE_2633 0
#endif

namespace endstone_dynamic_properties {

#if ENDSTONE_DYNAMIC_PROPERTIES_VERIFIED_NATIVE_BRIDGE
// Implemented by the generated, stage-verified translation unit.  This must
// have external linkage: declaring it in the anonymous namespace makes an
// otherwise valid generated bridge impossible to link.
std::shared_ptr<IDynamicPropertyAdapter> makeVerifiedBds2633DynamicPropertyAdapter(
    endstone::Server &server);
#endif
#if ENDSTONE_DYNAMIC_PROPERTIES_EXPERIMENTAL_LIVE_2633 && defined(__linux__)
std::shared_ptr<IDynamicPropertyAdapter> makeExperimentalLiveBds2633DynamicPropertyAdapter(
    endstone::Server &server);
#endif

namespace {

std::string_view canonicalBdsBuild(std::string_view build) noexcept {
    if (build.starts_with("1.")) build.remove_prefix(2);
    if (build == "26.33.1") return "26.33";
    return build;
}

bool validIdentifierList(std::string_view value) noexcept {
    if (value.empty() || value.front() == '.' || value.back() == '.') return false;
    bool previous_dot = false;
    for (const char current : value) {
        if (current == '.') {
            if (previous_dot) return false;
            previous_dot = true;
            continue;
        }
        if (!std::isalnum(static_cast<unsigned char>(current)) && current != '-') return false;
        previous_dot = false;
    }
    return true;
}

bool expectedEndstoneVersion(std::string_view runtime) noexcept {
    constexpr std::string_view Expected = "0.11.6";
    if (runtime.starts_with('v')) runtime.remove_prefix(1);
    if (runtime == Expected) return true;
    if (!runtime.starts_with(Expected)) return false;
    auto suffix = runtime.substr(Expected.size());
    if (suffix.starts_with('+')) return validIdentifierList(suffix.substr(1));
    if (suffix.starts_with(".dev")) {
        suffix.remove_prefix(4);
        const auto metadata = suffix.find('+');
        const auto serial = suffix.substr(0, metadata);
        if (serial.empty() || !std::ranges::all_of(serial, [](char c) {
                return c >= '0' && c <= '9';
            })) {
            return false;
        }
        return metadata == std::string_view::npos ||
               validIdentifierList(suffix.substr(metadata + 1));
    }
    if (suffix.starts_with("-dev")) {
        suffix.remove_prefix(4);
        if (suffix.empty()) return true;
        if (suffix.starts_with('+')) return validIdentifierList(suffix.substr(1));
        if (!suffix.starts_with('.')) return false;
        suffix.remove_prefix(1);
        const auto metadata = suffix.find('+');
        const auto prerelease = suffix.substr(0, metadata);
        return validIdentifierList(prerelease) &&
               (metadata == std::string_view::npos ||
                validIdentifierList(suffix.substr(metadata + 1)));
    }
    return false;
}

const RuntimeExecutableIdentity &currentProcessExecutableIdentity() {
    // Hashing the 200+ MB server executable on every status command stalls the
    // server thread.  The process image cannot change during this process, so
    // bind it once on first activation inspection and reuse that evidence.
    static const RuntimeExecutableIdentity Identity = inspectCurrentProcessExecutable();
    return Identity;
}

class GuardedBds2633DynamicPropertyAdapter final : public IDynamicPropertyAdapter {
public:
    explicit GuardedBds2633DynamicPropertyAdapter(NativeActivationReport report)
        : report_(std::move(report)) {}

    [[nodiscard]] std::string_view name() const noexcept override {
        if (!report_.runtime_version_match || !report_.endstone_version_match)
            return "bds-1.26.33.1-dynamic-properties-runtime-mismatch";
        if (!report_.executable_hash_match)
            return "bds-1.26.33.1-dynamic-properties-binary-identity-gate";
        return "bds-1.26.33.1-dynamic-properties-complete-control-gate-closed";
    }

    [[nodiscard]] DynamicPropertyCapabilities capabilities() const noexcept override {
        DynamicPropertyCapabilities caps;
        caps.exact_build_match =
            report_.runtime_version_match && report_.endstone_version_match;
        caps.exact_binary_hash_match = report_.executable_hash_match;
        caps.symbols_validated = report_.symbols_validated;
        caps.stage_probe_passed = report_.stage_probe_passed;
        return caps;
    }

    [[nodiscard]] CaptureResult capture(const CollectionRef &) override {
        const auto result = closedResult();
        return {result.status, result.message, std::nullopt};
    }

    [[nodiscard]] ListCollectionsResult listCollections(
        const DynamicPropertyTarget &) override {
        const auto result = closedResult();
        return {result.status, result.message, {}};
    }

    OperationResult apply(const DynamicPropertyOperation &, bool) override {
        return closedResult();
    }

    TransactionResult transact(const DynamicPropertyTransaction &) override {
        const auto result = closedResult();
        return {
            result.status,
            result.message,
            {result},
            false,
            {},
        };
    }

    OperationResult flush(const DynamicPropertyTarget &) override {
        return closedResult();
    }

private:
    [[nodiscard]] OperationResult closedResult() const {
        if (!report_.runtime_version_match || !report_.endstone_version_match) {
            return {
                DynamicPropertyStatus::RuntimeMismatch,
                "Dynamic Properties API requires BDS package 1.26.33.1/runtime 26.33 "
                "with Endstone 0.11.6",
                {},
                {},
                0,
            };
        }
        if (!report_.executable_hash_match) {
            return {
                DynamicPropertyStatus::BinaryIdentityMismatch,
                "the running BDS executable does not match the activated platform manifest",
                {},
                {},
                0,
            };
        }
        std::string message =
            "complete dynamic-property control is disabled until live, offline, stored, "
            "block and external-hook validation all pass";
        if (!report_.failures.empty()) {
            message += ": ";
            for (std::size_t index = 0; index < report_.failures.size(); ++index) {
                if (index != 0) message += ", ";
                message += report_.failures[index];
            }
        }
        return {
            DynamicPropertyStatus::SymbolValidationFailed,
            std::move(message),
            {},
            {},
            0,
        };
    }

    NativeActivationReport report_;
};

} // namespace

NativeActivationReport inspectBds2633DynamicPropertyActivation(endstone::Server &server) {
    NativeActivationReport report;
    report.runtime_version_match =
        canonicalBdsBuild(server.getMinecraftVersion()) == generated::RuntimeBds;
    report.endstone_version_match = expectedEndstoneVersion(server.getVersion());
    report.manifest_activated = generated::NativeManifestActivated;
    report.symbols_validated = generated::SymbolsValidated;
    report.storage_contracts_validated = generated::StorageContractsValidated;
    report.external_hooks_validated = generated::ExternalHooksValidated;
    report.stage_probe_passed = generated::StageProbePassed;
    report.verified_bridge_compiled =
        ENDSTONE_DYNAMIC_PROPERTIES_VERIFIED_NATIVE_BRIDGE != 0;

    if (!generated::ExecutableSha256.empty() && generated::ExecutableSize != 0) {
        const auto &identity = currentProcessExecutableIdentity();
        report.executable_hash_match =
            identity.ok() && identity.size == generated::ExecutableSize &&
            identity.sha256 == generated::ExecutableSha256;
        if (!identity.ok()) {
            report.failures.emplace_back(
                "runtime executable identity failed: " + identity.error);
        }
    }

    if (!report.runtime_version_match)
        report.failures.emplace_back("BDS runtime version mismatch");
    if (!report.endstone_version_match)
        report.failures.emplace_back("Endstone runtime version mismatch");
    if (!report.manifest_activated)
        report.failures.emplace_back("platform manifest is not activated");
    if (!report.executable_hash_match)
        report.failures.emplace_back("executable SHA-256/size mismatch");
    if (!report.symbols_validated)
        report.failures.emplace_back("native symbols are not behavior-verified");
    if (!report.storage_contracts_validated)
        report.failures.emplace_back("offline/stored target contracts are incomplete");
    if (!report.external_hooks_validated)
        report.failures.emplace_back("external mutation hooks are incomplete");
    if (!report.stage_probe_passed)
        report.failures.emplace_back("complete-control stage probe has not passed");
    if (!report.verified_bridge_compiled)
        report.failures.emplace_back("verified native bridge is not compiled");
    return report;
}

std::shared_ptr<IDynamicPropertyAdapter> makeBds2633DynamicPropertyAdapter(
    endstone::Server &server) {
    auto report = inspectBds2633DynamicPropertyActivation(server);
#if ENDSTONE_DYNAMIC_PROPERTIES_VERIFIED_NATIVE_BRIDGE
    if (report.complete()) return makeVerifiedBds2633DynamicPropertyAdapter(server);
#endif
#if ENDSTONE_DYNAMIC_PROPERTIES_EXPERIMENTAL_LIVE_2633 && defined(__linux__)
    if (report.runtime_version_match && report.endstone_version_match &&
        report.executable_hash_match) {
        return makeExperimentalLiveBds2633DynamicPropertyAdapter(server);
    }
#endif
    return std::make_shared<GuardedBds2633DynamicPropertyAdapter>(std::move(report));
}

bool hasExperimentalLiveControl(
    const DynamicPropertyCapabilities &capabilities) noexcept {
    return capabilities.world && capabilities.online_players &&
           capabilities.loaded_entities && capabilities.read && capabilities.write &&
           capabilities.remove && capabilities.clear && capabilities.list_ids &&
           capabilities.list_collections && capabilities.byte_count &&
           capabilities.bulk_set && capabilities.collection_rename &&
           capabilities.property_copy_move && capabilities.collection_copy_move &&
           capabilities.collection_migration && capabilities.export_import &&
           capabilities.atomic_transactions && capabilities.rollback &&
           capabilities.persistence_flush && capabilities.exact_build_match &&
           capabilities.exact_binary_hash_match && capabilities.symbols_validated;
}

} // namespace endstone_dynamic_properties
