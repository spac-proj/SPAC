#include "spac/registry.hpp"

namespace SPAC {
namespace internal {

Registry& Registry::get() {
    static Registry instance;
    return instance;
}

}  // namespace internal
}  // namespace SPAC
