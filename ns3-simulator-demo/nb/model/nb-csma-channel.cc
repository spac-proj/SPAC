// modiefied from ns3 existing code
/*
 * Copyright (c) 2007 Emmanuelle Laprise
 *
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * Author: Emmanuelle Laprise <emmanuelle.laprise@bluekazoo.ca>
 */

#include "nb-csma-channel.h"

#include "nb-csma-net-device.h"

#include "ns3/log.h"
#include "ns3/packet.h"
#include "ns3/simulator.h"

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("NbCsmaChannel");

NS_OBJECT_ENSURE_REGISTERED(NbCsmaChannel);

TypeId
NbCsmaChannel::GetTypeId()
{
    static TypeId tid =
        TypeId("ns3::NbCsmaChannel")
            .SetParent<Channel>()
            .SetGroupName("Nb")
            .AddConstructor<NbCsmaChannel>()
            .AddAttribute(
                "DataRate",
                "The transmission data rate to be provided to devices connected to the channel",
                DataRateValue(DataRate(0xffffffff)),
                MakeDataRateAccessor(&NbCsmaChannel::m_bps),
                MakeDataRateChecker())
            .AddAttribute("Delay",
                          "Transmission delay through the channel",
                          TimeValue(Seconds(0)),
                          MakeTimeAccessor(&NbCsmaChannel::m_delay),
                          MakeTimeChecker());
    return tid;
}

NbCsmaChannel::NbCsmaChannel()
    : Channel()
{
    NS_LOG_FUNCTION_NOARGS();
    m_state = IDLE;
    m_deviceList.clear();
}

NbCsmaChannel::~NbCsmaChannel()
{
    NS_LOG_FUNCTION(this);
    m_deviceList.clear();
}

int32_t
NbCsmaChannel::Attach(Ptr<NbCsmaNetDevice> device)
{
    NS_LOG_FUNCTION(this << device);
    NS_ASSERT(device);

    NbCsmaDeviceRec rec(device);

    m_deviceList.push_back(rec);
    return (m_deviceList.size() - 1);
}

bool
NbCsmaChannel::Reattach(Ptr<NbCsmaNetDevice> device)
{
    NS_LOG_FUNCTION(this << device);
    NS_ASSERT(device);

    for (auto it = m_deviceList.begin(); it < m_deviceList.end(); it++)
    {
        if (it->devicePtr == device)
        {
            if (!it->active)
            {
                it->active = true;
                return true;
            }
            else
            {
                return false;
            }
        }
    }
    return false;
}

bool
NbCsmaChannel::Reattach(uint32_t deviceId)
{
    NS_LOG_FUNCTION(this << deviceId);

    if (deviceId < m_deviceList.size())
    {
        return false;
    }

    if (m_deviceList[deviceId].active)
    {
        return false;
    }
    else
    {
        m_deviceList[deviceId].active = true;
        return true;
    }
}

bool
NbCsmaChannel::Detach(uint32_t deviceId)
{
    NS_LOG_FUNCTION(this << deviceId);

    if (deviceId < m_deviceList.size())
    {
        if (!m_deviceList[deviceId].active)
        {
            NS_LOG_WARN("NbCsmaChannel::Detach(): Device is already detached (" << deviceId << ")");
            return false;
        }

        m_deviceList[deviceId].active = false;

        if ((m_state == TRANSMITTING) && (m_currentSrc == deviceId))
        {
            NS_LOG_WARN("NbCsmaChannel::Detach(): Device is currently"
                        << "transmitting (" << deviceId << ")");
        }

        return true;
    }
    else
    {
        return false;
    }
}

bool
NbCsmaChannel::Detach(Ptr<NbCsmaNetDevice> device)
{
    NS_LOG_FUNCTION(this << device);
    NS_ASSERT(device);

    for (auto it = m_deviceList.begin(); it < m_deviceList.end(); it++)
    {
        if ((it->devicePtr == device) && (it->active))
        {
            it->active = false;
            return true;
        }
    }
    return false;
}

