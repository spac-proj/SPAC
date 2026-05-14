#include "switch_top.hpp"
#include "common.hpp"
#include "rx_engine.hpp"
#include "hash_engine.hpp"
#include "scheduler.hpp"
#include <pthread.h>
#include <stdio.h>

void rx_wrapper(
    axis_strm rx[NUM_PORTS],
    axis_strmi data_after_rx[NUM_PORTS],
    meta_strm meta_after_rx[NUM_PORTS],
    ap_uint<1> reset_ctrl
) {
#pragma HLS PIPELINE II=1
#pragma HLS INLINE off
    for (int sp = 0; sp < NUM_PORTS; sp++) { // src port
#pragma HLS UNROLL
        rx_engine(sp, rx[sp], data_after_rx[sp], meta_after_rx[sp], reset_ctrl);
    }
}

void hash_wrapper(                      // hash can not parallelized
    meta_strm meta_after_rx[NUM_PORTS], 
    meta_strm meta_after_hash[NUM_PORTS],  
    ap_uint<1> reset_ctrl
) {
    #pragma HLS INLINE
    if constexpr(HASH_MODULE_TYPE == HashModuleType::MultiBankHash) {
        multi_bank_hash(meta_after_rx, meta_after_hash, reset_ctrl);
    } else if constexpr(HASH_MODULE_TYPE == HashModuleType::FullLookupTable) {
        full_lookup_table(meta_after_rx, meta_after_hash, reset_ctrl);
    }
}

void scheduler_wrapper(
    axis_strmi data_after_rx[NUM_PORTS],
    meta_strm meta_after_hash[NUM_PORTS],
    axis_strm tx[NUM_PORTS],
    ap_uint<1> reset_ctrl
) {
    #pragma HLS INLINE
    if constexpr(SCHEDULER_TYPE == SchedulerType::iSLIP) {
        scheduler_iSLIP(data_after_rx, meta_after_hash, tx, reset_ctrl);
    } else if constexpr(BUFFER_TYPE == BufferType::NBuffersPerPort) {
        scheduler_nb1p(data_after_rx, meta_after_hash, tx, reset_ctrl);
    } else if constexpr(BUFFER_TYPE == BufferType::OneBufferPerPort) {
        scheduler(data_after_rx, meta_after_hash, tx, reset_ctrl);
    }
}

void switch_top(
    axis_strm rx[NUM_PORTS],      
    axis_strm tx[NUM_PORTS],      
    ap_uint<1> reset_ctrl         
) {
    #pragma HLS DATAFLOW 
    #pragma HLS array_partition variable=rx complete dim=1
    #pragma HLS array_partition variable=tx complete dim=1
    #pragma HLS INTERFACE axis port=rx
    #pragma HLS INTERFACE axis port=tx 
 

    axis_strmi data_after_rx[NUM_PORTS];
    meta_strm meta_after_rx[NUM_PORTS]; 
    meta_strm meta_after_hash[NUM_PORTS];
#pragma HLS STREAM variable=data_after_rx depth=64
#pragma HLS STREAM variable=meta_after_rx depth=64
#pragma HLS STREAM variable=meta_after_hash depth=64
#pragma HLS array_partition variable=data_after_rx complete dim=1
#pragma HLS array_partition variable=meta_after_rx complete dim=1
#pragma HLS array_partition variable=meta_after_hash complete dim=1


    // purely for RTL test:
    // for (int i = 0; i < NUM_PORTS; i++) {
    //     if (!rx[i].empty()) {
    //         axis_word tmp;
    //         rx[i].read(tmp);
    //         tx[i].write((axis_word)tmp);
    //     }
    // }

    // receive engine, put total_len, src addr, dst addr, src port in meta info
    rx_wrapper(rx, data_after_rx, meta_after_rx, reset_ctrl);

    // purely for RTL test:
    // for (int i = 0; i < NUM_PORTS; i++) {
    //     if (!meta_after_rx[i].empty() && !data_after_rx[i].empty()) {
    //         axis_wordi tmp;
    //         data_after_rx[i].read(tmp);
    //         tx[i].write((axis_word)tmp);
    //     }
    // }

    // hash engine, save (src addr, src port) mapping, query dst port based on dst, not unroll as share fwd_table
    hash_wrapper(meta_after_rx, meta_after_hash, reset_ctrl);

    // voq write, schedule and send data
    

    scheduler_wrapper(data_after_rx, meta_after_hash, tx, reset_ctrl);
}