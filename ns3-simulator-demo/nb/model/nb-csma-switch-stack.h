#ifndef NB_CSMA_SWITCH_STACK_H
#define NB_CSMA_SWITCH_STACK_H

#include "ns3/object.h"
#include "nb-csma-switch-port-device.h"
#include "ns3/queue.h"
#include "ns3/ptr.h"
#include "ns3/packet.h"
#include "ns3/nstime.h"
#include "ns3/event-id.h"
#include <vector>
#include <unordered_map>

// C-helpers (nb_simple.c)
extern "C" {
unsigned int nb__get_src_host_id (void* p);
unsigned int nb__get_dst_host_id (void* p);
}

namespace ns3 {

class NbCsmaSwitchStack : public Object
{
public:
    static TypeId GetTypeId ();

    NbCsmaSwitchStack ();
    ~NbCsmaSwitchStack () override;

    void AttachPort (Ptr<NbCsmaSwitchPortDevice> port);
    void PortBecameIdle (Ptr<NbCsmaSwitchPortDevice> port);

private:
    using PortId = uint32_t;
    using HostId = uint32_t;

    bool OnDeviceReceive (Ptr<NetDevice> dev,
                          Ptr<const Packet> pkt,
                          uint16_t proto,
                          const Address& from);

    void Enqueue   (PortId in, PortId out, Ptr<Packet> pkt);
    void Arbitrate ();                  // Full iSLIP
    void CleanFwdTable ();

    std::vector< Ptr<NbCsmaSwitchPortDevice> >                m_ports;
    std::unordered_map< Ptr<NbCsmaSwitchPortDevice>, PortId > m_portIndex;
    std::vector< std::vector< Ptr<Queue<Packet>> > >      m_voq;     // [in][out]

    std::vector< PortId > m_nextOut;  // per-input  RR pointer
    std::vector< PortId > m_nextIn;   // per-output RR pointer

    std::unordered_map< HostId, PortId > m_fwd;
    std::unordered_map< HostId, Time >   m_fwdTime;

    Time m_entryTimeout { Seconds (300) };

    EventId m_cleanupEvent;
};

} // namespace ns3
#endif // NB_SWITCH_STACK_H