#include "endstone_dynamic_properties/bds_26_30_adapter.h"
#include "endstone_dynamic_properties/live_service.h"
#include "endstone_dynamic_properties/version.h"

#include <endstone/plugin/plugin.h>
#include <endstone/plugin/service_manager.h>
#include <endstone/plugin/service_priority.h>

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
        if (!service_->capabilities().completeControl()) {
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
        getLogger().info(
            std::string("Dynamic Properties API ") + ENDSTONE_DYNAMIC_PROPERTIES_VERSION +
            " registered complete service " +
            std::string(endstone_dynamic_properties::DynamicPropertyServiceName) +
            " using " + service_->adapterName());
#endif
    }

    void onDisable() override {
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

ENDSTONE_PLUGIN(
    "dynamic_properties_api",
    ENDSTONE_DYNAMIC_PROPERTIES_VERSION,
    DynamicPropertiesApiPlugin) {
    prefix = "DynamicPropertiesAPI";
    description = "Exact-build complete Dynamic Properties API for Endstone";
    website = "https://github.com/TheNINJALLO/endstone-dynamic-properties-api";
    authors = {"Ninj-OS contributors"};
}
