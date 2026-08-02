#pragma once

#include <cstdint>
#include <string_view>

#ifndef ENDSTONE_DYNAMIC_PROPERTIES_VERSION
#define ENDSTONE_DYNAMIC_PROPERTIES_VERSION "0.1.0-alpha.3"
#endif

namespace endstone_dynamic_properties {

inline constexpr std::string_view ReleaseVersion = ENDSTONE_DYNAMIC_PROPERTIES_VERSION;
inline constexpr std::string_view ServiceName = "endstone:dynamic-properties:v1";
inline constexpr std::uint32_t ServiceAbiVersion = 1;
inline constexpr std::string_view TargetBdsPackage = "1.26.33.1";
inline constexpr std::string_view TargetBdsRuntime = "26.33";
inline constexpr std::string_view TargetEndstoneVersion = "0.11.6";

} // namespace endstone_dynamic_properties
