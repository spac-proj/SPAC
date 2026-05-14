#include "nb-p2p-switch-stack.h"
#include "ns3/log.h"
#include "ns3/simulator.h"
#include "ns3/drop-tail-queue.h"
#include <algorithm>
#include "gen_headers.h"

namespace ns3 {

NS_LOG_COMPONENT_DEFINE ("NbP2PSwitchStack");
NS_OBJECT_ENSURE_REGISTERED (NbP2PSwitchStack);

TypeId
NbP2PSwitchStack::GetTypeId ()
{
    static TypeId tid = TypeId ("ns3::NbP2PSwitchStack")
                            .SetParent<Object> ()
                            .SetGroupName ("Nb")
                            .AddConstructor<NbP2PSwitchStack> ();
    return tid;
}

NbP2PSwitchStack::NbP2PSwitchStack () : Object ()
{
    NS_LOG_FUNCTION (this);
    // m_cleanupEvent = Simulator::Schedule (m_entryTimeout,
    //                                       &NbP2PSwitchStack::CleanFwdTable,
    //                                       this);
}

NbP2PSwitchStack::~NbP2PSwitchStack()
{
    // if (m_cleanupEvent.IsPending()) {
    //     Simulator::Cancel(m_cleanupEvent);
    // }
}

/* ---------------------- port management ---------------------- */
void
NbP2PSwitchStack::AttachPort (Ptr<NbP2PSwitchPortDevice> port)
{
    PortId id = m_ports.size ();
    m_ports.push_back (port);
    m_portIndex[port] = id;

    port->SetStack(this);
    port->SetReceiveCallback(MakeCallback (&NbP2PSwitchStack::OnDeviceReceive, this));

    // create new colums for each row
    for (auto& row : m_voq) {
        row.emplace_back (CreateObject<DropTailQueue<Packet>> ());
    }
    // push an empty row first, then resize and fill with distinct queues
    m_voq.emplace_back();
    std::vector< Ptr<Queue<Packet>> >& newRow = m_voq.back();
    newRow.resize (m_ports.size());
    for (uint32_t out = 0; out < m_ports.size(); ++out)
    {
        newRow[out] = CreateObject<DropTailQueue<Packet>> ();
    }

    // create new nextOut and nextIn for round-robin scheduling
    m_nextOut.push_back (0);
    m_nextIn .push_back (0);
}

/* ---------------------- ingress ---------------------- */
bool
NbP2PSwitchStack::OnDeviceReceive (Ptr<NetDevice> dev,
                                Ptr<const Packet> pkt,
                                uint16_t /*proto*/,
                                const Address& /*from*/)
{
    Ptr<NbP2PSwitchPortDevice> inPort = DynamicCast<NbP2PSwitchPortDevice> (dev);
    PortId in = m_portIndex[inPort];

    /* copy data and parse Nb header */
    uint32_t len = pkt->GetSize ();
    std::unique_ptr<uint8_t[]> buffer (new uint8_t[len + nb__packet_headroom]);
    pkt->CopyData (buffer.get () + nb__packet_headroom, len);

    HostId src = nb__get_src_host_id (buffer.get ());
    HostId dst = nb__get_dst_host_id (buffer.get ());
    printf("Switch Received! src: %d, dst: %d, time: %.6f\n", src, dst, Simulator::Now ().GetSeconds ());
    bool learnedNew = (m_fwd.find(src) == m_fwd.end());
    m_fwd[src]      = in;
    m_fwdTime[src]  = Simulator::Now ();
    if (learnedNew)
    {
        printf("[SW] learn host %u is from port %u\n", src, in);
    }

    if (m_fwd.find (dst) == m_fwd.end ()) {
        /* not learned => Flood */
        printf("[SW] flood unknown dst %u from inPort %u\n", dst, in);
        for (PortId out = 0; out < m_ports.size (); ++out) {
            if (out != in) {
                Enqueue (in, out, pkt->Copy ());
            }
        }
    } else {
        PortId out = m_fwd[dst];
        if (out != in) {
            printf("[SW] unicast dst %u via outPort %u\n", dst, out);
            Enqueue (in, out, pkt->Copy ());
        }
    }

    Arbitrate ();
    return true;
}

/* ---------------------- VOQ & arbitration ---------------------- */
void
NbP2PSwitchStack::Enqueue (PortId in, PortId out, Ptr<Packet> pkt)
{
    m_voq[in][out]->Enqueue (pkt);
}

void
NbP2PSwitchStack::Arbitrate ()
{
    const uint32_t N = m_ports.size ();
    printf("[iSLIP] Arbitrate: N=%d\n", N);
    // printf("m_voq[2][0]->GetNPackets(): %d\n", m_voq[2][0]->GetNPackets());
    if (N == 0) return;

    std::vector<int> matchedIn (N, -1);
    std::vector<int> matchedOut (N, -1);

    bool progress = true;
    while (progress) {
        progress = false;

        /* ---------- Grant for output ports by round-robin scheduling ---------- */
        std::vector<int> grant (N, -1); // out -> in
        // Grant phase debug
        printf("[iSLIP] ---- Grant phase ----\n");
        for (uint32_t out = 0; out < N; ++out)
        {
            if (matchedOut[out] != -1 || m_ports[out]->IsBusy ()) continue;

            uint32_t start = m_nextIn[out];
            for (uint32_t k = 0; k < N; ++k) {
                uint32_t in = (start + k) % N;
                if (matchedIn[in] == -1 && !m_voq[in][out]->IsEmpty ()) {
                    grant[out] = in;
                    printf("[iSLIP] out %u grant: in %u\n", out, in);
                    break;
                }
            }
        }

        /* ---------- Accept for input ports by round-robin scheduling ---------- */
        for (uint32_t in = 0; in < N; ++in) {
            if (matchedIn[in] != -1) continue;

            uint32_t start = m_nextOut[in];
            for (uint32_t k = 0; k < N; ++k) {
                uint32_t out = (start + k) % N;
                if (grant[out] == static_cast<int>(in)) {
                    /* send 1 packet */
                    Ptr<Packet> p = m_voq[in][out]->Dequeue ();
                    printf("[iSLIP] in %u accept: out %u\n", in, out);
                    if (!m_ports[out]->SendFromStack (p)) {
                        printf("[iSLIP] sendFromStack failed\n");
                        m_voq[in][out]->Enqueue (p); // put back to voq
                        printf("[iSLIP] enqueue packet back to voq\n");
                        continue;
                    }

                    matchedIn[in]  = out;
                    matchedOut[out] = in;
                    progress = true;

                    /* update round-robin pointers */
                    m_nextOut[in] = (out + 1) % N;
                    m_nextIn[out] = (in + 1) % N;
                    break;
                }
            }
        }
    }
}

/* ---------------------- port idle callback ---------------------- */
void
NbP2PSwitchStack::PortBecameIdle (Ptr<NbP2PSwitchPortDevice> /*port*/)
{
    printf("[iSLIP] PortBecameIdle\n");
    Arbitrate();
}

/* ---------------------- fwd table aging ---------------------- */
void
NbP2PSwitchStack::CleanFwdTable ()
{
    Time now = Simulator::Now ();
    for (auto it = m_fwdTime.begin (); it != m_fwdTime.end ();)
    {
        if (now - it->second > m_entryTimeout)
        {
            m_fwd.erase (it->first);
            it = m_fwdTime.erase (it);
        }
        else
        {
            ++it;
        }
    }
    m_cleanupEvent = Simulator::Schedule (m_entryTimeout,
                                          &NbP2PSwitchStack::CleanFwdTable,
                                          this);
}

} // namespace ns3
// ... existing code ...