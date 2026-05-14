#include "nb-p2p-switch-port-device.h"
#include "nb-p2p-switch-stack.h"
#include "ns3/log.h"
#include "ns3/simulator.h"
#include "ns3/drop-tail-queue.h"
#include "ns3/mac48-address.h"
#include "ns3/uinteger.h"

namespace ns3 {

NS_LOG_COMPONENT_DEFINE ("NbP2PSwitchPortDevice");
NS_OBJECT_ENSURE_REGISTERED (NbP2PSwitchPortDevice);

TypeId
NbP2PSwitchPortDevice::GetTypeId ()
{
    static TypeId tid = TypeId ("ns3::NbP2PSwitchPortDevice")
                            .SetParent<NbP2PNetDevice> ()
                            .SetGroupName ("Nb")
                            .AddConstructor<NbP2PSwitchPortDevice> ();
    return tid;
}

NbP2PSwitchPortDevice::NbP2PSwitchPortDevice ()
    : m_stack (nullptr)
    //   m_isBusy (false)
{
    NS_LOG_FUNCTION (this);

    // 1. Create a tiny internal queue (capacity = 1) to satisfy NbP2PDevice
    Ptr<DropTailQueue<Packet>> q = CreateObject<DropTailQueue<Packet>> ();
    q->SetAttribute ("MaxSize", QueueSizeValue (QueueSize ("1p")));
    SetQueue (q);

    // 2. Connect to the PhyTxEnd trace so we know when the transmission really finished
    //    This gives us an accurate "port became idle" event.
    m_phyTxEndTrace.ConnectWithoutContext (MakeCallback (&NbP2PSwitchPortDevice::OnPhyTxEnd, this));
}

void
NbP2PSwitchPortDevice::SetStack (Ptr<NbP2PSwitchStack> stack)
{
    m_stack = stack;
}

bool
NbP2PSwitchPortDevice::SendFromStack (Ptr<Packet> packet)
{
    NS_LOG_FUNCTION (this << packet);

    if (m_txMachineState != READY)
    {
        printf("NbP2PSwitchPortDevice is busy; cannot send now\n");
        NS_LOG_WARN ("NbP2PSwitchPortDevice is busy; cannot send now");
        return false;
    }

    return TransmitStart(packet);
}

bool
NbP2PSwitchPortDevice::IsBusy () const
{
    return m_txMachineState != READY;;
}

void
NbP2PSwitchPortDevice::NotifyIdleLater ()
{
    if (m_txMachineState == READY && m_stack) {
        printf("Recal Switch, PortBecameIdle! time: %.6f\n", Simulator::Now().GetSeconds());
        m_stack->PortBecameIdle (this);
    }
    else {
        Simulator::Schedule (NanoSeconds (1), &NbP2PSwitchPortDevice::NotifyIdleLater, this);
    }
}

void
NbP2PSwitchPortDevice::OnPhyTxEnd (Ptr<const Packet> /*pkt*/)
{
    NS_LOG_FUNCTION (this);
    // Transmission is physically finished; wait the gap before ready for next transmission 
    if (m_stack) {
        Simulator::Schedule (m_tInterframeGap, &NbP2PSwitchPortDevice::NotifyIdleLater, this);
    }
}

} // namespace ns3
