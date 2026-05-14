// modiefied from ns3 existing code
/*
 * Copyright (c) 2007, 2008 University of Washington
 *
 * SPDX-License-Identifier: GPL-2.0-only
 */

#include "nb-p2p-net-device.h"

#include "nb-p2p-channel.h"

#include "ns3/error-model.h"
#include "ns3/llc-snap-header.h"
#include "ns3/log.h"
#include "ns3/mac48-address.h"
#include "ns3/pointer.h"
#include "ns3/queue.h"
#include "ns3/simulator.h"
#include "ns3/trace-source-accessor.h"
#include "ns3/uinteger.h"

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("NbP2PNetDevice");

NS_OBJECT_ENSURE_REGISTERED(NbP2PNetDevice);

TypeId
NbP2PNetDevice::GetTypeId()
{
    static TypeId tid =
        TypeId("ns3::NbP2PNetDevice")
            .SetParent<NetDevice>()
            .SetGroupName("NbP2P")
            .AddConstructor<NbP2PNetDevice>()
            .AddAttribute("Mtu",
                          "The MAC-level Maximum Transmission Unit",
                          UintegerValue(DEFAULT_MTU),
                          MakeUintegerAccessor(&NbP2PNetDevice::SetMtu,
                                               &NbP2PNetDevice::GetMtu),
                          MakeUintegerChecker<uint16_t>())
            // .AddAttribute("Address",
            //               "The MAC address of this device.",
            //               Mac48AddressValue(Mac48Address("ff:ff:ff:ff:ff:ff")),
            //               MakeMac48AddressAccessor(&NbP2PNetDevice::m_address),
            //               MakeMac48AddressChecker())
            .AddAttribute("DataRate",
                          "The default data rate for point to point links",
                          DataRateValue(DataRate("32768b/s")),
                          MakeDataRateAccessor(&NbP2PNetDevice::m_bps),
                          MakeDataRateChecker())
            .AddAttribute("ReceiveErrorModel",
                          "The receiver error model used to simulate packet loss",
                          PointerValue(),
                          MakePointerAccessor(&NbP2PNetDevice::m_receiveErrorModel),
                          MakePointerChecker<ErrorModel>())
            .AddAttribute("InterframeGap",
                          "The time to wait between packet (frame) transmissions",
                          TimeValue(Seconds(0)),
                          MakeTimeAccessor(&NbP2PNetDevice::m_tInterframeGap),
                          MakeTimeChecker())

            //
            // Transmit queueing discipline for the device which includes its own set
            // of trace hooks.
            //
            .AddAttribute("TxQueue",
                          "A queue to use as the transmit queue in the device.",
                          PointerValue(),
                          MakePointerAccessor(&NbP2PNetDevice::m_queue),
                          MakePointerChecker<Queue<Packet>>())

            //
            // Trace sources at the "top" of the net device, where packets transition
            // to/from higher layers.
            //
            .AddTraceSource("MacTx",
                            "Trace source indicating a packet has arrived "
                            "for transmission by this device",
                            MakeTraceSourceAccessor(&NbP2PNetDevice::m_macTxTrace),
                            "ns3::Packet::TracedCallback")
            .AddTraceSource("MacTxDrop",
                            "Trace source indicating a packet has been dropped "
                            "by the device before transmission",
                            MakeTraceSourceAccessor(&NbP2PNetDevice::m_macTxDropTrace),
                            "ns3::Packet::TracedCallback")
            .AddTraceSource("MacPromiscRx",
                            "A packet has been received by this device, "
                            "has been passed up from the physical layer "
                            "and is being forwarded up the local protocol stack.  "
                            "This is a promiscuous trace,",
                            MakeTraceSourceAccessor(&NbP2PNetDevice::m_macPromiscRxTrace),
                            "ns3::Packet::TracedCallback")
            .AddTraceSource("MacRx",
                            "A packet has been received by this device, "
                            "has been passed up from the physical layer "
                            "and is being forwarded up the local protocol stack.  "
                            "This is a non-promiscuous trace,",
                            MakeTraceSourceAccessor(&NbP2PNetDevice::m_macRxTrace),
                            "ns3::Packet::TracedCallback")
#if 0
    // Not currently implemented for this device
    .AddTraceSource ("MacRxDrop",
                     "Trace source indicating a packet was dropped "
                     "before being forwarded up the stack",
                     MakeTraceSourceAccessor (&NbP2PNetDevice::m_macRxDropTrace),
                     "ns3::Packet::TracedCallback")
#endif
            //
            // Trace sources at the "bottom" of the net device, where packets transition
            // to/from the channel.
            //
            .AddTraceSource("PhyTxBegin",
                            "Trace source indicating a packet has begun "
                            "transmitting over the channel",
                            MakeTraceSourceAccessor(&NbP2PNetDevice::m_phyTxBeginTrace),
                            "ns3::Packet::TracedCallback")
            .AddTraceSource("PhyTxEnd",
                            "Trace source indicating a packet has been "
                            "completely transmitted over the channel",
                            MakeTraceSourceAccessor(&NbP2PNetDevice::m_phyTxEndTrace),
                            "ns3::Packet::TracedCallback")
            .AddTraceSource("PhyTxDrop",
                            "Trace source indicating a packet has been "
                            "dropped by the device during transmission",
                            MakeTraceSourceAccessor(&NbP2PNetDevice::m_phyTxDropTrace),
                            "ns3::Packet::TracedCallback")
#if 0
    // Not currently implemented for this device
    .AddTraceSource ("PhyRxBegin",
                     "Trace source indicating a packet has begun "
                     "being received by the device",
                     MakeTraceSourceAccessor (&NbP2PNetDevice::m_phyRxBeginTrace),
                     "ns3::Packet::TracedCallback")
#endif
            .AddTraceSource("PhyRxEnd",
                            "Trace source indicating a packet has been "
                            "completely received by the device",
                            MakeTraceSourceAccessor(&NbP2PNetDevice::m_phyRxEndTrace),
                            "ns3::Packet::TracedCallback")
            .AddTraceSource("PhyRxDrop",
                            "Trace source indicating a packet has been "
                            "dropped by the device during reception",
                            MakeTraceSourceAccessor(&NbP2PNetDevice::m_phyRxDropTrace),
                            "ns3::Packet::TracedCallback")

            //
            // Trace sources designed to simulate a packet sniffer facility (tcpdump).
            // Note that there is really no difference between promiscuous and
            // non-promiscuous traces in a point-to-point link.
            //
            .AddTraceSource("Sniffer",
                            "Trace source simulating a non-promiscuous packet sniffer "
                            "attached to the device",
                            MakeTraceSourceAccessor(&NbP2PNetDevice::m_snifferTrace),
                            "ns3::Packet::TracedCallback")
            .AddTraceSource("PromiscSniffer",
                            "Trace source simulating a promiscuous packet sniffer "
                            "attached to the device",
                            MakeTraceSourceAccessor(&NbP2PNetDevice::m_promiscSnifferTrace),
                            "ns3::Packet::TracedCallback");
    return tid;
}

