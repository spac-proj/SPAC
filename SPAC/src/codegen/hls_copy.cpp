#include "spac/codegen/hls_copy.hpp"
#include "spac/registry.hpp"
#include "spac/switch_config.hpp"

#include <filesystem>
#include <fstream>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#ifndef SPAC_HLS_ROOT
#  error "SPAC_HLS_ROOT must be defined at compile time (set by SPAC Makefile)"
#endif

namespace SPAC {
namespace codegen {

namespace fs = std::filesystem;

namespace {

void copy_file_into(const fs::path& src, const fs::path& dst) {
    if (!fs::exists(src)) {
        throw std::runtime_error("Missing HLS template file: " + src.string());
    }
    fs::create_directories(dst.parent_path());
    fs::copy_file(src, dst, fs::copy_options::overwrite_existing);
}

std::string read_text(const fs::path& path) {
    std::ifstream is(path);
    std::stringstream buf;
    buf << is.rdbuf();
    return buf.str();
}

void write_text(const fs::path& path, const std::string& body) {
    std::ofstream os(path);
    os << body;
}

// Returns true if a `constexpr <type> NAME = <rhs>;` declaration was found
// (regardless of whether the value actually changed), so callers can detect
// missing names instead of silent no-ops.
bool patch_constexpr(std::string& body,
                     const std::string& name,
                     const std::string& value) {
    const std::string pattern =
        R"((constexpr\s+[A-Za-z_][A-Za-z0-9_:<>\s]*?\s+))"
        + name +
        R"(\s*=\s*[^;]+;)";
    const std::regex pat(pattern);
    if (!std::regex_search(body, pat)) {
        return false;
    }
    body = std::regex_replace(body, pat,
                              std::string("$1") + name + " = " + value + ";");
    return true;
}

const std::string& netblocks_scheduler_filename(SchedulerType s,
                                                BufferPolicy  b) {
    static const std::string sched_islip   = "scheduler_iSLIP.cpp";
    static const std::string sched_rr_1b1p = "scheduler.cpp";
    static const std::string sched_rr_nb1p = "scheduler_nb1p.cpp";

    if (s == SchedulerType::iSLIP) return sched_islip;
    if (b == BufferPolicy::OneBufferPerPort) return sched_rr_1b1p;
    return sched_rr_nb1p;
}

}  // namespace

void emit_hls_tree(const std::string& dst_hls_root) {
    auto& reg = internal::Registry::get();
    if (reg.switch_config == nullptr) {
        throw std::runtime_error(
            "compile_lib: no SPAC::SwitchConfig was instantiated.");
    }
    const auto& cfg = *reg.switch_config;

    const fs::path src_root  = SPAC_HLS_ROOT;
    const fs::path dst_root  = dst_hls_root;
    const fs::path dst_inc   = dst_root / "include";
    const fs::path dst_src   = dst_root / "src";

    fs::create_directories(dst_inc);
    fs::create_directories(dst_src);

    static const std::vector<std::string> always_headers = {
        "rx_engine.hpp", "hash_engine.hpp",
        "scheduler.hpp", "switch_top.hpp",
    };
    for (const auto& h : always_headers) {
        copy_file_into(src_root / "include" / h, dst_inc / h);
    }

    {
        std::string body = read_text(src_root / "include" / "common.hpp");

        std::ostringstream hash_v;   hash_v   << "HashModuleType::"
            << ((cfg.hash_policy == HashPolicy::FullLookupTable)
                    ? "FullLookupTable" : "MultiBankHash");
        std::ostringstream buffer_v; buffer_v << "BufferType::"
            << ((cfg.buffer_policy == BufferPolicy::OneBufferPerPort)
                    ? "OneBufferPerPort" : "NBuffersPerPort");
        std::ostringstream sched_v;  sched_v  << "SchedulerType::"
            << ((cfg.scheduler == SchedulerType::iSLIP)
                    ? "iSLIP" : "RoundRobin");

        bool any = false;
        any |= patch_constexpr(body, "HASH_MODULE_TYPE",    hash_v.str());
        any |= patch_constexpr(body, "BUFFER_TYPE",         buffer_v.str());
        any |= patch_constexpr(body, "SCHEDULER_TYPE",      sched_v.str());
        any |= patch_constexpr(body, "NUM_PORTS",
                               std::to_string(cfg.num_ports));
        any |= patch_constexpr(body, "MAX_QUEUE_DEPTH_LOG",
                               std::to_string(cfg.max_queue_depth_log));
        any |= patch_constexpr(body, "HASH_BITS",
                               std::to_string(cfg.hash_bits));
        if (!any) {
            throw std::runtime_error(
                "common.hpp patching failed: no constexpr matched.");
        }
        write_text(dst_inc / "common.hpp", body);
    }

    static const std::vector<std::string> always_srcs = {
        "rx_engine.cpp", "hash_engine.cpp", "switch_top.cpp",
    };
    for (const auto& s : always_srcs) {
        copy_file_into(src_root / "src" / s, dst_src / s);
    }

    const auto& sched = netblocks_scheduler_filename(cfg.scheduler,
                                                     cfg.buffer_policy);
    copy_file_into(src_root / "src" / sched, dst_src / sched);

    for (const char* tcl : {"run_hls.tcl", "run_hls_cosim.tcl"}) {
        const fs::path candidate = src_root / tcl;
        if (fs::exists(candidate)) {
            copy_file_into(candidate, dst_root / tcl);
        }
    }
}

}  // namespace codegen
}  // namespace SPAC
