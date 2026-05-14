#include "spac/binding.hpp"
#include "spac/registry.hpp"
#include "spac/layout.hpp"

#include "spac/codegen/impl_cpp.hpp"
#include "spac/codegen/packet_hpp.hpp"
#include "spac/codegen/hls_copy.hpp"
#include "spac/codegen/netblocks.hpp"

#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>

namespace SPAC {

namespace fs = std::filesystem;

namespace {

void validate(const NB::FieldRef& seq_hint) {
    auto& reg = internal::Registry::get();
    if (reg.layout == nullptr) {
        throw std::runtime_error(
            "compile_lib: no NB::Layout has been instantiated.");
    }
    if (reg.switch_config == nullptr) {
        throw std::runtime_error(
            "compile_lib: no SPAC::SwitchConfig has been instantiated.");
    }
    if (!reg.routing_key_set) {
        throw std::runtime_error(
            "compile_lib: SPAC::set_routing_key was never called.");
    }
    if (!seq_hint.valid()) {
        throw std::runtime_error(
            "compile_lib: seq_hint FieldRef is not valid.");
    }
}

}  // namespace

void compile_lib(NB::FieldRef seq_hint, const std::string& output_dir) {
    validate(seq_hint);

    // seq_hint is treated as set_flow_id() unless the user already set one,
    // matching the demo.cpp shorthand `compile_lib(seq, dir)`.
    auto& reg = internal::Registry::get();
    if (!reg.flow_id_set) {
        reg.flow_id     = seq_hint;
        reg.flow_id_set = true;
    }

    const fs::path out_root = output_dir;
    const fs::path hls_root = out_root / "hls";
    const fs::path nb_root  = out_root / "netblocks";
    fs::create_directories(hls_root / "include");
    fs::create_directories(hls_root / "src");
    fs::create_directories(nb_root);

    const fs::path scratch = out_root / ".spac_scratch";
    fs::create_directories(scratch);
    const fs::path impl_cpp = scratch / "spac_impl.cpp";

    codegen::write_netblocks_impl_cpp(impl_cpp.string());
    auto art = codegen::build_netblocks_stack(impl_cpp.string(),
                                              nb_root.string());
    codegen::write_packet_hpp(art.proto_txt_path,
                              art.gen_headers_path,
                              (hls_root / "include" / "packet.hpp").string());
    codegen::emit_hls_tree(hls_root.string());

    std::cout << "[SPAC] Generation complete.\n"
              << "[SPAC] HLS tree:           " << hls_root  << "\n"
              << "[SPAC] net-blocks driver:  " << nb_root   << "\n"
              << "[SPAC] proto layout dump:  " << art.proto_txt_path
              << "\n";
}

}  // namespace SPAC
