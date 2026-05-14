#include "hash_engine.hpp"
#include "common.hpp"
#include "stdio.h"
#include "algorithm"

// Forwarding table, 1bit valid + ADDR_LENGTH bits for verifying + LOG_NUM_PORTS bits for ports
constexpr int VALID_START = 0;
constexpr int PORT_START = VALID_START + 1;
constexpr int PORT_END = PORT_START + utils::req_bits(NUM_PORTS) - 1;
constexpr int ADDR_START = PORT_END + 1;
constexpr int ADDR_END   = ADDR_START + ADDR_LENGTH - 1;

void multi_bank_hash(
    meta_strm meta_in[NUM_PORTS],
    meta_strm meta_out[NUM_PORTS],
    ap_uint<1> reset_ctrl
) {
    static ap_uint<1 + ADDR_LENGTH + utils::req_bits(NUM_PORTS)> fwd_table[HASH_BANKS][1 << HASH_BITS];
    #pragma HLS INLINE off
    #pragma HLS PIPELINE II=3

    #pragma HLS ARRAY_PARTITION variable=fwd_table dim=1 type=complete
    #pragma HLS dependence variable=fwd_table intra false
    #pragma HLS dependence variable=fwd_table inter false
    static metadata buffer[NUM_PORTS]; // For simplicity, buffer depth is 1
    static int save_ptr[HASH_BANKS];
    static int read_ptr[HASH_BANKS];
    static bool saved[NUM_PORTS];
    static bool read[NUM_PORTS];
    #pragma HLS ARRAY_PARTITION variable=buffer complete
    #pragma HLS ARRAY_PARTITION variable=save_ptr complete
    #pragma HLS ARRAY_PARTITION variable=read_ptr complete
    #pragma HLS ARRAY_PARTITION variable=saved complete
    #pragma HLS ARRAY_PARTITION variable=read complete
    #pragma HLS dependence variable=buffer intra false
    #pragma HLS dependence variable=buffer inter false
    #pragma HLS dependence variable=save_ptr intra false
    #pragma HLS dependence variable=save_ptr inter false
    #pragma HLS dependence variable=read_ptr intra false
    #pragma HLS dependence variable=read_ptr inter false
    #pragma HLS dependence variable=saved intra false
    #pragma HLS dependence variable=saved inter false
    #pragma HLS dependence variable=read intra false
    #pragma HLS dependence variable=read inter false

    if (reset_ctrl) {
        for (int i = 0; i < NUM_PORTS; i++) {
        #pragma HLS UNROLL
            saved[i] = 1;
            read[i] = 1;
        }
        for (int i = 0; i < HASH_BANKS; i++) {
        #pragma HLS UNROLL
            save_ptr[i] = read_ptr[i] = 0;
        }
        return;
    }
    bool req_save[NUM_PORTS][HASH_BANKS] = {false};
    bool req_read[NUM_PORTS][HASH_BANKS] = {false};
    #pragma HLS ARRAY_PARTITION variable=req_save dim=1 type=complete
    #pragma HLS ARRAY_PARTITION variable=req_save dim=2 type=complete
    #pragma HLS ARRAY_PARTITION variable=req_read dim=1 type=complete
    #pragma HLS ARRAY_PARTITION variable=req_read dim=2 type=complete
    for (int sp = 0; sp < NUM_PORTS; sp++) {
    #pragma HLS UNROLL
        if (saved[sp] && read[sp]) {
            if (!meta_in[sp].empty()) {
                meta_in[sp].read(buffer[sp]);
                ap_uint<HASH_BANKS_BITS> src_bank = ap_uint<HASH_BANKS_BITS> (buffer[sp].src_addr);
                ap_uint<HASH_BANKS_BITS> dst_bank = ap_uint<HASH_BANKS_BITS> (buffer[sp].dst_addr);
                printf("hash reading meta from sp = %d, src_bank = %d, dst_bank = %d\n", sp, src_bank, dst_bank);
                saved[sp] = 0;
                read[sp] = 0;
                req_save[sp][src_bank] = 1;
                req_read[sp][dst_bank] = 1;
            } 
        } else {
            if (!saved[sp]) {
                ap_uint<HASH_BANKS_BITS> src_bank = ap_uint<HASH_BANKS_BITS> (buffer[sp].src_addr);
                req_save[sp][src_bank] = 1;
            }
            if (!read[sp]) {
                ap_uint<HASH_BANKS_BITS> dst_bank = ap_uint<HASH_BANKS_BITS> (buffer[sp].dst_addr);
                req_read[sp][dst_bank] = 1;
            }
        }
    }
    int grant_save[HASH_BANKS];
    int grant_read[HASH_BANKS];
    #pragma HLS ARRAY_PARTITION variable=grant_save dim=1 type=complete
    #pragma HLS ARRAY_PARTITION variable=grant_read dim=1 type=complete
    for (int b = 0; b < HASH_BANKS; b++) {
    #pragma HLS UNROLL
        grant_save[b] = grant_read[b] = -1;
        int sv = save_ptr[b];

        // if (b == 2 && req_save[2][2]) {
        //     printf("hash_engine: req_save[2][2] is true\n");
        //     printf("hash_engine: save_ptr = %d\n", save_ptr[b]);
        // }
        // if (b == 1 && req_read[2][1]) {
        //     printf("hash_engine: req_read[2][1] is true\n");
        //     printf("hash_engine: read_ptr = %d\n", read_ptr[b]);
        // }

        for (int step = 0; step < NUM_PORTS; step++) { // not grant same as previous cycle
            if (req_save[sv][b]) {
                grant_save[b] = sv;
                break;
            }
            sv = (sv == NUM_PORTS - 1) ? 0 : sv + 1;
        }
        save_ptr[b] = sv;
        int rv = read_ptr[b];
        for (int step = 0; step < NUM_PORTS; step++) { // not grant same as previous cycle
            if (req_read[rv][b]) {
                grant_read[b] = rv;
                break;
            }
            rv = (rv == NUM_PORTS - 1) ? 0 : rv + 1;
        }
        read_ptr[b] = rv;
    }
    bool save_temp[NUM_PORTS] = {0};
    bool read_temp[NUM_PORTS] = {0};
    #pragma HLS ARRAY_PARTITION variable=save_temp complete
    #pragma HLS ARRAY_PARTITION variable=read_temp complete
    metadata save_buffer_temp[NUM_PORTS];
    metadata read_buffer_temp[NUM_PORTS];
    #pragma HLS ARRAY_PARTITION variable=save_buffer_temp complete
    #pragma HLS ARRAY_PARTITION variable=read_buffer_temp complete
    for (int sp = 0; sp < NUM_PORTS; sp++) {
    #pragma HLS UNROLL
        save_buffer_temp[sp] = buffer[sp]; 
    }
    for (int b = 0; b < HASH_BANKS; b++) {
        #pragma HLS UNROLL
        int sp_s = grant_save[b];
        int sp_r = grant_read[b];
        if (sp_s != -1) {
            ap_uint<1 + ADDR_LENGTH + utils::req_bits(NUM_PORTS)> src_entry;
            auto m = save_buffer_temp[sp_s];
            src_entry.bit(VALID_START) = 1;
            src_entry(ADDR_END, ADDR_START) = m.src_addr;
            src_entry(PORT_END, PORT_START) = ap_uint<utils::req_bits(NUM_PORTS)>(sp_s);
            auto src_key = ap_uint<HASH_BITS> (m.src_addr);
            fwd_table[b][src_key] = src_entry; // one write
            save_temp[sp_s] = 1;
        }
        if (sp_r != -1) {
            ap_uint<1 + ADDR_LENGTH + utils::req_bits(NUM_PORTS)> dst_entry;
            auto m = save_buffer_temp[sp_r];
            auto dst_key = ap_uint<HASH_BITS> (m.dst_addr);
            dst_entry = fwd_table[b][dst_key]; // one read
            bool empty  = (dst_entry.bit(VALID_START) == 0);
            bool hit    = (dst_entry(ADDR_END, ADDR_START) == m.dst_addr);
            if (!empty && hit) {
                m.dst_port = dst_entry(PORT_END, PORT_START);
                m.broadcast = 0;
            } else {
                m.broadcast = 1;
            }
            read_buffer_temp[sp_r] = m; // update dst port
            read_temp[sp_r] = 1;
        }
    }
    for (int sp = 0; sp < NUM_PORTS; sp++) {
    #pragma HLS UNROLL
        if (save_temp[sp]) {
            saved[sp] = 1; // save src entry
            printf("saved, %d %d %d\n", sp, saved[sp], read[sp]);
        }
        if (read_temp[sp]) {
            meta_out[sp].write(read_buffer_temp[sp]); // write out dst entry
            read[sp] = 1; // output dst entry
            printf("outed, %d %d %d\n", sp, saved[sp], read[sp]);
        }
    }
}

