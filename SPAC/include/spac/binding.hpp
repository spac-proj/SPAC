#pragma once
#include "field.hpp"

#include <string>

namespace SPAC {

void set_routing_key(NB::FieldRef src, NB::FieldRef dst);
void set_flow_id    (NB::FieldRef seq);
void set_app_id     (NB::FieldRef app);

void compile_lib(NB::FieldRef seq_hint, const std::string& output_dir);

}  // namespace SPAC
