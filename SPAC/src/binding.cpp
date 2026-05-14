#include "spac/binding.hpp"
#include "spac/registry.hpp"

#include <stdexcept>

namespace SPAC {

namespace {
void require_field(const NB::FieldRef& f, const char* who) {
    if (!f.valid()) {
        throw std::runtime_error(std::string(who)
            + ": FieldRef is not valid (was it returned by Layout::add_field?)");
    }
}
}  // namespace

void set_routing_key(NB::FieldRef src, NB::FieldRef dst) {
    require_field(src, "set_routing_key(src)");
    require_field(dst, "set_routing_key(dst)");
    if (src.bits != dst.bits) {
        throw std::runtime_error(
            "set_routing_key: src and dst widths must currently match "
            "(hash engine indexes the forwarding table by a single width).");
    }
    auto& reg = internal::Registry::get();
    reg.routing_src    = src;
    reg.routing_dst    = dst;
    reg.routing_key_set = true;
}

void set_flow_id(NB::FieldRef seq) {
    require_field(seq, "set_flow_id");
    auto& reg = internal::Registry::get();
    reg.flow_id     = seq;
    reg.flow_id_set = true;
}

void set_app_id(NB::FieldRef app) {
    require_field(app, "set_app_id");
    auto& reg = internal::Registry::get();
    reg.app_id     = app;
    reg.app_id_set = true;
}

}  // namespace SPAC
