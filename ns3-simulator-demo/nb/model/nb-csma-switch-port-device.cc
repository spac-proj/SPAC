#include "nb-csma-switch-port-device.h"
#include "nb-csma-switch-stack.h"
#include "ns3/log.h"
#include "ns3/simulator.h"
#include "ns3/drop-tail-queue.h"
#include "ns3/mac48-address.h"
#include "ns3/uinteger.h"

namespace ns3 {

NS_LOG_COMPONENT_DEFINE ("NbCsmaSwitchPortDevice");
NS_OBJECT_ENSURE_REGISTERED (NbCsmaSwitchPortDevice);

TypeId
NbCsmaSwitchPortDevice::GetTypeId ()
{
    static TypeId tid = TypeId ("ns3::NbCsmaSwitchPortDevice")
                            .SetParent<NbCsmaNetDevice> ()
                            .SetGroupName ("Nb")
                            .AddConstructor<NbCsmaSwitchPortDevice> ();
    return tid;
}

NbCsmaSwitchPortDevice::NbCsmaSwitchPortDevice ()
    : m_stack (nullptr)
    //   m_isBusy (false)
{
    NS_LOG_FUNCTION (this);

    // 1. Create a tiny internal queue (capacity = 1) to satisfy NbCsmaNetDevice
    Ptr<DropTailQueue<Packet>> q = CreateObject<DropTailQueue<Packet>> ();
    q->SetAttribute ("MaxSize", QueueSizeValue (QueueSize ("1p")));
    SetQueue (q);

    // 2. Connect to the PhyTxEnd trace so we know when the transmission really finished
    //    This gives us an accurate "port became idle" event.
    m_phyTxEndTrace.ConnectWithoutContext (MakeCallback (&NbCsmaSwitchPortDevice::OnPhyTxEnd, this));
}

void
NbCsmaSwitchPortDevice::SetStack (Ptr<NbCsmaSwitchStack> stack)
{
    m_stack = stack;
}

bool
NbCsmaSwitchPortDevice::SendFromStack (Ptr<Packet> packet)
{
    NS_LOG_FUNCTION (this << packet);

    if (m_txMachineState != READY)
    {
        printf("NbCsmaSwitchPortDevice is busy; cannot send now\n");
        NS_LOG_WARN ("NbCsmaSwitchPortDevice is busy; cannot send now");
        return false;
    }

    // Mark as busy before handing to lower layer
    // m_isBusy = true;
    m_currentPkt = packet;           // protected
    TransmitStart();
    return true;
}

bool
NbCsmaSwitchPortDevice::IsBusy () const
{
    return m_txMachineState != READY;;
}

void
NbCsmaSwitchPortDevice::NotifyIdleLater ()
{
    if (m_txMachineState == READY && m_stack) {
        printf("Recal Switch, PortBecameIdle! time: %.6f\n", Simulator::Now().GetSeconds());
        m_stack->PortBecameIdle (this);
    }
    else {
        Simulator::Schedule (NanoSeconds (1), &NbCsmaSwitchPortDevice::NotifyIdleLater, this);
    }
}

void
NbCsmaSwitchPortDevice::OnPhyTxEnd (Ptr<const Packet> /*pkt*/)
{
    NS_LOG_FUNCTION (this);
    // Transmission is physically finished; wait the gap before ready for next transmission 
    if (m_stack) {
        Simulator::Schedule (m_tInterframeGap, &NbCsmaSwitchPortDevice::NotifyIdleLater, this);
    }
}

} // namespace ns3
