// modiefied from ns3 existing code
/*
 * Copyright (c) 2007, 2008 University of Washington
 *
 * SPDX-License-Identifier: GPL-2.0-only
 */

#include "nb-p2p-channel.h"

#include "nb-p2p-net-device.h"

#include "ns3/log.h"
#include "ns3/packet.h"
#include "ns3/simulator.h"
#include "ns3/trace-source-accessor.h"

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("NbP2PChannel");

NS_OBJECT_ENSURE_REGISTERED(NbP2PChannel);

TypeId
NbP2PChannel::GetTypeId()
{
    static TypeId tid =
        TypeId("ns3::NbP2PChannel")
            .SetParent<Channel>()
            .SetGroupName("NbP2P")
            .AddConstructor<NbP2PChannel>()
            .AddAttribute("Delay",
                          "Propagation delay through the channel",
                          TimeValue(Seconds(0)),
                          MakeTimeAccessor(&NbP2PChannel::m_delay),
                          MakeTimeChecker())
            .AddTraceSource("TxRxNbP2P",
                            "Trace source indicating transmission of packet "
                            "from the NbP2PChannel, used by the Animation "
                            "interface.",
                            MakeTraceSourceAccessor(&NbP2PChannel::m_txrxNbP2P),
                            "ns3::NbP2PChannel::TxRxAnimationCallback");
    return tid;
}

//
// By default, you get a channel that
// has an "infitely" fast transmission speed and zero delay.
NbP2PChannel::NbP2PChannel()
    : Channel(),
      m_delay(),
      m_nDevices(0)
{
    NS_LOG_FUNCTION_NOARGS();
}

void
NbP2PChannel::Attach(Ptr<NbP2PNetDevice> device)
{
    NS_LOG_FUNCTION(this << device);
    NS_ASSERT_MSG(m_nDevices < N_DEVICES, "Only two devices permitted");
    NS_ASSERT(device);

    m_link[m_nDevices++].m_src = device;
    //
    // If we have both devices connected to the channel, then finish introducing
    // the two halves and set the links to IDLE.
    //
    if (m_nDevices == N_DEVICES)
    {
        m_link[0].m_dst = m_link[1].m_src;
        m_link[1].m_dst = m_link[0].m_src;
        m_link[0].m_state = IDLE;
        m_link[1].m_state = IDLE;
    }
}

bool
NbP2PChannel::TransmitStart(Ptr<const Packet> p, Ptr<NbP2PNetDevice> src, Time txTime)
{
    NS_LOG_FUNCTION(this << p << src);
    NS_LOG_LOGIC("UID is " << p->GetUid() << ")");

    NS_ASSERT(m_link[0].m_state != INITIALIZING);
    NS_ASSERT(m_link[1].m_state != INITIALIZING);

    uint32_t wire = src == m_link[0].m_src ? 0 : 1;

    Simulator::ScheduleWithContext(m_link[wire].m_dst->GetNode()->GetId(),
                                   txTime + m_delay,
                                   &NbP2PNetDevice::Receive,
                                   m_link[wire].m_dst,
                                   p->Copy());

    // Call the tx anim callback on the net device
    m_txrxNbP2P(p, src, m_link[wire].m_dst, txTime, txTime + m_delay);
    return true;
}

std::size_t
NbP2PChannel::GetNDevices() const
{
    NS_LOG_FUNCTION_NOARGS();
    return m_nDevices;
}

Ptr<NbP2PNetDevice>
NbP2PChannel::GetNbP2PDevice(std::size_t i) const
{
    NS_LOG_FUNCTION_NOARGS();
    NS_ASSERT(i < 2);
    return m_link[i].m_src;
}

Ptr<NetDevice>
NbP2PChannel::GetDevice(std::size_t i) const
{
    NS_LOG_FUNCTION_NOARGS();
    return GetNbP2PDevice(i);
}

Time
NbP2PChannel::GetDelay() const
{
    return m_delay;
}

Ptr<NbP2PNetDevice>
NbP2PChannel::GetSource(uint32_t i) const
{
    return m_link[i].m_src;
}

Ptr<NbP2PNetDevice>
NbP2PChannel::GetDestination(uint32_t i) const
{
    return m_link[i].m_dst;
}

bool
NbP2PChannel::IsInitialized() const
{
    NS_ASSERT(m_link[0].m_state != INITIALIZING);
    NS_ASSERT(m_link[1].m_state != INITIALIZING);
    return true;
}

} // namespace ns3
