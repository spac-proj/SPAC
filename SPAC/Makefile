# ---------------------------------------------------------------------------
# SPAC DSL build.
#
# Targets:
#   make           - build libspac.a and demo binaries
#   make demo      - build only the bundled demo binaries
#   make clean     - wipe build output
# ---------------------------------------------------------------------------

CXX        ?= g++
AR         ?= ar
CXXSTD     ?= -std=c++17
CXXFLAGS   ?= -O2 -Wall -Wextra -Wno-unused-parameter -fPIC
SPAC_ROOT  := $(abspath .)
HLS_ROOT   := $(abspath ../switch_hls)
NB_ROOT    := $(abspath ../net-blocks)

INCLUDES   := -I$(SPAC_ROOT)/include
DEFINES    := -DSPAC_HLS_ROOT=\"$(HLS_ROOT)\" \
              -DSPAC_NETBLOCKS_ROOT=\"$(NB_ROOT)\"

BUILD_DIR  := build
OBJ_DIR    := $(BUILD_DIR)/obj

LIB        := $(BUILD_DIR)/libspac.a
EXAMPLES_DIR := examples
DEMO_BIN   := $(BUILD_DIR)/demo_clean
DEMO_RR    := $(BUILD_DIR)/demo_rr

# ---------- Sources ---------------------------------------------------------
SRCS := \
    src/registry.cpp \
    src/layout.cpp \
    src/switch_config.cpp \
    src/binding.cpp \
    src/compile_lib.cpp \
    src/codegen/impl_cpp.cpp \
    src/codegen/packet_hpp.cpp \
    src/codegen/hls_copy.cpp \
    src/codegen/netblocks.cpp

OBJS := $(SRCS:%.cpp=$(OBJ_DIR)/%.o)

DEPS := $(OBJS:.o=.d)

# ---------- Targets ---------------------------------------------------------
.PHONY: all demo clean
all: $(LIB) demo

demo: $(DEMO_BIN) $(DEMO_RR)

$(LIB): $(OBJS)
	@mkdir -p $(@D)
	$(AR) rcs $@ $^

$(BUILD_DIR)/%: $(EXAMPLES_DIR)/%.cpp $(LIB)
	@mkdir -p $(@D)
	$(CXX) $(CXXSTD) $(CXXFLAGS) $(INCLUDES) $(DEFINES) \
	    $< -o $@ -L$(BUILD_DIR) -lspac -lstdc++fs

$(OBJ_DIR)/%.o: %.cpp
	@mkdir -p $(@D)
	$(CXX) $(CXXSTD) $(CXXFLAGS) $(INCLUDES) $(DEFINES) -MMD -MP -c $< -o $@

clean:
	rm -rf $(BUILD_DIR)

-include $(DEPS)
