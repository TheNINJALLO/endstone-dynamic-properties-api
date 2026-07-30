cmake_minimum_required(VERSION 3.20)
project(endstone_dynamic_properties_consumer LANGUAGES CXX)

find_package(EndstoneDynamicProperties 0.1 CONFIG REQUIRED)

add_executable(endstone_dynamic_properties_consumer main.cpp)
target_link_libraries(endstone_dynamic_properties_consumer PRIVATE
    EndstoneDynamicProperties::core)

enable_testing()
add_test(NAME installed_package_smoke
    COMMAND endstone_dynamic_properties_consumer)
