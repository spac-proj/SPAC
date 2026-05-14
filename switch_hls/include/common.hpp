#pragma once
#include <ap_axi_sdata.h>
#include <hls_stream.h>
#include <ap_int.h>

#include "packet.hpp"


// Queue Settings
constexpr int MAX_QUEUE_DEPTH_LOG = 3;
constexpr int MAX_QUEUE_DEPTH = 1 << MAX_QUEUE_DEPTH_LOG; // Max queue size for VOQ, must be power of 2 for quick mod

namespace utils {
    constexpr int req_bits(int n) { // calculate require bits for representing n, minimum is 1
        return (n <= 2) ? 1 : req_bits(n >> 1) + 1;
    }
    inline bool is_full(ap_uint<utils::req_bits(MAX_QUEUE_DEPTH)> &head, ap_uint<utils::req_bits(MAX_QUEUE_DEPTH)> &tail) {
    #pragma HLS INLINE  
        return head == (tail + 1) % MAX_QUEUE_DEPTH;
    }
    inline bool is_empty(ap_uint<utils::req_bits(MAX_QUEUE_DEPTH)> &head, ap_uint<utils::req_bits(MAX_QUEUE_DEPTH)> &tail) {
    #pragma HLS INLINE  
        return head == tail;
    }
}

// Global Settings for each module
constexpr int NUM_PORTS = 4;      // Alveo U45N support 8 ports in breakout mode

enum class HashModuleType {
    MultiBankHash,
    FullLookupTable
};

enum class BufferType {
    OneBufferPerPort,  // "1b1p"
    NBuffersPerPort    // "nb1p"
};

enum class SchedulerType {
    RoundRobin,
    iSLIP
};

constexpr HashModuleType HASH_MODULE_TYPE = HashModuleType::FullLookupTable; // "MultiBankHash" or "FullLookupTable"
constexpr int HASH_BANKS_BITS = utils::req_bits(NUM_PORTS);  // for MultiBankHash, Number of bits used in hash banks, 3 bits for 8 banks
constexpr int HASH_BANKS = NUM_PORTS; // for MultiBankHash, Number of banks in MultiBankHash
constexpr int HASH_BITS = 7;     // for MultiBankHashm, Number of bits used in hash function for forwarding table

constexpr BufferType BUFFER_TYPE = BufferType::NBuffersPerPort; // "1b1p" or "nb1p", 1 buffer per port or N buffers per port

constexpr SchedulerType SCHEDULER_TYPE = SchedulerType::iSLIP; // "RoundRobin" or "iSLIP", Round Robin or iSLIP scheduler

// AXI-Stream
typedef ap_axiu<512,1,0,0> axis_word; // <data, user, unuse, unuse>
typedef hls::stream<axis_word> axis_strm;

struct axis_wordi {
    ap_uint<512> data;
    ap_uint<1>   last;

    axis_wordi() {}

    axis_wordi(ap_uint<512> data, ap_uint<1> last)
        : data(data), last(last) {}

    operator axis_word() const {
        axis_word out;
        out.data = data;
        out.keep = -1; 
        out.last = last;
        out.user = 0;
        return out;
    }

    static axis_wordi from_axis_word(const axis_word &in) {
        return axis_wordi(in.data, in.last);
    }
};
typedef hls::stream<axis_wordi> axis_strmi;


// Meta data info, Extracted Info mations, src port omitted as it is iterated in top
struct metadata {
    ap_uint<ADDR_LENGTH> src_addr;   // Source address
    ap_uint<ADDR_LENGTH> dst_addr;  // Destine address
    ap_uint<utils::req_bits(NUM_PORTS)> dst_port;  // Destine port
    ap_uint<PACKET_TOTAL_LENGTH> pkt_len;   // Packet total Length（32 bits align with NetBlocks, maybe too much）
    ap_uint<1> broadcast;  // Broadcast sign, use when dst port is unknown
    ap_uint<1> valid;      // Valid sign, may use for checksum in the future
    metadata() {}
    metadata(ap_uint<ADDR_LENGTH> sa, ap_uint<ADDR_LENGTH> da, ap_uint<utils::req_bits(NUM_PORTS)> dp, 
    ap_uint<PACKET_TOTAL_LENGTH> pl, ap_uint<1> bd, ap_uint<1> v)
     : src_addr(sa), dst_addr(da), dst_port(dp), pkt_len(pl), broadcast(bd), valid(v) {}
};

typedef hls::stream<metadata> meta_strm;
