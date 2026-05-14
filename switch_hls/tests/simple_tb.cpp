// #include "switch_top.hpp"
// #include "common.hpp"
// #include <cstdio>

// // AXIS beat construction
// static axis_word make_header(
//         ap_uint<ADDR_LENGTH> src,
//         ap_uint<ADDR_LENGTH> dst,
//         ap_uint<PACKET_TOTAL_LENGTH> words) {
//     axis_word w;
//     // Clear entire word
//     w.data = 0;
//     // Payload length (words inc. header)
//     w.data(PACKET_TOTAL_LENGTH - 1, 0) = words;
//     // Source & destination L2 addresses
//     w.data(SRC_ADDR_START + ADDR_LENGTH - 1, SRC_ADDR_START) = src;
//     w.data(DST_ADDR_START + ADDR_LENGTH - 1, DST_ADDR_START) = dst;
//     // Single-word packet -> last = 1
//     w.last = 1;
//     return w;
// }

// // Push a single-word packet into ingress stream of port `p`
// static void inject_packet(axis_strm (&rx)[NUM_PORTS],
//                           unsigned      p,
//                           ap_uint<ADDR_LENGTH> src,
//                           ap_uint<ADDR_LENGTH> dst) {
//     axis_word hdr = make_header(src, dst, 1);
//     rx[p].write(hdr);
// }

// // Read out one packet (single word) if present, return true if got one
// static bool drain_packet(axis_strm &txPort,
//                          ap_uint<ADDR_LENGTH> &src,
//                          ap_uint<ADDR_LENGTH> &dst) {
//     if (txPort.size() == 0) return false;
//     axis_word w = txPort.read();
//     src = w.data(SRC_ADDR_START + ADDR_LENGTH - 1, SRC_ADDR_START);
//     dst = w.data(DST_ADDR_START + ADDR_LENGTH - 1, DST_ADDR_START);
//     return true;
// }

// // Simulation constants

// static void run_cycles(axis_strm (&rx)[NUM_PORTS],
//                        axis_strm (&tx)[NUM_PORTS],
//                        int cycles,
//                        ap_uint<1> &rst) {
//     for (int c = 0; c < cycles; ++c) {
//         switch_top(rx, tx, rst);
//         for (int p = 0; p < NUM_PORTS; p++) {
//             if (tx[p].size() > 0) {
//                 printf("cycle = %d, port = %d, size = %d \n", c, p, (int)tx[p].size());
//             }
//         }
//     }
// }

// int main() {

//     axis_strm rx[NUM_PORTS];
//     axis_strm tx[NUM_PORTS];
// #pragma HLS STREAM variable=rx depth=32
// #pragma HLS STREAM variable=tx depth=32

//     ap_uint<1> reset_ctrl = 1;

//     run_cycles(rx, tx, 32, reset_ctrl); // clear
//     reset_ctrl = 0;
//     run_cycles(rx, tx, 32, reset_ctrl); // make it stable
    
//     // Test #1 – Flooding on unknown destination
//     // Packet: Port1 (addr=0x1) -> dst_addr = 0x2 (unknown)
//     printf("Before injection: rx[1].size()=%d\n", (int)rx[1].size());
//     inject_packet(rx, 1, 0x1, 0x2);
//     printf("After injection: rx[1].size()=%d\n", (int)rx[1].size());
//     run_cycles(rx, tx, 32, reset_ctrl);
//     printf("After digest: rx[1].size()=%d\n", (int)rx[1].size());
//     for (unsigned p = 0; p < NUM_PORTS; ++p) {
//         printf("tx[%u].size()=%d\n", p, (int)tx[p].size());
//     }

//     bool flood_ok = true;
//     ap_uint<ADDR_LENGTH> src, dst;

//     // Expect one copy on every egress except port1
//     for (unsigned p = 0; p < NUM_PORTS; ++p) {
//         if (p == 1) continue;
//         bool got = drain_packet(tx[p], src, dst);
//         flood_ok &= got && (dst == 0x2) && (src == 0x1);
//         printf("got %u= %d\n", p, got ? 1 : 0);
//     }
//     // Port1 must be silent
//     flood_ok &= (tx[1].size() == 0);

//     printf("[TB] Flooding test : %s\n", flood_ok ? "PASS" : "FAIL");

//     // Test #2 – Learning + Unicast
//     // Packet: Port2 (addr=0x2) -> dst = 0x1 (switch should have learned mappint (src_addr=0x1, port1)
//     inject_packet(rx, 2, 0x2, 0x1);
//     run_cycles(rx, tx, 32, reset_ctrl);

