#pragma once
#include <string>

namespace SPAC {
namespace codegen {

void write_packet_hpp(const std::string& proto_txt_path,
                      const std::string& gen_headers_path,
                      const std::string& out_packet_hpp_path);

}  // namespace codegen
}  // namespace SPAC
