#include "nb-stack.h"
#include "ns3/log.h"
#include "ns3/simulator.h"
#include "ns3/uinteger.h"
#include "nb_runtime.h"
#include <unordered_map>



namespace ns3 {

extern "C" void
NbStackCbWrapper (int event, nb__connection_t* c)
{
    void* ud = nb__get_user_data(c);
    if (ud) {
        static_cast<NbStack*>(ud)->OnEvent(event, c);
    }
}

NS_LOG_COMPONENT_DEFINE("NbStack");
NS_OBJECT_ENSURE_REGISTERED(NbStack);

TypeId
NbStack::GetTypeId()
{
    static TypeId tid = TypeId ("ns3::NbStack")
    .SetParent<Object> ()
    .SetGroupName ("Nb")
    .AddConstructor<NbStack> ()
    .AddAttribute ("HostId",
                   "host id",
                   UintegerValue (0),
                   MakeUintegerAccessor (&NbStack::m_hostId),
                   MakeUintegerChecker<uint32_t> ())
    // if tracing event
    //.AddTraceSource ("TxPacket", "...", MakeTraceSourceAccessor (&NetBlockStack::m_txTrace))
    ;
    return tid;
}

bool NbStack::OnDeviceReceive(Ptr<NetDevice> dev, Ptr<const Packet> p, uint16_t protocol, const Address& from)
{
    // This function is called when a packet is received by the device
    // Here we can handle the packet as needed
    NS_LOG_FUNCTION(this << dev << p << protocol << from);
    
    SetNbParameters();
    uint32_t size = p->GetSize();
    std::unique_ptr<uint8_t[]> buffer(new uint8_t[size + nb__packet_headroom]);
    p->CopyData(buffer.get() + nb__packet_headroom, size);
    // printf("Received: begin running ingress step, size=%u\n", size);
    // printf("num conn: %d\n", nb__net_state->num_conn);
    // printf("app id 0: %u\n", nb__net_state->active_local_app_ids[0]);
    // printf("app id 1: %u\n", nb__net_state->active_local_app_ids[1]);
    // printf("remote app id 0: %u\n", nb__net_state->active_remote_app_ids[0]);
    // printf("remote app id 1: %u\n", nb__net_state->active_remote_app_ids[1]);
    nb__run_ingress_step(buffer.get(), size);
    nb__cycle_connections(); // Process potential callbacks
    return true; // Indicate that the packet was processed
}

NbStack::NbStack(uint32_t hostId, Ptr<NetDevice> dev)
  : m_hostId(hostId),
    m_localHostId(0),
    m_state(nullptr),
    m_dev(dev),
    m_timerManager(CreateObject<NbTimerManager>()), 
    m_callbacks() {}

NbStack::NbStack()
  : m_hostId(0),
    m_localHostId(0),
    m_state(nullptr),
    m_dev(nullptr),
    m_timerManager(CreateObject<NbTimerManager>()), 
    m_callbacks() {}

NbStack::~NbStack() 
{
  if (m_cycleEvent.IsPending()) {
    Simulator::Cancel(m_cycleEvent);
  }
}

void
NbStack::InitTransport() 
{
}

void
NbStack::DeinitTransport() 
{
}

void
NbStack::StackInit() 
{
  SetNbParameters();
  nb__net_init ();
  m_localHostId = nb__my_local_host_id;
  m_state = nb__net_state;
  if (m_dev != nullptr) {
    m_dev -> SetReceiveCallback (
      MakeCallback (&NbStack::OnDeviceReceive, this));
  }
  // below is no longer needed, as we will explicitly call cycle connection after establish/receive
  // m_cycleEvent = Simulator::Schedule(MilliSeconds(1), &NbStack::CycleConnections, this);
}

nb__connection_t*
NbStack::Establish (
    uint64_t   remoteHostId,
    uint32_t   remoteAppId,
    uint32_t   localAppId,
    CallbackT  cb) 
{
  SetNbParameters();
  nb__connection_t* conn =
    nb__establish (remoteHostId, remoteAppId, localAppId,
                   &NbStackCbWrapper);
  m_callbacks[conn] = std::move (cb);
  nb__set_user_data(conn, this); // Set user data to this instance for callback
  nb__cycle_connections(); // Process potential callbacks
  return conn;
}

void
NbStack::Destablish(nb__connection_t* conn) 
{
  SetNbParameters();
  nb__destablish(conn);
  m_callbacks.erase(conn);
  nb__set_user_data(conn, nullptr); // Clear user data
}

nb__connection_t*
NbStack::Accept (
    nb__connection_t* listenConn,
    CallbackT         cb)
{
  printf("NbStack::Accept\n");
  SetNbParameters();
  nb__connection_t* conn =
    nb__accept(listenConn, &NbStackCbWrapper);
  m_callbacks[conn] = std::move (cb);
  nb__set_user_data(conn, this); // Set user data to this instance for callback
  nb__cycle_connections(); // Process potential callbacks
  return conn;
}

void
NbStack::OnEvent(int event, nb__connection_t* conn) 
{
  auto it = m_callbacks.find(conn);
  if (it != m_callbacks.end()) {
    // Call the callback function with the event and connection
    it->second(event, conn);
  } else {
    NS_LOG_ERROR("No callback found for connection " << conn);
  }
}

// void NbStack::CycleConnections() {
//   SetNbParameters();
//   nb__cycle_connections();
//   m_cycleEvent = Simulator::Schedule(
//     MilliSeconds(1), &NbStack::CycleConnections, this);
// }

// I/O interface

int
NbStack::Send(nb__connection_t* conn,
              const char*       buf,
              int               len)
{
  SetNbParameters();
  printf("NbStack Send Request Info: From = %u, To = %llu, time = %.6f\n",
         m_hostId, conn->remote_host_id, Simulator::Now().GetSeconds());
  return nb__send(conn, const_cast<char*>(buf), len);
}

int
NbStack::Read(nb__connection_t* conn,
              char*             buf,
              int               maxLen)
{
  SetNbParameters();
  return nb__read(conn, buf, maxLen);
}

}