#include <spac/spac.hpp>

#include <cstdint>

int main() {
    NB::Layout pkt;
    auto src = pkt.add_field<uint16_t>("src");
    auto dst = pkt.add_field<uint16_t>("dst");
    auto seq = pkt.add_field<uint8_t>("seq");

    SPAC::set_routing_key(src, dst);

    SPAC::SwitchConfig sw;
    sw.hash_policy   = SPAC::HashPolicy::MultiBankHash;
    sw.buffer_policy = SPAC::BufferPolicy::OneBufferPerPort;
    sw.scheduler     = SchedulerType::RoundRobin;
    sw.num_ports     = 8;
    sw.hash_bits     = 8;

    SPAC::compile_lib(seq, "./out_rr");
    return 0;
}
