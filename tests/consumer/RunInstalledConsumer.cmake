cmake_minimum_required(VERSION 3.20)

foreach(required_variable
        PACKAGE_BUILD_DIR
        CONSUMER_SOURCE_DIR
        WORK_ROOT
        GENERATOR
        CTEST_COMMAND)
    if(NOT DEFINED ${required_variable} OR "${${required_variable}}" STREQUAL "")
        message(FATAL_ERROR "${required_variable} is required")
    endif()
endforeach()

cmake_path(SET normalized_package_build_dir NORMALIZE "${PACKAGE_BUILD_DIR}")
cmake_path(SET normalized_work_root NORMALIZE "${WORK_ROOT}")
cmake_path(IS_PREFIX normalized_package_build_dir "${normalized_work_root}"
    NORMALIZE work_root_is_in_build_tree)
if(NOT work_root_is_in_build_tree OR
   NOT normalized_work_root MATCHES "/_consumer(/|$)")
    message(FATAL_ERROR
        "Refusing to clean unexpected consumer test directory: ${WORK_ROOT}")
endif()

file(REMOVE_RECURSE "${WORK_ROOT}")
set(install_prefix "${WORK_ROOT}/install")
set(consumer_build_dir "${WORK_ROOT}/build")

set(install_command
    "${CMAKE_COMMAND}" --install "${PACKAGE_BUILD_DIR}"
    --prefix "${install_prefix}")
if(DEFINED CONFIG AND NOT CONFIG STREQUAL "")
    list(APPEND install_command --config "${CONFIG}")
endif()
execute_process(
    COMMAND ${install_command}
    RESULT_VARIABLE install_result
    OUTPUT_VARIABLE install_output
    ERROR_VARIABLE install_error
)
if(NOT install_result EQUAL 0)
    message(FATAL_ERROR
        "Package installation failed (${install_result}):\n${install_output}\n${install_error}")
endif()

set(configure_command
    "${CMAKE_COMMAND}"
    -S "${CONSUMER_SOURCE_DIR}"
    -B "${consumer_build_dir}"
    -G "${GENERATOR}"
    "-DCMAKE_PREFIX_PATH=${install_prefix}"
)
if(DEFINED GENERATOR_PLATFORM AND NOT GENERATOR_PLATFORM STREQUAL "")
    list(APPEND configure_command -A "${GENERATOR_PLATFORM}")
endif()
if(DEFINED GENERATOR_TOOLSET AND NOT GENERATOR_TOOLSET STREQUAL "")
    list(APPEND configure_command -T "${GENERATOR_TOOLSET}")
endif()
if(NOT MULTI_CONFIG AND DEFINED CONFIG AND NOT CONFIG STREQUAL "")
    list(APPEND configure_command "-DCMAKE_BUILD_TYPE=${CONFIG}")
endif()
execute_process(
    COMMAND ${configure_command}
    RESULT_VARIABLE configure_result
    OUTPUT_VARIABLE configure_output
    ERROR_VARIABLE configure_error
)
if(NOT configure_result EQUAL 0)
    message(FATAL_ERROR
        "Consumer configuration failed (${configure_result}):\n${configure_output}\n${configure_error}")
endif()

set(build_command
    "${CMAKE_COMMAND}" --build "${consumer_build_dir}" --parallel)
if(DEFINED CONFIG AND NOT CONFIG STREQUAL "")
    list(APPEND build_command --config "${CONFIG}")
endif()
execute_process(
    COMMAND ${build_command}
    RESULT_VARIABLE build_result
    OUTPUT_VARIABLE build_output
    ERROR_VARIABLE build_error
)
if(NOT build_result EQUAL 0)
    message(FATAL_ERROR
        "Consumer build failed (${build_result}):\n${build_output}\n${build_error}")
endif()

set(test_command
    "${CTEST_COMMAND}" --test-dir "${consumer_build_dir}" --output-on-failure)
if(DEFINED CONFIG AND NOT CONFIG STREQUAL "")
    list(APPEND test_command -C "${CONFIG}")
endif()
execute_process(
    COMMAND ${test_command}
    RESULT_VARIABLE test_result
    OUTPUT_VARIABLE test_output
    ERROR_VARIABLE test_error
)
if(NOT test_result EQUAL 0)
    message(FATAL_ERROR
        "Consumer test failed (${test_result}):\n${test_output}\n${test_error}")
endif()

message(STATUS "Installed package consumer passed")
