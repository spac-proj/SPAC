#pragma once
#include <string>
#include <utility>

namespace SPAC {

enum class HashPolicy    { FullLookupTable, MultiBankHash };
enum class BufferPolicy  { OneBufferPerPort, NBuffersPerPort };
enum class SchedulerType { iSLIP, RoundRobin };

struct PerfModel {
    template <typename... Args>
    PerfModel(Args&&...) {}
};

struct SwitchConfig {
    HashPolicy    hash_policy        = HashPolicy::FullLookupTable;
    BufferPolicy  buffer_policy      = BufferPolicy::NBuffersPerPort;
    SchedulerType scheduler          = SchedulerType::iSLIP;
    int           num_ports          = 4;
    int           max_queue_depth_log = 3;
    int           hash_bits          = 7;

    SwitchConfig& attach_kernel(const std::string&, const std::string&) {
        return *this;
    }
    template <typename T>
    SwitchConfig& performance(T&&) { return *this; }

    SwitchConfig();
    ~SwitchConfig();
    SwitchConfig(const SwitchConfig&)            = delete;
    SwitchConfig& operator=(const SwitchConfig&) = delete;
};

const char* to_string(HashPolicy);
const char* to_string(BufferPolicy);
const char* to_string(SchedulerType);

}  // namespace SPAC

using SchedulerType = SPAC::SchedulerType;
