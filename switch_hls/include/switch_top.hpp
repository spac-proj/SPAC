#pragma once
#include "common.hpp"

// Top layer function, entry point
void switch_top(
    axis_strm rx[NUM_PORTS],      // Input ports from 8 AXI-Stream
    axis_strm tx[NUM_PORTS],      // Output ports to 8 AXI-Stream
    ap_uint<1> reset_ctrl         // Reset signal
);

