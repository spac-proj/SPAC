// modiefied from ns3 existing code
/*
 * Copyright (c) 2008 INRIA
 *
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * Author: Mathieu Lacage <mathieu.lacage@sophia.inria.fr>
 */

#include "nb-csma-helper.h"

#include "ns3/abort.h"
#include "ns3/config.h"
#include "ns3/nb-csma-channel.h"
#include "ns3/nb-csma-net-device.h"
#include "ns3/log.h"
#include "ns3/names.h"
#include "ns3/net-device-queue-interface.h"
#include "ns3/object-factory.h"
#include "ns3/packet.h"
#include "ns3/simulator.h"
#include "ns3/trace-helper.h"
#include "ns3/nstime.h"

#include <string>

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("NbCsmaHelper");

NbCsmaHelper::NbCsmaHelper()
{
    m_queueFactory.SetTypeId("ns3::DropTailQueue<Packet>");
    m_deviceFactory.SetTypeId("ns3::NbCsmaNetDevice");
    m_channelFactory.SetTypeId("ns3::NbCsmaChannel");
    m_enableFlowControl = true;
}

void
NbCsmaHelper::SetDeviceAttribute(std::string n1, const AttributeValue& v1)
{
    m_deviceFactory.Set(n1, v1);
}

void
NbCsmaHelper::SetChannelAttribute(std::string n1, const AttributeValue& v1)
{
    m_channelFactory.Set(n1, v1);
}

void
NbCsmaHelper::DisableFlowControl()
{
    m_enableFlowControl = false;
}

void
NbCsmaHelper::EnablePcapInternal(std::string prefix,
                               Ptr<NetDevice> nd,
                               bool promiscuous,
                               bool explicitFilename)
{
    //
    // All of the Pcap enable functions vector through here including the ones
    // that are wandering through all of devices on perhaps all of the nodes in
    // the system.  We can only deal with devices of type NbCsmaNetDevice.
    //
    Ptr<NbCsmaNetDevice> device = nd->GetObject<NbCsmaNetDevice>();
    if (!device)
    {
        NS_LOG_INFO("NbCsmaHelper::EnablePcapInternal(): Device "
                    << device << " not of type ns3::NbCsmaNetDevice");
        return;
    }

    PcapHelper pcapHelper;

    std::string filename;
    if (explicitFilename)
    {
        filename = prefix;
    }
    else
    {
        filename = pcapHelper.GetFilenameFromDevice(prefix, device);
    }

    Ptr<PcapFileWrapper> file =
        pcapHelper.CreateFile(filename, std::ios::out, PcapHelper::DLT_EN10MB);
    if (promiscuous)
    {
        pcapHelper.HookDefaultSink<NbCsmaNetDevice>(device, "PromiscSniffer", file);
    }
    else
    {
        pcapHelper.HookDefaultSink<NbCsmaNetDevice>(device, "Sniffer", file);
    }
}

void
NbCsmaHelper::EnableAsciiInternal(Ptr<OutputStreamWrapper> stream,
                                std::string prefix,
                                Ptr<NetDevice> nd,
                                bool explicitFilename)
{
    //
    // All of the ascii enable functions vector through here including the ones
    // that are wandering through all of devices on perhaps all of the nodes in
    // the system.  We can only deal with devices of type NbCsmaNetDevice.
    //
    Ptr<NbCsmaNetDevice> device = nd->GetObject<NbCsmaNetDevice>();
    if (!device)
    {
        NS_LOG_INFO("NbCsmaHelper::EnableAsciiInternal(): Device "
                    << device << " not of type ns3::NbCsmaNetDevice");
        return;
    }

    //
    // Our default trace sinks are going to use packet printing, so we have to
    // make sure that is turned on.
    //
    Packet::EnablePrinting();

    //
    // If we are not provided an OutputStreamWrapper, we are expected to create
    // one using the usual trace filename conventions and do a Hook*WithoutContext
    // since there will be one file per context and therefore the context would
    // be redundant.
    //
    if (!stream)
    {
        //
        // Set up an output stream object to deal with private ofstream copy
        // constructor and lifetime issues.  Let the helper decide the actual
        // name of the file given the prefix.
        //
        AsciiTraceHelper asciiTraceHelper;

        std::string filename;
        if (explicitFilename)
        {
            filename = prefix;
        }
        else
        {
            filename = asciiTraceHelper.GetFilenameFromDevice(prefix, device);
        }

        Ptr<OutputStreamWrapper> theStream = asciiTraceHelper.CreateFileStream(filename);

        //
        // The MacRx trace source provides our "r" event.
        //
        asciiTraceHelper.HookDefaultReceiveSinkWithoutContext<NbCsmaNetDevice>(device,
                                                                             "MacRx",
                                                                             theStream);

        //
        // The "+", '-', and 'd' events are driven by trace sources actually in the
        // transmit queue.
        //
        Ptr<Queue<Packet>> queue = device->GetQueue();
        asciiTraceHelper.HookDefaultEnqueueSinkWithoutContext<Queue<Packet>>(queue,
                                                                             "Enqueue",
                                                                             theStream);
        asciiTraceHelper.HookDefaultDropSinkWithoutContext<Queue<Packet>>(queue, "Drop", theStream);
        asciiTraceHelper.HookDefaultDequeueSinkWithoutContext<Queue<Packet>>(queue,
                                                                             "Dequeue",
                                                                             theStream);

        return;
    }

    //
    // If we are provided an OutputStreamWrapper, we are expected to use it, and
    // to providd a context.  We are free to come up with our own context if we
    // want, and use the AsciiTraceHelper Hook*WithContext functions, but for
    // compatibility and simplicity, we just use Config::Connect and let it deal
    // with the context.
    //
    // Note that we are going to use the default trace sinks provided by the
    // ascii trace helper.  There is actually no AsciiTraceHelper in sight here,
    // but the default trace sinks are actually publicly available static
    // functions that are always there waiting for just such a case.
    //
    uint32_t nodeid = nd->GetNode()->GetId();
    uint32_t deviceid = nd->GetIfIndex();
    std::ostringstream oss;

    oss << "/NodeList/" << nd->GetNode()->GetId() << "/DeviceList/" << deviceid
        << "/$ns3::NbCsmaNetDevice/MacRx";
    Config::Connect(oss.str(),
                    MakeBoundCallback(&AsciiTraceHelper::DefaultReceiveSinkWithContext, stream));

    oss.str("");
    oss << "/NodeList/" << nodeid << "/DeviceList/" << deviceid
        << "/$ns3::NbCsmaNetDevice/TxQueue/Enqueue";
    Config::Connect(oss.str(),
                    MakeBoundCallback(&AsciiTraceHelper::DefaultEnqueueSinkWithContext, stream));

    oss.str("");
    oss << "/NodeList/" << nodeid << "/DeviceList/" << deviceid
        << "/$ns3::NbCsmaNetDevice/TxQueue/Dequeue";
    Config::Connect(oss.str(),
                    MakeBoundCallback(&AsciiTraceHelper::DefaultDequeueSinkWithContext, stream));

    oss.str("");
    oss << "/NodeList/" << nodeid << "/DeviceList/" << deviceid
        << "/$ns3::NbCsmaNetDevice/TxQueue/Drop";
    Config::Connect(oss.str(),
                    MakeBoundCallback(&AsciiTraceHelper::DefaultDropSinkWithContext, stream));
}

