# SPAC

SPAC is a small C++ DSL that emits a complete switch + driver bundle from a
single source file. A SPAC program describes:

1. **A custom protocol** (field names + widths) using `NB::Layout`.
2. **Semantic bindings** that connect protocol fields to switch routing
   (`SPAC::set_routing_key`, `SPAC::set_flow_id`, `SPAC::set_app_id`).
3. **Switch architecture** choices (`SPAC::SwitchConfig`) - which scheduler,
   hash module and buffer the HLS switch should be built around.

Running the compiled program writes a self-contained output directory:

```
out_dir/
├── hls/              # HLS template parameterised for this protocol
│   ├── include/      #   common.hpp + per-protocol packet.hpp + ...
│   ├── src/          #   rx_engine.cpp uses get_src / get_dst now
│   └── run_hls.tcl
└── netblocks/        # Net-Blocks driver + transport + Makefile.frag
    ├── nb_proto.c
    ├── gen_headers.h
    ├── nb_runtime.{c,h}, nb_timer.{c,h}, nb_ipc_transport.c, nb_data_queue.h
    └── Makefile.frag
```

---

## Building

The DSL needs Net-Blocks already compiled (it links against
`libnet_blocks.a` + `libbuildit.a`):

```
cd ../net-blocks  &&  make -C buildit -j  &&  make -j
cd ../SPAC        &&  make -j
```

This produces:
- `build/libspac.a`
- `build/demo_clean`
- `build/demo_rr`

---

## Writing a SPAC program

```cpp
#include <spac/spac.hpp>
#include <cstdint>

int main() {
    // 1. Custom protocol
    NB::Layout pkt;
    auto src = pkt.add_field<uint8_t>("src");
    auto dst = pkt.add_field<uint8_t>("dst");
    auto seq = pkt.add_field<uint8_t>("seq");

    // 2. Semantic bindings
    SPAC::set_routing_key(src, dst);
    SPAC::set_flow_id(seq);            // optional
    // SPAC::set_app_id(...);          // optional - default keeps net-blocks' 16-bit app_id

    // 3. Switch architecture
    SPAC::SwitchConfig sw;
    sw.hash_policy   = SPAC::HashPolicy::FullLookupTable;   // or MultiBankHash
    sw.buffer_policy = SPAC::BufferPolicy::NBuffersPerPort; // or OneBufferPerPort
    sw.scheduler     = SchedulerType::iSLIP;                // or RoundRobin
    sw.num_ports     = 4;

    // 4. Emit
    SPAC::compile_lib(seq, "./out_demo");
    return 0;
}
```

`SPAC::Auto` is not supported in this version - the user must pick concrete enum
values(you can use our python simulator to do dse).  

---

## Run Flow

`SPAC::compile_lib(seq, out_dir)`:

1. Validates the registered DSL state.
2. Emits `out_dir/.spac_scratch/spac_impl.cpp` from a tiny.cpp-style template.
3. Compiles + runs that program against `libnet_blocks.a` + `libbuildit.a`.
   The program writes:
   - `gen_headers.h`     (Net-Blocks connection layout)
   - `nb_proto.c`        (the generated driver)
   - `proto.txt`         (per-field bit layout dump)
4. Reads the headroom from `gen_headers.h` and the field offsets from
   `proto.txt`, then writes `out_dir/hls/include/packet.hpp` with concrete
   accessors.
5. Copies the HLS source tree into `out_dir/hls/`, keeping only the picked
   scheduler variant and substituting the chosen enums into `common.hpp`.
6. Copies the Net-Blocks runtime files (`nb_runtime.{c,h}`,
   `nb_timer.{c,h}`, `nb_ipc_transport.c`, `nb_data_queue.h`) to
   `out_dir/netblocks/` and emits a `Makefile.frag`.

---

## Limitations / future work

- `SPAC::Auto`, `SPAC::PerfModel`, in-network kernel attachment are stubbed
  (the latter as no-op chains) - explicit configuration only.
- The DSL emits a "tiny" Net-Blocks stack (no reliability / checksum /
  routing). To enable any of those, extend `set_*` knobs and the codegen in
  `src/codegen/impl_cpp.cpp`.
- Connection setup currently uses Net-Blocks signaling, which needs ports
  `(8080, 8081, ...)` to fit inside the configured app-id width. If you call
  `set_app_id(field)` with a small width, pick test ports that fit.

