#include <endstone_dynamic_properties/dynamic_properties_api.h>

#include <string_view>

int main() {
    using namespace endstone_dynamic_properties;

    const DynamicPropertyValue value = true;
    if (valueTypeName(value) != std::string_view{"bool"}) return 1;
    if (ServiceName != std::string_view{"endstone:dynamic-properties:v1"}) return 2;
    return 0;
}
