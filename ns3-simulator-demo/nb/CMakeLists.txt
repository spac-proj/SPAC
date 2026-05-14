set(CMAKE_DISABLE_PRECOMPILE_HEADERS ON)
check_include_file_cxx(stdint.h HAVE_STDINT_H)
if(HAVE_STDINT_H)
    add_definitions(-DHAVE_STDINT_H)
endif()

set(examples_as_tests_sources)
if(${ENABLE_EXAMPLES})
    set(examples_as_tests_sources
        #test/nb-examples-test-suite.cc
        )
endif()
# build_lib(
#     LIBNAME nb
#     SOURCE_FILES model/shrunk-header.cc
#                  model/shrunk-app.cc
#                  helper/shrunk-helper.cc
#                  model/simple-shrunk-net-device.cc
#                  helper/shrunk-device-helper.cc 
#     HEADER_FILES model/shrunk-header.h
#                  model/shrunk-app.h
#                  helper/shrunk-helper.h
#                  model/simple-shrunk-net-device.h
#                 helper/shrunk-device-helper.h
#     LIBRARIES_TO_LINK 
#                 ${libcore}
#                 ${libnetwork}     
#                 ${libpoint-to-point}
#                 ${libapplications} 
#                 ${libinternet} 
#                 ${libmobility}    
#     TEST_SOURCES test/shrunk-test-suite.cc
#                  ${examples_as_tests_sources}
# )

build_lib(
    LIBNAME nb
    SOURCE_FILES
        model/nb_runtime.cc
        model/nb_simple.c
        model/nb_timer.cc
        model/nb_ns3_transport.cc
        model/nb-app.cc
        model/nb-app-client.cc
        model/nb-app-server.cc
        model/nb-csma-net-device.cc
        model/nb-csma-channel.cc
        model/nb-p2p-net-device.cc
        model/nb-p2p-channel.cc
        model/nb-stack.cc
        model/nb-timer-manager.cc
        model/backoff.cc
        model/nb-csma-switch-stack.cc
        model/nb-p2p-switch-stack.cc
        model/nb-csma-switch-port-device.cc
        model/nb-p2p-switch-port-device.cc
        helper/nb-csma-helper.cc
        helper/nb-p2p-helper.cc
    HEADER_FILES
        model/nb_runtime.h
        model/nb_timer.h
        model/nb-app.h
        model/nb-app-client.h
        model/nb-app-server.h
        model/nb-csma-net-device.h
        model/nb-csma-channel.h
        model/nb-p2p-net-device.h
        model/nb-p2p-channel.h
        model/nb-stack.h
        model/nb-timer-manager.h
        model/backoff.h
        model/gen_headers.h
        model/nb_data_queue.h
        model/nb-csma-switch-stack.h
        model/nb-p2p-switch-stack.h
        model/nb-csma-switch-port-device.h
        model/nb-p2p-switch-port-device.h
        helper/nb-csma-helper.h
        helper/nb-p2p-helper.h
    LIBRARIES_TO_LINK
        ${libcore}
        ${libnetwork}
        ${libapplications}
        ${libinternet}
        ${libmobility}
    TEST_SOURCES
        test/nb-test-suite.cc
        ${examples_as_tests_sources}
)