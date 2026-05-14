#pragma once
#include "common.hpp"

void rx_engine(
    ap_uint<utils::req_bits(NUM_PORTS)> src_port,
    axis_strm &data_in, 
    axis_strmi &data_out, 
    meta_strm &meta_out,
    ap_uint<1> reset_ctrl
);
