#pragma once
#include "field.hpp"
#include "switch_config.hpp"

namespace NB { class Layout; }

namespace SPAC {
namespace internal {

struct Registry {
    NB::Layout*    layout         = nullptr;
    SwitchConfig*  switch_config  = nullptr;

    NB::FieldRef   routing_src    {};
    NB::FieldRef   routing_dst    {};
    NB::FieldRef   flow_id        {};
    NB::FieldRef   app_id         {};

    bool routing_key_set = false;
    bool flow_id_set     = false;
    bool app_id_set      = false;

    static Registry& get();
};

}  // namespace internal
}  // namespace SPAC