bool
NbCsmaChannel::TransmitStart(Ptr<const Packet> p, uint32_t srcId)
{
    NS_LOG_FUNCTION(this << p << srcId);
    NS_LOG_INFO("UID is " << p->GetUid() << ")");

    if (m_state != IDLE)
    {
        NS_LOG_WARN("NbCsmaChannel::TransmitStart(): State is not IDLE");
        return false;
    }

    if (!IsActive(srcId))
    {
        NS_LOG_ERROR(
            "NbCsmaChannel::TransmitStart(): Seclected source is not currently attached to network");
        return false;
    }

    NS_LOG_LOGIC("switch to TRANSMITTING");
    m_currentPkt = p;
    m_currentSrc = srcId;
    m_state = TRANSMITTING;
    return true;
}

bool
NbCsmaChannel::IsActive(uint32_t deviceId)
{
    return m_deviceList[deviceId].active;
}

bool
NbCsmaChannel::TransmitEnd()
{
    NS_LOG_FUNCTION(this << m_currentPkt << m_currentSrc);
    NS_LOG_INFO("UID is " << m_currentPkt->GetUid() << ")");

    NS_ASSERT(m_state == TRANSMITTING);
    m_state = PROPAGATING;

    bool retVal = true;

    if (!IsActive(m_currentSrc))
    {
        NS_LOG_ERROR("NbCsmaChannel::TransmitEnd(): Seclected source was detached before the end of "
                     "the transmission");
        retVal = false;
    }

    NS_LOG_LOGIC("Schedule event in " << m_delay.As(Time::S));

    NS_LOG_LOGIC("Receive");

    for (auto it = m_deviceList.begin(); it < m_deviceList.end(); it++)
    {
        if (it->IsActive() && it->devicePtr != m_deviceList[m_currentSrc].devicePtr)
        {
            // schedule reception events
            Simulator::ScheduleWithContext(it->devicePtr->GetNode()->GetId(),
                                           m_delay,
                                           &NbCsmaNetDevice::Receive,
                                           it->devicePtr,
                                           m_currentPkt,
                                           m_deviceList[m_currentSrc].devicePtr);
        }
    }

    // also schedule for the tx side to go back to IDLE
    Simulator::Schedule(m_delay, &NbCsmaChannel::PropagationCompleteEvent, this);
    return retVal;
}

void
NbCsmaChannel::PropagationCompleteEvent()
{
    NS_LOG_FUNCTION(this << m_currentPkt);
    NS_LOG_INFO("UID is " << m_currentPkt->GetUid() << ")");

    NS_ASSERT(m_state == PROPAGATING);
    m_state = IDLE;
}

uint32_t
NbCsmaChannel::GetNumActDevices()
{
    int numActDevices = 0;
    for (auto it = m_deviceList.begin(); it < m_deviceList.end(); it++)
    {
        if (it->active)
        {
            numActDevices++;
        }
    }
    return numActDevices;
}

std::size_t
NbCsmaChannel::GetNDevices() const
{
    return m_deviceList.size();
}

Ptr<NbCsmaNetDevice>
NbCsmaChannel::GetNbCsmaDevice(std::size_t i) const
{
    return m_deviceList[i].devicePtr;
}

int32_t
NbCsmaChannel::GetDeviceNum(Ptr<NbCsmaNetDevice> device)
{
    int i = 0;
    for (auto it = m_deviceList.begin(); it < m_deviceList.end(); it++)
    {
        if (it->devicePtr == device)
        {
            if (it->active)
            {
                return i;
            }
            else
            {
                return -2;
            }
        }
        i++;
    }
    return -1;
}

bool
NbCsmaChannel::IsBusy()
{
    return m_state != IDLE;
}

DataRate
NbCsmaChannel::GetDataRate()
{
    return m_bps;
}

Time
NbCsmaChannel::GetDelay()
{
    return m_delay;
}

WireState
NbCsmaChannel::GetState()
{
    return m_state;
}

Ptr<NetDevice>
NbCsmaChannel::GetDevice(std::size_t i) const
{
    return GetNbCsmaDevice(i);
}

NbCsmaDeviceRec::NbCsmaDeviceRec()
{
    active = false;
}

NbCsmaDeviceRec::NbCsmaDeviceRec(Ptr<NbCsmaNetDevice> device)
{
    devicePtr = device;
    active = true;
}

NbCsmaDeviceRec::NbCsmaDeviceRec(const NbCsmaDeviceRec& deviceRec)
{
    devicePtr = deviceRec.devicePtr;
    active = deviceRec.active;
}

bool
NbCsmaDeviceRec::IsActive() const
{
    return active;
}

} // namespace ns3