NetDeviceContainer
NbCsmaHelper::Install(Ptr<Node> node) const
{
    Ptr<NbCsmaChannel> channel = m_channelFactory.Create()->GetObject<NbCsmaChannel>();
    return Install(node, channel);
}

NetDeviceContainer
NbCsmaHelper::Install(std::string nodeName) const
{
    Ptr<Node> node = Names::Find<Node>(nodeName);
    return Install(node);
}

NetDeviceContainer
NbCsmaHelper::Install(Ptr<Node> node, Ptr<NbCsmaChannel> channel) const
{
    return NetDeviceContainer(InstallPriv(node, channel));
}

NetDeviceContainer
NbCsmaHelper::Install(Ptr<Node> node, std::string channelName) const
{
    Ptr<NbCsmaChannel> channel = Names::Find<NbCsmaChannel>(channelName);
    return NetDeviceContainer(InstallPriv(node, channel));
}

NetDeviceContainer
NbCsmaHelper::Install(std::string nodeName, Ptr<NbCsmaChannel> channel) const
{
    Ptr<Node> node = Names::Find<Node>(nodeName);
    return NetDeviceContainer(InstallPriv(node, channel));
}

NetDeviceContainer
NbCsmaHelper::Install(std::string nodeName, std::string channelName) const
{
    Ptr<Node> node = Names::Find<Node>(nodeName);
    Ptr<NbCsmaChannel> channel = Names::Find<NbCsmaChannel>(channelName);
    return NetDeviceContainer(InstallPriv(node, channel));
}

NetDeviceContainer
NbCsmaHelper::Install(const NodeContainer& c) const
{
    Ptr<NbCsmaChannel> channel = m_channelFactory.Create()->GetObject<NbCsmaChannel>();

    return Install(c, channel);
}

NetDeviceContainer
NbCsmaHelper::Install(const NodeContainer& c, Ptr<NbCsmaChannel> channel) const
{
    NetDeviceContainer devs;

    for (auto i = c.Begin(); i != c.End(); i++)
    {
        devs.Add(InstallPriv(*i, channel));
    }

    return devs;
}

NetDeviceContainer
NbCsmaHelper::Install(const NodeContainer& c, std::string channelName) const
{
    Ptr<NbCsmaChannel> channel = Names::Find<NbCsmaChannel>(channelName);
    return Install(c, channel);
}

int64_t
NbCsmaHelper::AssignStreams(NetDeviceContainer c, int64_t stream)
{
    int64_t currentStream = stream;
    Ptr<NetDevice> netDevice;
    for (auto i = c.Begin(); i != c.End(); ++i)
    {
        netDevice = (*i);
        Ptr<NbCsmaNetDevice> csma = DynamicCast<NbCsmaNetDevice>(netDevice);
        if (csma)
        {
            currentStream += csma->AssignStreams(currentStream);
        }
    }
    return (currentStream - stream);
}

Ptr<NetDevice>
NbCsmaHelper::InstallPriv(Ptr<Node> node, Ptr<NbCsmaChannel> channel) const
{
    Ptr<NbCsmaNetDevice> device = m_deviceFactory.Create<NbCsmaNetDevice>();
    device->SetAddress(Address());
    node->AddDevice(device);
    Ptr<Queue<Packet>> queue = m_queueFactory.Create<Queue<Packet>>();
    device->SetQueue(queue);
    device->Attach(channel);
    if (m_enableFlowControl)
    {
        // Aggregate a NetDeviceQueueInterface object
        Ptr<NetDeviceQueueInterface> ndqi = CreateObject<NetDeviceQueueInterface>();
        ndqi->GetTxQueue(0)->ConnectQueueTraces(queue);
        device->AggregateObject(ndqi);
    }
    // device->SetBackoffParams(MicroSeconds(512), 0, 1024, 10, 16);
    // printf("Backoff Params: SlotTime 512us, MinSlots 0, MaxSlots 1024, ceiling 10, MaxRetries 16\n");
    return device;
}

} // namespace ns3
