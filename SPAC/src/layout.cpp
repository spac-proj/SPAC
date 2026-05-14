#include "spac/layout.hpp"
#include "spac/registry.hpp"

#include <stdexcept>

namespace NB {

Layout::Layout() {
    auto& reg = SPAC::internal::Registry::get();
    if (reg.layout != nullptr) {
        throw std::runtime_error(
            "NB::Layout: only a single Layout instance is supported per DSL "
            "program in this version.");
    }
    reg.layout = this;
}

Layout::~Layout() {
    auto& reg = SPAC::internal::Registry::get();
    if (reg.layout == this) {
        reg.layout = nullptr;
    }
}

FieldRef Layout::add_field_raw(const std::string& name, int bits) {
    if (bits <= 0) {
        throw std::runtime_error("NB::Layout::add_field: width must be > 0");
    }
    FieldInfo info;
    info.name = name;
    info.bits = bits;
    fields_.push_back(info);

    FieldRef ref;
    ref.layout = this;
    ref.index  = static_cast<int>(fields_.size()) - 1;
    ref.bits   = bits;
    return ref;
}

}  // namespace NB
