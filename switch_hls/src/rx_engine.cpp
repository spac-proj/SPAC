#include "rx_engine.hpp"
#include "common.hpp"

enum rxStateEnum {HEADER, CONSUME};
static rxStateEnum rx_states[NUM_PORTS];

void rx_engine(
    ap_uint<utils::req_bits(NUM_PORTS)> src_port,
    axis_strm &data_in, 
    axis_strmi &data_out,
    meta_strm &meta_out,
    ap_uint<1> reset_ctrl
) {
#pragma HLS INLINE
#pragma HLS array_partition variable=rx_states complete dim=1
#pragma HLS dependence variable=rx_states inter false

    if (reset_ctrl) {
        rx_states[src_port] = HEADER;
        return;
    }

    ap_uint<ADDR_LENGTH> src_addr;
    ap_uint<ADDR_LENGTH> dst_addr;
    ap_uint<PACKET_TOTAL_LENGTH> pkt_len;
    axis_word cur_word;
    switch (rx_states[src_port]) {
        case HEADER:
            if (!data_in.empty()) {
                data_in.read(cur_word);
                pkt_len  = get_pkt_len(cur_word.data);
                src_addr = get_src(cur_word.data);
                dst_addr = get_dst(cur_word.data);
                meta_out.write(metadata(src_addr, dst_addr, 0, pkt_len, 0, 1));
                data_out.write(axis_wordi::from_axis_word(cur_word));
                if (!cur_word.last) rx_states[src_port] = CONSUME;
            }
            break;

        case CONSUME:
            if (!data_in.empty()) {
                data_in.read(cur_word);
                data_out.write(axis_wordi::from_axis_word(cur_word));
                if (cur_word.last) rx_states[src_port] = HEADER;
            }
            break;
    }
}