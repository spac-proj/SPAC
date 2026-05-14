#pragma once
#include <string>

namespace SPAC {
namespace codegen {

struct NetblocksArtifacts {
    std::string proto_txt_path;
    std::string gen_headers_path;
    std::string nb_proto_c_path;
};

NetblocksArtifacts build_netblocks_stack(const std::string& impl_cpp_path,
                                         const std::string& dst_nb_root);

}  // namespace codegen
}  // namespace SPAC
