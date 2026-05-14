#include "ns3/net-device.h"
#include "nb-stack.h"
#include "nb_runtime.h"
#include "ns3/address.h"
#include "ns3/packet.h"
#include "nb-timer-manager.h"
#include "ns3/address.h"

ns3::Ptr<ns3::NetDevice> tls_device = nullptr;
ns3::Ptr<ns3::NbTimerManager> tls_timer_manager = nullptr;
  
// provide a function to get the current thread's NetDevice
void nb__ns3_set_device (ns3::Ptr<ns3::NetDevice> d) {
    tls_device = d;
}

void nb__ns3_set_timer_manager(ns3::Ptr<ns3::NbTimerManager> tm) {
    tls_timer_manager = tm;
}

void nb__ns3_set_host(unsigned int host_id) {
	// Set the thread host id
	nb__my_host_id = host_id;
}

void nb__ns3_set_local_host(unsigned long long local_host_id) {
	// Set the thread local host id
	nb__my_local_host_id = local_host_id;
}

void nb__ns3_set_state(nb__net_state_t* state) {
	// Set the thread local net state
	nb__net_state = state;
}

int nb__send_packet(char* buff, int len)
{
  if (!tls_device) {
    // error: "No NetDevice registered for this thread";
    return -1;
  }
  // wrap the buffer into a ns3::Packet
  ns3::Ptr<ns3::Packet> p = ns3::Create<ns3::Packet>( (uint8_t*)buff, len );
  bool ok = tls_device->Send ( p, ns3::Address(), 0);
  return ok ? len : -1;
}

char* nb__request_send_buffer(void) {
	// TODO: This extra space needs to come from the headroom, either directly 
	// call get_headroom or get it as a parameter
	return (char*)malloc(1024 + 32);
}

void* nb__return_send_buffer(char* p) {
	free(p);
}