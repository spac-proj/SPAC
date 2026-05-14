#ifndef NB_CSMA_SWITCH_PORT_DEVICE_H
#define NB_CSMA_SWITCH_PORT_DEVICE_H

#include "nb-csma-net-device.h"
#include "ns3/ptr.h"
#include "ns3/drop-tail-queue.h"

namespace ns3
{

class NbCsmaSwitchStack; // Forward declaration

/**
 * @brief A single port on an NbSwitch, inheriting from NbCsmaNetDevice.
 *
 * This version reuses the machinery of NbCsmaNetDevice, only overriding
 * the necessary parts to interact with the NbCsmaSwitchStack.
 */
class NbCsmaSwitchPortDevice : public NbCsmaNetDevice
{
  public:
    static TypeId GetTypeId();

    NbCsmaSwitchPortDevice();
    ~NbCsmaSwitchPortDevice() override = default;

    /**
     * @brief Sets the controlling switch stack.
     * @param stack The switch stack that manages this port.
     */
    void SetStack(Ptr<NbCsmaSwitchStack> stack);

    /**
     * @brief Initiates a packet transmission from the switch stack.
     *
     * This will use the underlying NbCsmaNetDevice's send logic.
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
    // --- Override NbCsmaNetDevice callbacks ---

  private:
    Ptr<NbCsmaSwitchStack> m_stack;
    // bool m_isBusy;
    void OnPhyTxEnd(Ptr<const Packet> packet);
    void NotifyIdleLater();
};

} // namespace ns3

#endif // NB_SWITCH_PORT_DEVICE_H