NbP2PNetDevice::NbP2PNetDevice()
    : m_txMachineState(READY),
      m_channel(nullptr),
      m_linkUp(false),
      m_currentPkt(nullptr)
{
    NS_LOG_FUNCTION(this);
}

NbP2PNetDevice::~NbP2PNetDevice()
{
    NS_LOG_FUNCTION(this);
}

void
NbP2PNetDevice::DoDispose()
{
    NS_LOG_FUNCTION(this);
    m_node = nullptr;
    m_channel = nullptr;
    m_receiveErrorModel = nullptr;
    m_currentPkt = nullptr;
    m_queue = nullptr;
    NetDevice::DoDispose();
}

void
NbP2PNetDevice::SetDataRate(DataRate bps)
{
    NS_LOG_FUNCTION(this);
    m_bps = bps;
}

void
NbP2PNetDevice::SetInterframeGap(Time t)
{
    NS_LOG_FUNCTION(this << t.As(Time::S));
    m_tInterframeGap = t;
}

bool
NbP2PNetDevice::TransmitStart(Ptr<Packet> p)
{
    NS_LOG_FUNCTION(this << p);
    NS_LOG_LOGIC("UID is " << p->GetUid() << ")");

    //
    // This function is called to start the process of transmitting a packet.
    // We need to tell the channel that we've started wiggling the wire and
    // schedule an event that will be executed when the transmission is complete.
    //
    NS_ASSERT_MSG(m_txMachineState == READY, "Must be READY to transmit");
    m_txMachineState = BUSY;
    m_currentPkt = p;
    m_phyTxBeginTrace(m_currentPkt);

    Time txTime = m_bps.CalculateBytesTxTime(p->GetSize());
    Time txCompleteTime = txTime + m_tInterframeGap;

    NS_LOG_LOGIC("Schedule TransmitCompleteEvent in " << txCompleteTime.As(Time::S));
    Simulator::Schedule(txCompleteTime, &NbP2PNetDevice::TransmitComplete, this);

    bool result = m_channel->TransmitStart(p, this, txTime);
    if (!result)
    {
        m_phyTxDropTrace(p);
    }
    return result;
}

