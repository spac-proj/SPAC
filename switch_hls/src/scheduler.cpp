#include "common.hpp"
#include "stdio.h"
#include "scheduler.hpp"
static axis_wordi data_buffer[NUM_PORTS][MAX_QUEUE_DEPTH];
static ap_uint<NUM_PORTS> bitmap_buffer[NUM_PORTS][MAX_QUEUE_DEPTH];
static ap_uint<utils::req_bits(MAX_QUEUE_DEPTH)> voq[NUM_PORTS][NUM_PORTS][MAX_QUEUE_DEPTH];
static ap_uint<utils::req_bits(MAX_QUEUE_DEPTH)> voq_head[NUM_PORTS][NUM_PORTS];
static ap_uint<utils::req_bits(MAX_QUEUE_DEPTH)> voq_tail[NUM_PORTS][NUM_PORTS];
static ap_uint<utils::req_bits(MAX_QUEUE_DEPTH)> free_addr[NUM_PORTS][MAX_QUEUE_DEPTH];
static ap_uint<utils::req_bits(MAX_QUEUE_DEPTH)> free_addr_head[NUM_PORTS];
static ap_uint<utils::req_bits(MAX_QUEUE_DEPTH)> free_addr_tail[NUM_PORTS];

// digest states
static digest_state_t digest_states[NUM_PORTS];
static ap_uint<utils::req_bits(NUM_PORTS)> digest_dp[NUM_PORTS];

// tx states
static ap_uint<utils::req_bits(NUM_PORTS)> tx_serving_sp[NUM_PORTS];
static ap_uint<utils::req_bits(NUM_PORTS)> tx_next_sp[NUM_PORTS];
static ap_uint<1> tx_busy[NUM_PORTS];
static ap_uint<1> sp_busy[NUM_PORTS];

static void enqueue_word(
    const int sp,
    ap_uint<NUM_PORTS> dst_mask,
    const axis_wordi &cur_word
) {
#pragma HLS INLINE
    auto data_addr = free_addr[sp][free_addr_head[sp]];
    free_addr_head[sp] += 1;
    auto &data = data_buffer[sp][data_addr];
    auto &bitmap = bitmap_buffer[sp][data_addr];
    data   = cur_word;
    bitmap = dst_mask;
    for (int dp = 0; dp < NUM_PORTS; ++dp) {
    #pragma HLS UNROLL
        if (dst_mask[dp]) {
            int tail = voq_tail[sp][dp];
            voq[sp][dp][tail] = data_addr;
            voq_tail[sp][dp] = tail + 1;
        }
    }
}

