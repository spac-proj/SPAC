// Custom Protocol
NB::Layout pkt;
auto src = pkt.add_field<uint8_t>(”src");
auto dst = pkt.add_field<uint8_t>(”dst");
auto seq =pkt.add_field<uint8_t>(”seq");

// Semantic Binding
SPAC::set_routing_key(src,dst); 
SPAC::set_flow_id(seq);
SPAC::compile_lib(seq);

// Switch Architecture
SPAC::SwitchConfig sw;
// Register vs. BRAM vs. CAM
sw.hash_policy = SPAC::Auto; 
// Distributed vs. Shared Mem
sw.buffer_policy = SPAC::Auto;
// Manual override to iSLIP
sw.scheduler = SchedulerType::iSLIP; 
// InNetwork Computing sw.attach_kernel("agg_top", "src/agg_kernel.cpp")
  .performance(SPAC::PerfModel(...));