void
NbP2PNetDevice::TransmitComplete()
{
    NS_LOG_FUNCTION(this);

    //
    // This function is called to when we're all done transmitting a packet.
    // We try and pull another packet off of the transmit queue.  If the queue
    // is empty, we are done, otherwise we need to start transmitting the
    // next packet.
    //
    NS_ASSERT_MSG(m_txMachineState == BUSY, "Must be BUSY if transmitting");
    m_txMachineState = READY;

    NS_ASSERT_MSG(m_currentPkt, "NbP2PNetDevice::TransmitComplete(): m_currentPkt zero");

    m_phyTxEndTrace(m_currentPkt);
    m_currentPkt = nullptr;

    Ptr<Packet> p = m_queue->Dequeue();
    if (!p)
    {
        NS_LOG_LOGIC("No pending packets in device queue after tx complete");
        return;
    }

    //
    // Got another packet off of the queue, so start the transmit process again.
    //
    m_snifferTrace(p);
    m_promiscSnifferTrace(p);
    TransmitStart(p);
}

bool
NbP2PNetDevice::Attach(Ptr<NbP2PChannel> ch)
{
    NS_LOG_FUNCTION(this << &ch);

    m_channel = ch;

    m_channel->Attach(this);

    //
    // This device is up whenever it is attached to a channel.  A better plan
    // would be to have the link come up when both devices are attached, but this
    // is not done for now.
    //
    NotifyLinkUp();
    return true;
}

void
NbP2PNetDevice::SetQueue(Ptr<Queue<Packet>> q)
{
    NS_LOG_FUNCTION(this << q);
    m_queue = q;
}

void
NbP2PNetDevice::SetReceiveErrorModel(Ptr<ErrorModel> em)
{
    NS_LOG_FUNCTION(this << em);
    m_receiveErrorModel = em;
}

void
NbP2PNetDevice::Receive(Ptr<Packet> packet)
{
    NS_LOG_FUNCTION(this << packet);
    uint16_t protocol = 0;

    if (m_receiveErrorModel && m_receiveErrorModel->IsCorrupt(packet))
    {
        //
        // If we have an error model and it indicates that it is time to lose a
        // corrupted packet, don't forward this packet up, let it go.
        //
        m_phyRxDropTrace(packet);
    }
    else
    {
        //
        // Hit the trace hooks.  All of these hooks are in the same place in this
        // device because it is so simple, but this is not usually the case in
        // more complicated devices.
        //
        m_snifferTrace(packet);
        m_promiscSnifferTrace(packet);
        m_phyRxEndTrace(packet);

        //
        // Trace sinks will expect complete packets, not packets without some of the
        // headers.
        //
        Ptr<Packet> originalPacket = packet->Copy();

        // if (!m_promiscCallback.IsNull())
        // {
        //     m_macPromiscRxTrace(originalPacket);
        //     m_promiscCallback(this,
        //                       packet,
        //                       protocol,
        //                       GetRemote(),
        //                       GetAddress(),
        //                       NetDevice::PACKET_HOST);
        // }

        m_macRxTrace(originalPacket);
        m_rxCallback(this, originalPacket, 0, Address());
    }
}

Ptr<Queue<Packet>>
NbP2PNetDevice::GetQueue() const
{
    NS_LOG_FUNCTION(this);
    return m_queue;
}

void
NbP2PNetDevice::NotifyLinkUp()
{
    NS_LOG_FUNCTION(this);
    m_linkUp = true;
    m_linkChangeCallbacks();
}

void
NbP2PNetDevice::SetIfIndex(const uint32_t index)
{
    NS_LOG_FUNCTION(this);
    m_ifIndex = index;
}

uint32_t
NbP2PNetDevice::GetIfIndex() const
{
    return m_ifIndex;
}

Ptr<Channel>
NbP2PNetDevice::GetChannel() const
{
    return m_channel;
}

//
// This is a point-to-point device, so we really don't need any kind of address
// information.  However, the base class NetDevice wants us to define the
// methods to get and set the address.  Rather than be rude and assert, we let
// clients get and set the address, but simply ignore them.

void
NbP2PNetDevice::SetAddress(Address address)
{
    // NS_LOG_FUNCTION(this << address);
    // m_address = Mac48Address::ConvertFrom(address);
}