void scheduler(
    axis_strmi data_after_rx[NUM_PORTS],
    meta_strm meta_after_hash[NUM_PORTS],
    axis_strm tx[NUM_PORTS],
    ap_uint<1> reset_ctrl
) {
    #pragma HLS PIPELINE II=4
    #pragma HLS INLINE off
    #pragma HLS ARRAY_PARTITION variable=data_buffer dim=1 complete
    #pragma HLS ARRAY_PARTITION variable=bitmap_buffer dim=1 complete
    #pragma HLS ARRAY_PARTITION variable=voq dim=1 complete
    #pragma HLS ARRAY_PARTITION variable=voq dim=2 complete
    #pragma HLS ARRAY_PARTITION variable=voq_head dim=1 complete
    #pragma HLS ARRAY_PARTITION variable=voq_head dim=2 complete
    #pragma HLS ARRAY_PARTITION variable=voq_tail dim=1 complete
    #pragma HLS ARRAY_PARTITION variable=voq_tail dim=2 complete
    #pragma HLS ARRAY_PARTITION variable=free_addr dim=1 complete
    #pragma HLS ARRAY_PARTITION variable=free_addr_head dim=1 complete
    #pragma HLS ARRAY_PARTITION variable=free_addr_tail dim=1 complete
    #pragma HLS BIND_STORAGE variable=data_buffer type=RAM_T2P impl=BRAM
    #pragma HLS BIND_STORAGE variable=bitmap_buffer type=RAM_T2P impl=BRAM
    #pragma HLS BIND_STORAGE variable=free_addr type=RAM_T2P impl=BRAM
    #pragma HLS BIND_STORAGE variable=voq         type=RAM_T2P impl=BRAM
    #pragma HLS ARRAY_PARTITION variable=digest_states   complete
    #pragma HLS ARRAY_PARTITION variable=digest_dp       complete
    #pragma HLS ARRAY_PARTITION variable=tx_busy         complete
    #pragma HLS ARRAY_PARTITION variable=tx_serving_sp   complete
    #pragma HLS ARRAY_PARTITION variable=tx_next_sp      complete
    #pragma HLS ARRAY_PARTITION variable=sp_busy         complete
    #pragma HLS DEPENDENCE variable=voq intra false
    #pragma HLS DEPENDENCE variable=data_buffer inter false
    #pragma HLS DEPENDENCE variable=data_buffer intra false
    #pragma HLS DEPENDENCE variable=free_addr intra false
    #pragma HLS DEPENDENCE variable=free_addr inter false
    #pragma HLS DEPENDENCE variable=tx_busy intra false
    #pragma HLS DEPENDENCE variable=tx_busy inter false
    #pragma HLS DEPENDENCE variable=sp_busy intra false
    #pragma HLS DEPENDENCE variable=sp_busy inter false
    #pragma HLS DEPENDENCE variable=bitmap_buffer intra false
    #pragma HLS DEPENDENCE variable=bitmap_buffer inter false
    #pragma HLS DEPENDENCE variable=free_addr_head intra false
    #pragma HLS DEPENDENCE variable=free_addr_head inter false
    #pragma HLS DEPENDENCE variable=free_addr_tail intra false
    #pragma HLS DEPENDENCE variable=free_addr_tail inter false
    #pragma HLS DEPENDENCE variable=voq_head intra false
    #pragma HLS DEPENDENCE variable=voq_head inter false
    #pragma HLS DEPENDENCE variable=voq_tail intra false
    #pragma HLS DEPENDENCE variable=voq_tail inter false
    #pragma HLS DEPENDENCE variable=tx_serving_sp intra false
    #pragma HLS DEPENDENCE variable=tx_serving_sp inter false
    #pragma HLS DEPENDENCE variable=tx_next_sp intra false
    #pragma HLS DEPENDENCE variable=tx_next_sp inter false
    #pragma HLS DEPENDENCE variable=digest_states intra false
    #pragma HLS DEPENDENCE variable=digest_states inter false


    static metadata IDLE_meta[NUM_PORTS];
    static axis_wordi IDLE_data[NUM_PORTS];
    static bool IDLE_meta_valid[NUM_PORTS];
    static bool IDLE_data_valid[NUM_PORTS];
    #pragma HLS ARRAY_PARTITION variable=IDLE_meta complete
    #pragma HLS ARRAY_PARTITION variable=IDLE_data complete
    #pragma HLS ARRAY_PARTITION variable=IDLE_meta_valid complete
    #pragma HLS ARRAY_PARTITION variable=IDLE_data_valid complete

    static ap_uint<32> reset_idx = 0; // Adjust bitwidth based on MAX_QUEUE_DEPTH, e.g., ap_uint<clog2(MAX_QUEUE_DEPTH)+1>

    if (reset_ctrl) {
        for (int i = 0; i < NUM_PORTS; i++) {
            #pragma HLS UNROLL
            bitmap_buffer[i][reset_idx] = 0;
            free_addr[i][reset_idx] = reset_idx;
        }
        reset_idx = (reset_idx + 1) % MAX_QUEUE_DEPTH;
        for (int i = 0; i < NUM_PORTS; i++) {
            #pragma HLS UNROLL
            digest_states[i] = IDLE;
            IDLE_data_valid[i] = false;
            IDLE_meta_valid[i] = false;
            tx_busy[i] = 0;
            sp_busy[i] = 0;
            tx_next_sp[i] = i;
            free_addr_head[i] = 0;
            free_addr_tail[i] = MAX_QUEUE_DEPTH - 1;
            for (int j = 0; j < NUM_PORTS; j++) {
                #pragma HLS UNROLL
                voq_head[i][j] = voq_tail[i][j] = 0;
            }
        }
        return;
    }

    bool free_list_empty[NUM_PORTS];    // snapshot
    bool voq_empty[NUM_PORTS][NUM_PORTS];          // snapshot
    for (int sp = 0; sp < NUM_PORTS; sp++) {
    #pragma HLS UNROLL
        free_list_empty[sp] = utils::is_empty(free_addr_head[sp], free_addr_tail[sp]);
    }
    for (int sp = 0; sp < NUM_PORTS; sp++) {
    #pragma HLS UNROLL
        for (int dp = 0; dp < NUM_PORTS; dp++) {
            #pragma HLS UNROLL
            voq_empty[sp][dp] = utils::is_empty(voq_head[sp][dp], voq_tail[sp][dp]);
        }
    }
    // digest
    for (int sp = 0; sp < NUM_PORTS; sp++) {
    #pragma HLS UNROLL
        metadata cur_meta;
        axis_wordi cur_word;
        ap_uint<NUM_PORTS> mask;

        if (free_list_empty[sp]) continue;
        bool need_enqueue = false;
        switch (digest_states[sp]) {
            case IDLE:
                if (!IDLE_meta_valid[sp] && !meta_after_hash[sp].empty()) {
                    IDLE_meta_valid[sp] = 1;
                    meta_after_hash[sp].read(IDLE_meta[sp]);
                    printf("received meta from src port = %d\n", sp);
                } 
                if (!IDLE_data_valid[sp] && !data_after_rx[sp].empty()) {
                    IDLE_data_valid[sp] = 1;
                    data_after_rx[sp].read(IDLE_data[sp]);
                    printf("received data from src port = %d\n", sp);
                }
                if (IDLE_meta_valid[sp] && IDLE_data_valid[sp]) {
                        need_enqueue = true;
                        cur_meta = IDLE_meta[sp];
                        cur_word = IDLE_data[sp];
                        IDLE_data_valid[sp] = false;
                        IDLE_meta_valid[sp] = false;
                        if (cur_meta.broadcast) {
                            digest_states[sp] = cur_word.last ? IDLE : PROCESSING_BROADCAST;
                            mask = ~((ap_uint<NUM_PORTS>)1 << sp);
                        } else {
                            digest_dp[sp] = cur_meta.dst_port;
                            digest_states[sp] = cur_word.last ? IDLE : PROCESSING_UNICAST;
                            mask = ((ap_uint<NUM_PORTS>)1 << digest_dp[sp]);
                        }
                    }
                    break;
                case PROCESSING_UNICAST:
                    if (!data_after_rx[sp].empty()) {
                        need_enqueue = true;
                        data_after_rx[sp].read(cur_word);
                        if (cur_word.last) digest_states[sp] = IDLE;
                        mask = ((ap_uint<NUM_PORTS>)1 << digest_dp[sp]);
                    }
                    break;
                case PROCESSING_BROADCAST:
                    if (!data_after_rx[sp].empty()) {
                        need_enqueue = true;
                        data_after_rx[sp].read(cur_word);
                        if (cur_word.last) digest_states[sp] = IDLE;
                        mask = ~((ap_uint<NUM_PORTS>)1 << sp);
                    }
                    break;
            }
        if (need_enqueue) enqueue_word(sp, mask, cur_word);
    }

    // output transmission
    int asked[NUM_PORTS];
    #pragma HLS ARRAY_PARTITION variable=asked complete
    #pragma HLS DEPENDENCE variable=asked intra false
    #pragma HLS DEPENDENCE variable=asked inter false
    for (int sp = 0; sp < NUM_PORTS; sp++) {
    #pragma HLS UNROLL
        asked[sp] = -1; // default value for not asked
    }
    for (int dp = 0; dp < NUM_PORTS; dp++) {
    #pragma HLS UNROLL
        int sp;
        sp = (tx_busy[dp] ? tx_serving_sp[dp] : tx_next_sp[dp]);
        bool valid = tx_busy[dp] || !sp_busy[sp];
        if (valid && !voq_empty[sp][dp]) {
            asked[sp] = dp;
            // int head = voq_head[sp][dp];
            // int data_addr = voq[sp][dp][head];
            // // auto &data = data_buffer[sp][data_addr];
            // voq_head[sp][dp] = head + 1;
            // // auto &bitmap = bitmap_buffer[sp]·[data_addr];
            // tx_busy[dp] = data_buffer[sp][data_addr].last ? ap_uint<1>(0) : ap_uint<1>(1);
            // sp_busy[sp] = data_buffer[sp][data_addr].last ? ap_uint<1>(0) : ap_uint<1>(1);
            //   if (!data_buffer[sp][data_addr].last) tx_serving_sp[dp] = sp;
            // bitmap_buffer[sp][data_addr] ^= ((ap_uint<NUM_PORTS>)1 << dp);
            // if (bitmap_buffer[sp][data_addr] == 0) {
            //     int tail = free_addr_tail[sp];
            //     free_addr[sp][tail] = data_addr;
            //     free_addr_tail[sp] = tail + 1;
            // }
            // tx[dp].write(static_cast<axis_word>(data_buffer[sp][data_addr]));
        }
        if (tx_next_sp[dp] == NUM_PORTS - 1) tx_next_sp[dp] = 0;
        else tx_next_sp[dp]++;
    }
    int tx_send_sp[NUM_PORTS];
    #pragma HLS ARRAY_PARTITION variable=tx_send_sp complete
    #pragma HLS DEPENDENCE variable=tx_send_sp intra false
    #pragma HLS DEPENDENCE variable=tx_send_sp inter false
    for (int dp = 0; dp < NUM_PORTS; dp++) {
    #pragma HLS UNROLL
        tx_send_sp[dp] = -1; // default value for not send
    }
    axis_wordi tx_send_data[NUM_PORTS];
    bool continue_serving[NUM_PORTS] = {0};
    #pragma HLS ARRAY_PARTITION variable=continue_serving complete
    #pragma HLS DEPENDENCE variable=continue_serving intra false
    #pragma HLS DEPENDENCE variable=continue_serving inter false
    #pragma HLS ARRAY_PARTITION variable=tx_send_data complete
    #pragma HLS DEPENDENCE variable=tx_send_data intra false
    #pragma HLS DEPENDENCE variable=tx_send_data inter false
    for (int sp = 0; sp < NUM_PORTS; sp++) {
    #pragma HLS UNROLL
        if (asked[sp] == -1) continue;
        int dp = asked[sp];
        int head = voq_head[sp][dp];
        int data_addr = voq[sp][dp][head];
        // auto &data = data_buffer[sp][data_addr];
        voq_head[sp][dp] = head + 1;
        // auto &bitmap = bitmap_buffer[sp][data_addr];
        // tx_busy[dp] = data_buffer[sp][data_addr].last ? ap_uint<1>(0) : ap_uint<1>(1);
        sp_busy[sp] = data_buffer[sp][data_addr].last ? ap_uint<1>(0) : ap_uint<1>(1);
        if (!data_buffer[sp][data_addr].last) continue_serving[dp] = 1;
        bitmap_buffer[sp][data_addr] ^= ((ap_uint<NUM_PORTS>)1 << dp);
        if (bitmap_buffer[sp][data_addr] == 0) {
            int tail = free_addr_tail[sp];
            free_addr[sp][tail] = data_addr;
            free_addr_tail[sp] = tail + 1;
        }
        // tx[dp].write(static_cast<axis_word>(data_buffer[sp][data_addr]));
        tx_send_sp[dp] = sp;
        tx_send_data[dp] = data_buffer[sp][data_addr];
    }
    for (int dp = 0; dp < NUM_PORTS; dp++) {
    #pragma HLS UNROLL
        if (tx_send_sp[dp] != -1) {
            tx[dp].write(tx_send_data[dp]);
            tx_busy[dp] = continue_serving[dp] ? ap_uint<1>(1) : ap_uint<1>(0);
            if (continue_serving[dp]) {
                tx_serving_sp[dp] = tx_send_sp[dp];
            }
        }
    }
}