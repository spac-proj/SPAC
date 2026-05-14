#pragma once
#include "common.hpp"
// Hash functions for forwarding table
// void hash_engine(
//     ap_uint<utils::req_bits(NUM_PORTS)> src_port,
//     meta_strm &meta_in,
//     meta_strm &meta_out,
//     ap_uint<1> reset_ctrl
// );
void multi_bank_hash(
    meta_strm meta_in[NUM_PORTS],
    meta_strm meta_out[NUM_PORTS],
    ap_uint<1> reset_ctrl
);

void full_lookup_table(
    meta_strm meta_in[NUM_PORTS],
    meta_strm meta_out[NUM_PORTS],
    ap_uint<1> reset_ctrl
);