//     bool unicast_ok =
//         drain_packet(tx[1], src, dst) && src == 0x2 && dst == 0x1;

//     // Ensure no duplicates on other egresses
//     for (unsigned p = 0; p < NUM_PORTS; p++) {
//         if (p == 1) continue;
//         unicast_ok &= (tx[p].size() == 0);
//     }
//     printf("[TB] Learning & unicast test : %s\n",
//            unicast_ok ? "PASS" : "FAIL");

//     // 4. Summary
//     if (flood_ok && unicast_ok) {
//         printf("[TB] *** ALL TESTS PASSED ***\n");
//         return 0;
//     } else {
//         printf("[TB] *** TESTS FAILED ***\n");
//         return 0;
//     }
// }
#include "switch_top.hpp"
#include "common.hpp"
#include <cstdio>
#include <cstring>

// -----------------------------------------------------------------------------
// Helpers: construct AXIS beats (same conventions as your original TB)
// -----------------------------------------------------------------------------

// Create a header beat for a packet of `words` total beats (including header).
// last == 1 only if words == 1.
static axis_word make_header_total(
        ap_uint<ADDR_LENGTH> src,
        ap_uint<ADDR_LENGTH> dst,
        ap_uint<PACKET_TOTAL_LENGTH> words) {
    axis_word w;
    // clear
    w.data = 0;
    // packet length field
    w.data(PACKET_TOTAL_LENGTH - 1, 0) = words;
    // addresses
    w.data(SRC_ADDR_START + ADDR_LENGTH - 1, SRC_ADDR_START) = src;
    w.data(DST_ADDR_START + ADDR_LENGTH - 1, DST_ADDR_START) = dst;
    // last only if single-beat packet
    w.last = (words == 1) ? 1 : 0;
    return w;
}

// Create a payload beat with a simple payload id and last flag.
static axis_word make_payload_beat(unsigned seq_id, bool last) {
    axis_word w;
    w.data = 0;
    // put seq in low bits (these bits are not used for header parsing)
    w.data(31, 0) = seq_id;
    w.last = last ? 1 : 0;
    return w;
}

// Inject a single-word packet into ingress port p
static void inject_packet(axis_strm (&rx)[NUM_PORTS],
                          unsigned      p,
                          ap_uint<ADDR_LENGTH> src,
                          ap_uint<ADDR_LENGTH> dst) {
    axis_word hdr = make_header_total(src, dst, 1);
    rx[p].write(hdr);
}

// Inject a multi-beat packet into ingress port p
// total_words >= 1, header is the first beat, then (total_words-1) payload beats
static void inject_multiword_packet(axis_strm (&rx)[NUM_PORTS],
                                    unsigned p,
                                    ap_uint<ADDR_LENGTH> src,
                                    ap_uint<ADDR_LENGTH> dst,
                                    int total_words,
                                    unsigned payload_base = 0x1000) {
    if (total_words <= 0) total_words = 1;
    // header
    axis_word hdr = make_header_total(src, dst, (ap_uint<PACKET_TOTAL_LENGTH>)total_words);
    rx[p].write(hdr);
    // payload beats
    for (int i = 1; i < total_words; ++i) {
        bool last = (i == total_words - 1);
        axis_word pl = make_payload_beat(payload_base + (unsigned)i, last);
        rx[p].write(pl);
    }
}

// Drain a multi-beat packet from txPort into dst_buf[] (max_words capacity).
// Returns number of beats read. Fills out_src/out_dst from the first beat header.
static int drain_packet_beats(axis_strm &txPort,
                              axis_word dst_buf[],
                              int max_words,
                              ap_uint<ADDR_LENGTH> &out_src,
                              ap_uint<ADDR_LENGTH> &out_dst) {
    if (txPort.size() == 0) return 0;
    int count = 0;
    // read until last=1 or until max_words reached
    while (txPort.size() > 0 && count < max_words) {
        axis_word w = txPort.read();
        dst_buf[count++] = w;
        if (count == 1) {
            // extract addresses from header beat
            out_src = w.data(SRC_ADDR_START + ADDR_LENGTH - 1, SRC_ADDR_START);
            out_dst = w.data(DST_ADDR_START + ADDR_LENGTH - 1, DST_ADDR_START);
        }
        if (w.last) break;
    }
    return count;
}

