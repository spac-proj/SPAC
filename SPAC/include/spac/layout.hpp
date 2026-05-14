#pragma once
#include "field.hpp"

#include <string>
#include <vector>

namespace NB {

struct FieldInfo {
    std::string name;
    int         bits;
};

class Layout {
public:
    Layout();
    ~Layout();

    template <typename T>
    FieldRef add_field(const std::string& name) {
        return add_field_raw(name, field_traits<T>::bits);
    }

    const std::vector<FieldInfo>& fields() const { return fields_; }

    Layout(const Layout&)            = delete;
    Layout& operator=(const Layout&) = delete;

private:
    FieldRef add_field_raw(const std::string& name, int bits);
    std::vector<FieldInfo> fields_;
};

}  // namespace NB