Address
NbP2PNetDevice::GetAddress() const
{
    return Address();
}

bool
NbP2PNetDevice::IsLinkUp() const
{
    NS_LOG_FUNCTION(this);
    return m_linkUp;
}

void
NbP2PNetDevice::AddLinkChangeCallback(Callback<void> callback)
{
    NS_LOG_FUNCTION(this);
    m_linkChangeCallbacks.ConnectWithoutContext(callback);
}

//
// This is a point-to-point device, so every transmission is a broadcast to
// all of the devices on the network.
//
bool
NbP2PNetDevice::IsBroadcast() const
{
    NS_LOG_FUNCTION(this);
    return true;
}

//
// We don't really need any addressing information since this is a
// point-to-point device.  The base class NetDevice wants us to return a
// broadcast address, so we make up something reasonable.
//
Address
NbP2PNetDevice::GetBroadcast() const
{
    NS_LOG_FUNCTION(this);
    return Mac48Address::GetBroadcast();
}

bool
NbP2PNetDevice::IsMulticast() const
{
    NS_LOG_FUNCTION(this);
    return true;
}

Address
NbP2PNetDevice::GetMulticast(Ipv4Address multicastGroup) const
{
    NS_LOG_FUNCTION(this);
    return Address();
}

Address
NbP2PNetDevice::GetMulticast(Ipv6Address addr) const
{
    NS_LOG_FUNCTION(this << addr);
    return Address();
}

bool
NbP2PNetDevice::IsPointToPoint() const
{
    NS_LOG_FUNCTION(this);
    return true;
}

bool
NbP2PNetDevice::IsBridge() const
{
    NS_LOG_FUNCTION(this);
    return false;
}

bool
NbP2PNetDevice::Send(Ptr<Packet> packet, const Address& dest, uint16_t protocolNumber)
{
    NS_LOG_FUNCTION(this << packet << dest << protocolNumber);
    NS_LOG_LOGIC("p=" << packet << ", dest=" << &dest);
    NS_LOG_LOGIC("UID is " << packet->GetUid());

    //
    // If IsLinkUp() is false it means there is no channel to send any packet
    // over so we just hit the drop trace on the packet and return an error.
    //
    if (!IsLinkUp())
    {
        m_macTxDropTrace(packet);
        return false;
    }

    m_macTxTrace(packet);

    //
    // We should enqueue and dequeue the packet to hit the tracing hooks.
    //
    if (m_queue->Enqueue(packet))
    {
        //
        // If the channel is ready for transition we send the packet right now
        //
        if (m_txMachineState == READY)
        {
            packet = m_queue->Dequeue();
            m_snifferTrace(packet);
            m_promiscSnifferTrace(packet);
            bool ret = TransmitStart(packet);
            return ret;
        }
        return true;
    }

    // Enqueue may fail (overflow)

    m_macTxDropTrace(packet);
    return false;
}

bool
NbP2PNetDevice::SendFrom(Ptr<Packet> packet,
                                const Address& source,
                                const Address& dest,
                                uint16_t protocolNumber)
{
    NS_LOG_FUNCTION(this << packet << source << dest << protocolNumber);
    return false;
}

Ptr<Node>
NbP2PNetDevice::GetNode() const
{
    return m_node;
}

void
NbP2PNetDevice::SetNode(Ptr<Node> node)
{
    NS_LOG_FUNCTION(this);
    m_node = node;
}

bool
NbP2PNetDevice::NeedsArp() const
{
    NS_LOG_FUNCTION(this);
    return false;
}

void
NbP2PNetDevice::SetReceiveCallback(NetDevice::ReceiveCallback cb)
{
    m_rxCallback = cb;
}

void
NbP2PNetDevice::SetPromiscReceiveCallback(NetDevice::PromiscReceiveCallback cb)
{
    m_promiscCallback = cb;
}

bool
NbP2PNetDevice::SupportsSendFrom() const
{
    NS_LOG_FUNCTION(this);
    return false;
}

void
NbP2PNetDevice::DoMpiReceive(Ptr<Packet> p)
{
    NS_LOG_FUNCTION(this << p);
    Receive(p);
}

bool
NbP2PNetDevice::SetMtu(uint16_t mtu)
{
    NS_LOG_FUNCTION(this << mtu);
    m_mtu = mtu;
    return true;
}

uint16_t
NbP2PNetDevice::GetMtu() const
{
    NS_LOG_FUNCTION(this);
    return m_mtu;
}

} // namespace ns3
