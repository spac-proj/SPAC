#pragma once
#include <ap_int.h>

namespace spac_packet {

constexpr int SRC_WIDTH      = 4;
constexpr int DST_WIDTH      = 4;
constexpr int PKT_LEN_WIDTH  = 32;

static_assert(SRC_WIDTH == DST_WIDTH,
              "Hash engine indexes the forwarding table by a single "
              "address width.");

constexpr int PKT_LEN_OFFSET = 0;
constexpr int DST_OFFSET     = 128;
constexpr int SRC_OFFSET     = 132;

template <int Width, int Lo>
inline ap_uint<Width> get_field(const ap_uint<512>& word) {
#pragma HLS INLINE
    return word.range(Lo + Width - 1, Lo);
}

template <int Width, int Lo>
inline void set_field(ap_uint<512>& word, ap_uint<Width> v) {
#pragma HLS INLINE
    word.range(Lo + Width - 1, Lo) = v;
}

inline ap_uint<SRC_WIDTH>     get_src    (const ap_uint<512>& w) { return get_field<SRC_WIDTH,     SRC_OFFSET>    (w); }
inline ap_uint<DST_WIDTH>     get_dst    (const ap_uint<512>& w) { return get_field<DST_WIDTH,     DST_OFFSET>    (w); }
inline ap_uint<PKT_LEN_WIDTH> get_pkt_len(const ap_uint<512>& w) { return get_field<PKT_LEN_WIDTH, PKT_LEN_OFFSET>(w); }

inline void set_src    (ap_uint<512>& w, ap_uint<SRC_WIDTH>     v) { set_field<SRC_WIDTH,     SRC_OFFSET>    (w, v); }
inline void set_dst    (ap_uint<512>& w, ap_uint<DST_WIDTH>     v) { set_field<DST_WIDTH,     DST_OFFSET>    (w, v); }
inline void set_pkt_len(ap_uint<512>& w, ap_uint<PKT_LEN_WIDTH> v) { set_field<PKT_LEN_WIDTH, PKT_LEN_OFFSET>(w, v); }

}  // namespace spac_packet

constexpr int ADDR_LENGTH         = spac_packet::SRC_WIDTH;
constexpr int PACKET_TOTAL_LENGTH = spac_packet::PKT_LEN_WIDTH;

using spac_packet::get_src;
using spac_packet::get_dst;
using spac_packet::get_pkt_len;
using spac_packet::set_src;
using spac_packet::set_dst;
using spac_packet::set_pkt_len;
