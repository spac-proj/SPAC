#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include <type_traits>

namespace NB {

class Layout;

template <typename T>
struct field_traits {
    static_assert(std::is_integral<T>::value,
                  "NB::Layout fields must be of integral type "
                  "(uint8_t, uint16_t, uint32_t, uint64_t).");
    static constexpr int bits = static_cast<int>(sizeof(T)) * 8;
};

struct FieldRef {
    Layout* layout = nullptr;
    int     index  = -1;
    int     bits   = 0;
    bool valid() const { return layout != nullptr && index >= 0; }
};

}  // namespace NB
