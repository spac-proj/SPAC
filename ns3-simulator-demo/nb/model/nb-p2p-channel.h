// modiefied from ns3 existing code
/*
 * Copyright (c) 2007 University of Washington
 *
 * SPDX-License-Identifier: GPL-2.0-only
 */

#ifndef NB_P2P_CHANNEL_H
#define NB_P2P_CHANNEL_H

#include "ns3/channel.h"
#include "ns3/data-rate.h"
#include "ns3/nstime.h"
#include "ns3/ptr.h"
#include "ns3/traced-callback.h"

#include <list>

namespace ns3
{

class NbP2PNetDevice;
class Packet;

/**
 * @ingroup point-to-point
 * @brief Simple Point To Point Channel.
 *
 * This class represents a very simple point to point channel.  Think full
 * duplex RS-232 or RS-422 with null modem and no handshaking.  There is no
 * multi-drop capability on this channel -- there can be a maximum of two
 * point-to-point net devices connected.
 *
 * There are two "wires" in the channel.  The first device connected gets the
 * [0] wire to transmit on.  The second device gets the [1] wire.  There is a
 * state (IDLE, TRANSMITTING) associated with each wire.
 *
 * @see Attach
 * @see TransmitStart
 */
class NbP2PChannel : public Channel
{
  public:
    /**
     * @brief Get the TypeId
     *
     * @return The TypeId for this class
     */
    static TypeId GetTypeId();

    /**
     * @brief Create a NbP2PChannel
     *
     * By default, you get a channel that has an "infinitely" fast
     * transmission speed and zero delay.
     */
    NbP2PChannel();

    /**
     * @brief Attach a given netdevice to this channel
     * @param device pointer to the netdevice to attach to the channel
     */
    void Attach(Ptr<NbP2PNetDevice> device);

    /**
     * @brief Transmit a packet over this channel
     * @param p Packet to transmit
     * @param src Source NbP2PNetDevice
     * @param txTime Transmit time to apply
     * @returns true if successful (currently always true)
     */
    virtual bool TransmitStart(Ptr<const Packet> p, Ptr<NbP2PNetDevice> src, Time txTime);

    /**
     * @brief Get number of devices on this channel
     * @returns number of devices on this channel
     */
    std::size_t GetNDevices() const override;

    /**
     * @brief Get NbP2PNetDevice corresponding to index i on this channel
     * @param i Index number of the device requested
     * @returns Ptr to NbP2PNetDevice requested
     */
    Ptr<NbP2PNetDevice> GetNbP2PDevice(std::size_t i) const;

    /**
     * @brief Get NetDevice corresponding to index i on this channel
     * @param i Index number of the device requested
     * @returns Ptr to NetDevice requested
     */
    Ptr<NetDevice> GetDevice(std::size_t i) const override;

  protected:
    /**
     * @brief Get the delay associated with this channel
     * @returns Time delay
     */
    Time GetDelay() const;

    /**
     * @brief Check to make sure the link is initialized
     * @returns true if initialized, asserts otherwise
     */
    bool IsInitialized() const;

    /**
     * @brief Get the net-device source
     * @param i the link requested
     * @returns Ptr to NbP2PNetDevice source for the
     * specified link
     */
    Ptr<NbP2PNetDevice> GetSource(uint32_t i) const;

    /**
     * @brief Get the net-device destination
     * @param i the link requested
     * @returns Ptr to NbP2PNetDevice destination for
     * the specified link
     */
    Ptr<NbP2PNetDevice> GetDestination(uint32_t i) const;

    /**
     * TracedCallback signature for packet transmission animation events.
     *
     * @param [in] packet The packet being transmitted.
     * @param [in] txDevice the TransmitTing NetDevice.
     * @param [in] rxDevice the Receiving NetDevice.
     * @param [in] duration The amount of time to transmit the packet.
     * @param [in] lastBitTime Last bit receive time (relative to now)
     * @deprecated The non-const \c Ptr<NetDevice> argument is deprecated
     * and will be changed to \c Ptr<const NetDevice> in a future release.
     */
    // NS_DEPRECATED() - tag for future removal
    typedef void (*TxRxAnimationCallback)(Ptr<const Packet> packet,
                                          Ptr<NetDevice> txDevice,
                                          Ptr<NetDevice> rxDevice,
                                          Time duration,
                                          Time lastBitTime);

  private:
    /** Each point to point link has exactly two net devices. */
    static const std::size_t N_DEVICES = 2;

    Time m_delay;           //!< Propagation delay
    std::size_t m_nDevices; //!< Devices of this channel

    /**
     * The trace source for the packet transmission animation events that the
     * device can fire.
     * Arguments to the callback are the packet, transmitting
     * net device, receiving net device, transmission time and
     * packet receipt time.
     *
     * @see class CallBackTraceSource
     * @deprecated The non-const \c Ptr<NetDevice> argument is deprecated
     * and will be changed to \c Ptr<const NetDevice> in a future release.
     */
    // NS_DEPRECATED() - tag for future removal
    TracedCallback<Ptr<const Packet>, // Packet being transmitted
                   Ptr<NetDevice>,    // Transmitting NetDevice
                   Ptr<NetDevice>,    // Receiving NetDevice
                   Time,              // Amount of time to transmit the pkt
                   Time               // Last bit receive time (relative to now)
                   >
        m_txrxNbP2P;

    /** @brief Wire states
     *
     */
    enum WireState
    {
        /** Initializing state */
        INITIALIZING,
        /** Idle state (no transmission from NetDevice) */
        IDLE,
        /** Transmitting state (data being transmitted from NetDevice. */
        TRANSMITTING,
        /** Propagating state (data is being propagated in the channel. */
        PROPAGATING
    };

    /**
     * @brief Wire model for the NbP2PChannel
     */
    class Link
    {
      public:
        /** @brief Create the link, it will be in INITIALIZING state
         *
         */
        Link() = default;

        WireState m_state{INITIALIZING};  //!< State of the link
        Ptr<NbP2PNetDevice> m_src; //!< First NetDevice
        Ptr<NbP2PNetDevice> m_dst; //!< Second NetDevice
    };

    Link m_link[N_DEVICES]; //!< Link model
};

} // namespace ns3

#endif /* POINT_TO_POINT_CHANNEL_H */
