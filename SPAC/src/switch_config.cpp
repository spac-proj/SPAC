#include "spac/switch_config.hpp"
#include "spac/registry.hpp"

#include <stdexcept>

namespace SPAC {

SwitchConfig::SwitchConfig() {
    auto& reg = internal::Registry::get();
    if (reg.switch_config != nullptr) {
        throw std::runtime_error(
            "SPAC::SwitchConfig: only a single SwitchConfig instance is "
            "supported per DSL program in this version.");
    }
    reg.switch_config = this;
}

SwitchConfig::~SwitchConfig() {
    auto& reg = internal::Registry::get();
    if (reg.switch_config == this) {
        reg.switch_config = nullptr;
    }
}

const char* to_string(HashPolicy p) {
    switch (p) {
    case HashPolicy::FullLookupTable: return "FullLookupTable";
    case HashPolicy::MultiBankHash:   return "MultiBankHash";
    }
    return "UNKNOWN";
}

const char* to_string(BufferPolicy p) {
    switch (p) {
    case BufferPolicy::OneBufferPerPort: return "OneBufferPerPort";
    case BufferPolicy::NBuffersPerPort:  return "NBuffersPerPort";
    }
    return "UNKNOWN";
}

const char* to_string(SchedulerType s) {
    switch (s) {
    case SchedulerType::iSLIP:      return "iSLIP";
    case SchedulerType::RoundRobin: return "RoundRobin";
    }
    return "UNKNOWN";
}

}  // namespace SPAC