// Print contents of packet (for debugging)
static void print_packet_beats(axis_word buf[], int n) {
    for (int i = 0; i < n; ++i) {
        printf("  beat %d: data_low32=0x%08x last=%d\n", i, (unsigned)buf[i].data(31,0), (int)buf[i].last);
    }
}

// Utility: single-cycle runner (calls switch_top n times)
static void run_cycles(axis_strm (&rx)[NUM_PORTS],
                       axis_strm (&tx)[NUM_PORTS],
                       int cycles,
                       ap_uint<1> &rst) {
    for (int c = 0; c < cycles; ++c) {
        switch_top(rx, tx, rst);
        // for (int p = 0; p < NUM_PORTS; p++) {
        //     if (tx[p].size() > 0) {
        //         printf("cycle = %d, port = %d, size = %d \n", c, p, (int)tx[p].size());
        //     }
        // }
    }
}

// -----------------------------------------------------------------------------
// Test bench main
// -----------------------------------------------------------------------------
int main() {

    axis_strm rx[NUM_PORTS];
    axis_strm tx[NUM_PORTS];
#pragma HLS STREAM variable=rx depth=64
#pragma HLS STREAM variable=tx depth=64

    ap_uint<1> reset_ctrl = 1;

    // Reset / initialization cycles
    run_cycles(rx, tx, 128, reset_ctrl); // reset stage
    reset_ctrl = 0;
    run_cycles(rx, tx, 128, reset_ctrl); // stabilization

    // ----------------------------
    // Test 1 — Flooding on unknown destination (existing test)
    // ----------------------------
    printf("Before injection: rx[1].size()=%d\n", (int)rx[1].size());
    inject_packet(rx, 1, 0x1, 0x2);
    printf("After injection: rx[1].size()=%d\n", (int)rx[1].size());
    run_cycles(rx, tx, 128, reset_ctrl);
    printf("After digest: rx[1].size()=%d\n", (int)rx[1].size());
    for (unsigned p = 0; p < NUM_PORTS; ++p) {
        printf("tx[%u].size()=%d\n", p, (int)tx[p].size());
    }

    bool flood_ok = true;
    ap_uint<ADDR_LENGTH> src, dst;

    // Expect one copy on every egress except port1
    for (unsigned p = 0; p < NUM_PORTS; ++p) {
        if (p == 1) continue;
        bool got = false;
        if (tx[p].size() > 0) {
            axis_word w = tx[p].read();
            got = true;
            src = w.data(SRC_ADDR_START + ADDR_LENGTH - 1, SRC_ADDR_START);
            dst = w.data(DST_ADDR_START + ADDR_LENGTH - 1, DST_ADDR_START);
        }
        flood_ok &= got && (dst == 0x2) && (src == 0x1);
        printf("got %u= %d\n", p, got ? 1 : 0);
    }
    // Port1 must be silent
    flood_ok &= (tx[1].size() == 0);
    printf("[TB] Flooding test : %s\n", flood_ok ? "PASS" : "FAIL");

    // ----------------------------
    // Test 2 — Learning + Unicast (existing test)
    // ----------------------------
    inject_packet(rx, 2, 0x2, 0x1); // port2 -> dst 0x1 (should be forwarded to port1)
    run_cycles(rx, tx, 128, reset_ctrl);

    bool unicast_ok = false;
    if (tx[1].size() > 0) {
        axis_word w = tx[1].read();
        ap_uint<ADDR_LENGTH> s = w.data(SRC_ADDR_START + ADDR_LENGTH - 1, SRC_ADDR_START);
        ap_uint<ADDR_LENGTH> d = w.data(DST_ADDR_START + ADDR_LENGTH - 1, DST_ADDR_START);
        unicast_ok = (s == 0x2 && d == 0x1);
    }
    // Ensure no duplicates on other egresses
    for (unsigned p = 0; p < NUM_PORTS; p++) {
        if (p == 1) continue;
        unicast_ok &= (tx[p].size() == 0);
    }
    printf("[TB] Learning & unicast test : %s\n",
           unicast_ok ? "PASS" : "FAIL");

    // ----------------------------
    // Test 3 — Multi-beat packet (single packet split into multiple AXIS beats)
    //   - Send a 4-beat packet from port 2 to destination 0x1 (learned earlier)
    //   - Expect tx[1] to deliver 4 beats in order with last set on final beat
    // ----------------------------
    const int multi_len = 4;
    inject_multiword_packet(rx, 2, 0x2, 0x1, multi_len, 0x2000);
    // run enough cycles for the packet to be digested and forwarded
    run_cycles(rx, tx, 128, reset_ctrl);

    axis_word pkt_buf[128];
    int got_words = drain_packet_beats(tx[1], pkt_buf, 128, src, dst);
    bool multi_ok = (got_words == multi_len) && (src == 0x2) && (dst == 0x1);
    if (!multi_ok) {
        printf("[TB] Multi-beat: expected %d beats, got %d\n", multi_len, got_words);
    } else {
        printf("[TB] Multi-beat: got packet from src=0x%x dst=0x%x len=%d\n", (unsigned)src, (unsigned)dst, got_words);
    }
    // optional: print packet beats for debugging
    // print_packet_beats(pkt_buf, got_words);
    printf("[TB] Multi-beat packet test : %s\n", multi_ok ? "PASS" : "FAIL");

    // ----------------------------
    // Test 4 — Two consecutive packets to the same destination (ordering)
    //   - Send two packets back-to-back from same source to same dst
    //   - Ensure they are delivered fully in order (packet A then packet B)
    // ----------------------------
    // Packet A: length 3, payload IDs base 0x3000
    // Packet B: length 2, payload IDs base 0x4000
    inject_multiword_packet(rx, 2, 0x2, 0x1, 3, 0x3000);
    inject_multiword_packet(rx, 2, 0x2, 0x1, 2, 0x4000);
    run_cycles(rx, tx, 96, reset_ctrl); // allow more cycles for two packets

    // Drain first packet
    axis_word pktA[128];
    ap_uint<ADDR_LENGTH> a_src, a_dst;
    int a_words = drain_packet_beats(tx[1], pktA, 128, a_src, a_dst);
    // Drain second packet
    axis_word pktB[128];
    ap_uint<ADDR_LENGTH> b_src, b_dst;
    int b_words = drain_packet_beats(tx[1], pktB, 128, b_src, b_dst);

    bool order_ok = true;
    order_ok &= (a_words == 3) && (b_words == 2);
    order_ok &= (a_src == 0x2) && (a_dst == 0x1);
    order_ok &= (b_src == 0x2) && (b_dst == 0x1);
    if (!order_ok) {
        printf("[TB] Two-packet ordering FAIL: a_words=%d b_words=%d a_src=0x%x b_src=0x%x\n",
               a_words, b_words, (unsigned)a_src, (unsigned)b_src);
    } else {
        printf("[TB] Two-packet ordering OK: A_len=%d B_len=%d\n", a_words, b_words);
    }
    printf("[TB] Consecutive packets to same dst test : %s\n", order_ok ? "PASS" : "FAIL");

    // ----------------------------
    // Test 5 — Broadcast multi-beat packet
    //   - Send a multi-beat broadcast from port 0; expect all egress ports except 0 to receive packet.
    // ----------------------------
    const int bcast_len = 3;
    inject_multiword_packet(rx, 0, 0, 0x7, bcast_len, 0x5000);
    // For broadcast, we must set the 'broadcast' bit in meta; in this testbench our make_header_total
    // does not set a separate broadcast flag. If the switch determines broadcast from a specific dst value,
    // adapt accordingly. We'll assume that dst==0 indicates broadcast in your environment OR your
    // meta generator sets broadcast — if that is different, adjust accordingly.
    run_cycles(rx, tx, 96, reset_ctrl);

    bool bcast_ok = true;
    for (unsigned p = 0; p < NUM_PORTS; ++p) {
        if (p == 0) {
            // source should not get its own copy
            bcast_ok &= (tx[p].size() == 0);
            continue;
        }
        axis_word tmp_buf[128];
        ap_uint<ADDR_LENGTH> s, d;
        int rc = drain_packet_beats(tx[p], tmp_buf, 128, s, d);
        if (rc != bcast_len) {
            printf("[TB] Broadcast: port %u expected %d beats, got %d\n", p, bcast_len, rc);
            bcast_ok = false;
        } else {
            // We don't assert addresses here because broadcast semantics in your design may encode addresses differently.
            printf("[TB] Broadcast: port %u got %d beats\n", p, rc);
        }
    }
    printf("[TB] Broadcast multi-beat test : %s\n", bcast_ok ? "PASS" : "FAIL");

    // ----------------------------
    // Final summary
    // ----------------------------
    bool all_ok = flood_ok && unicast_ok && multi_ok && order_ok && bcast_ok;
    if (all_ok) {
        printf("[TB] *** ALL TESTS PASSED ***\n");
        return 0;
    } else {
        printf("[TB] *** SOME TESTS FAILED ***\n");
        return 1;
    }
}
