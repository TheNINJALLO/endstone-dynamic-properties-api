#include "endstone_dynamic_properties/bds_26_30_adapter.h"
#include "endstone_dynamic_properties/live_service.h"
#include "endstone_dynamic_properties/version.h"

#include <endstone/plugin/plugin.h>
#include <endstone/plugin/service_manager.h>
#include <endstone/plugin/service_priority.h>

#include <algorithm>
#include <cstring>
#include <memory>
#include <string>

class DynamicPropertiesApiPlugin : public endstone::Plugin {
public:
    void onEnable() override {
#if !ENDSTONE_DYNAMIC_PROPERTIES_NATIVE_2630
        getLogger().error("Dynamic Properties API package contains no BDS 26.30 native boundary");
        return;
#else
        adapter_ = endstone_dynamic_properties::makeBds2633DynamicPropertyAdapter(getServer());
        if (!adapter_) {
            getLogger().error("Dynamic Properties API could not create its guarded native adapter");
            return;
        }

        service_ = std::make_shared<endstone_dynamic_properties::DynamicPropertyService>(adapter_);
#if ENDSTONE_DYNAMIC_PROPERTIES_EXPERIMENTAL_LIVE_2633 && defined(__linux__)
        endstone_dynamic_properties::bindExperimentalLiveBds2633Service(service_);
#endif
        const auto capabilities = service_->capabilities();
        if (!capabilities.completeControl() &&
            !endstone_dynamic_properties::hasExperimentalLiveControl(capabilities)) {
            const auto report =
                endstone_dynamic_properties::inspectBds2633DynamicPropertyActivation(getServer());
            std::string message =
                "Dynamic Properties API refused to register endstone:dynamic-properties:v1 "
                "because the complete live + stored control contract is not verified";
            if (!report.failures.empty()) {
                message += ": ";
                for (std::size_t index = 0; index < report.failures.size(); ++index) {
                    if (index != 0) message += ", ";
                    message += report.failures[index];
                }
            }
            getLogger().error(message);
            service_.reset();
            adapter_.reset();
            return;
        }

        provider_ = std::make_shared<
            endstone_dynamic_properties::LiveDynamicPropertyServiceProvider>(service_);
        getServer().getServiceManager().registerService(
            std::string(endstone_dynamic_properties::DynamicPropertyServiceName),
            provider_,
            *this,
            endstone::ServicePriority::Normal);
        const auto mode = capabilities.completeControl()
            ? "complete-control"
            : "experimental live world-only";
        getLogger().info(
            std::string("Dynamic Properties API ") + ENDSTONE_DYNAMIC_PROPERTIES_VERSION +
            " registered " + mode + " service " +
            std::string(endstone_dynamic_properties::DynamicPropertyServiceName) +
            " using " + service_->adapterName());
#endif
    }

    void onDisable() override {
#if ENDSTONE_DYNAMIC_PROPERTIES_EXPERIMENTAL_LIVE_2633 && defined(__linux__)
        endstone_dynamic_properties::unbindExperimentalLiveBds2633Service();
#endif
        getServer().getServiceManager().unregisterAll(*this);
        provider_.reset();
        service_.reset();
        adapter_.reset();
    }

private:
    std::shared_ptr<endstone_dynamic_properties::IDynamicPropertyAdapter> adapter_;
    std::shared_ptr<endstone_dynamic_properties::DynamicPropertyService> service_;
    std::shared_ptr<endstone_dynamic_properties::LiveDynamicPropertyServiceProvider> provider_;
};

#if ENDSTONE_DYNAMIC_PROPERTIES_EXPERIMENTAL_LIVE_2633 && defined(__linux__)
extern "C" __attribute__((visibility("default"))) int
endstone_dynamic_properties_probe_external_hooks_v1(
    const char *world_id,
    const char *collection,
    const char *key_prefix,
    endstone_dynamic_properties::ExperimentalExternalHookProbeWireResult *wire) {
    using namespace endstone_dynamic_properties;
    if (!world_id || !collection || !key_prefix || !wire) return 0;
    *wire = {};
    wire->struct_size = sizeof(*wire);
    const auto result = probeExperimentalLiveBds2633ExternalHooks(
        CollectionRef{DynamicPropertyTarget::world(world_id), collection}, key_prefix);
    wire->available = result.available;
    wire->set_intercepted = result.set_intercepted;
    wire->remove_intercepted = result.remove_intercepted;
    wire->clear_intercepted = result.clear_intercepted;
    wire->cancellation_blocked = result.cancellation_blocked;
    wire->cleanup_confirmed = result.cleanup_confirmed;
    const auto message_size = std::min(result.message.size(), sizeof(wire->message) - 1);
    std::memcpy(wire->message, result.message.data(), message_size);
    wire->message[message_size] = '\0';
    return result.ok() ? 1 : 0;
}
#endif

ENDSTONE_PLUGIN(
    "dynamic_properties_api",
    ENDSTONE_DYNAMIC_PROPERTIES_VERSION,
    DynamicPropertiesApiPlugin) {
    prefix = "DynamicPropertiesAPI";
    description = "Exact-build complete Dynamic Properties API for Endstone";
    website = "https://github.com/TheNINJALLO/endstone-dynamic-properties-api";
    authors = {"Ninj-OS contributors"};
}
