#include <spac/spac.hpp>

#include <cstdint>

int main() {
    // Custom Protocol
    NB::Layout pkt;
    auto src = pkt.add_field<uint8_t>("src");
    auto dst = pkt.add_field<uint8_t>("dst");
    auto seq = pkt.add_field<uint8_t>("seq");

    // Semantic Binding
    SPAC::set_routing_key(src, dst);
    SPAC::set_flow_id(seq);

    // Switch Architecture
    SPAC::SwitchConfig sw;
    sw.hash_policy         = SPAC::HashPolicy::FullLookupTable;
    sw.buffer_policy       = SPAC::BufferPolicy::NBuffersPerPort;
    sw.scheduler           = SchedulerType::iSLIP;
    sw.num_ports           = 4;
    sw.max_queue_depth_log = 3;

    SPAC::compile_lib(seq, "./out_demo");
    return 0;
}
