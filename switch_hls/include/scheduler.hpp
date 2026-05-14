#pragma once
#include "common.hpp"

void scheduler(
    axis_strmi data_after_rx[NUM_PORTS],
    meta_strm meta_after_hash[NUM_PORTS],
    axis_strm tx[NUM_PORTS],
    ap_uint<1> reset_ctrl
);

void scheduler_nb1p(
    axis_strmi data_after_rx[NUM_PORTS],
    meta_strm meta_after_hash[NUM_PORTS],
    axis_strm tx[NUM_PORTS],
    ap_uint<1> reset_ctrl
);

void scheduler_iSLIP(
    axis_strmi data_after_rx[NUM_PORTS],
    meta_strm meta_after_hash[NUM_PORTS],
    axis_strm tx[NUM_PORTS],
    ap_uint<1> reset_ctrl
);

enum digest_state_t {IDLE, PROCESSING_UNICAST, PROCESSING_BROADCAST};