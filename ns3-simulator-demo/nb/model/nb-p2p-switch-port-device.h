#ifndef NB_P2P_SWITCH_PORT_DEVICE_H
#define NB_P2P_SWITCH_PORT_DEVICE_H

#include "nb-p2p-net-device.h"
#include "ns3/ptr.h"
#include "ns3/drop-tail-queue.h"

namespace ns3
{

class NbP2PSwitchStack; // Forward declaration

/**
 * @brief A single port on an NbP2PSwitch, inheriting from NbP2PNetDevice.
 *
 * This version reuses the machinery of NbP2PNetDevice, only overriding
 * the necessary parts to interact with the NbP2PSwitchStack.
 */
class NbP2PSwitchPortDevice : public NbP2PNetDevice
{
  public:
    static TypeId GetTypeId();

    NbP2PSwitchPortDevice();
    ~NbP2PSwitchPortDevice() override = default;

    /**
     * @brief Sets the controlling switch stack.
     * @param stack The switch stack that manages this port.
     */
    void SetStack(Ptr<NbP2PSwitchStack> stack);

    /**
     * @brief Initiates a packet transmission from the switch stack.
     *
     * This will use the underlying NbP2PNetDevice's send logic.
     *
     * @param packet The packet to send.
     * @return true if the packet was accepted for transmission, false otherwise.
     */
    bool SendFromStack(Ptr<Packet> packet);

    /**
     * @brief Checks if the port is currently busy transmitting.
     * @return true if busy, false otherwise.
     */
    bool IsBusy() const;

  protected:
    // --- Override NbP2PNetDevice callbacks ---

  private:
    Ptr<NbP2PSwitchStack> m_stack;
    // bool m_isBusy;
    void OnPhyTxEnd(Ptr<const Packet> packet);
    void NotifyIdleLater();
};

} // namespace ns3

#endif // NB_SWITCH_PORT_DEVICE_H