void full_lookup_table(
    meta_strm meta_in[NUM_PORTS],
    meta_strm meta_out[NUM_PORTS],
    ap_uint<1> reset_ctrl
) {
    #pragma HLS INLINE off
    #pragma HLS PIPELINE II=1

    static ap_uint<1 + utils::req_bits(NUM_PORTS)> fwd_table[1 << ADDR_LENGTH];
    #pragma HLS ARRAY_PARTITION variable=fwd_table dim=1 type=complete
    #pragma HLS dependence variable=fwd_table intra false
    #pragma HLS dependence variable=fwd_table inter false

    if (reset_ctrl) {
        for (int i = 0; i < (1 << ADDR_LENGTH); i++) {
        #pragma HLS UNROLL
            fwd_table[i] = 0; // reset forwarding table
        }
        return;
    }
    ap_uint<1 + utils::req_bits(NUM_PORTS)> read_table[1 << ADDR_LENGTH];
    ap_uint<1 + utils::req_bits(NUM_PORTS)> write_table[1 << ADDR_LENGTH];
    #pragma HLS ARRAY_PARTITION variable=read_table dim=1 type=complete
    #pragma HLS ARRAY_PARTITION variable=write_table dim=1 type=complete

    for (int i = 0; i < (1 << ADDR_LENGTH); i++) {
    #pragma HLS UNROLL
        read_table[i] = fwd_table[i]; // read forwarding table
        write_table[i] = 0; // reset write table
    }

    for (int sp = 0; sp < NUM_PORTS; sp++) {
    #pragma HLS UNROLL
        if (!meta_in[sp].empty()) {
            metadata m;
            meta_in[sp].read(m);
            write_table[m.src_addr].bit(VALID_START) = 1;
            write_table[m.src_addr](PORT_END, PORT_START) = ap_uint<utils::req_bits(NUM_PORTS)>(sp);
            ap_uint<ADDR_LENGTH> dst = m.dst_addr;
            if (read_table[dst].bit(VALID_START) == 1) {
                m.dst_port = read_table[dst](PORT_END, PORT_START);
                m.broadcast = 0;
            } else {
                m.broadcast = 1;
            }
            meta_out[sp].write(m); // write out dst entry
        }
    }
    for (int i = 0; i < (1 << ADDR_LENGTH); i++) {
    #pragma HLS UNROLL
        if (write_table[i].bit(VALID_START) == 1) {
            fwd_table[i] = write_table[i]; // write forwarding table
        }
    }
}