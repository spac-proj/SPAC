build_lib_example(
    NAME nb-csma-example
    SOURCE_FILES nb-csma-example.cc
    LIBRARIES_TO_LINK ${libnb}
)
build_lib_example(
    NAME nb-csma-switch-example
    SOURCE_FILES nb-csma-switch-example.cc
    LIBRARIES_TO_LINK ${libnb}
)
build_lib_example(
    NAME nb-p2p-example
    SOURCE_FILES nb-p2p-example.cc
    LIBRARIES_TO_LINK ${libnb}
)
build_lib_example(
    NAME nb-p2p-switch-example
    SOURCE_FILES nb-p2p-switch-example.cc
    LIBRARIES_TO_LINK ${libnb}
)