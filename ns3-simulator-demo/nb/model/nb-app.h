// -------------------------
// File: src/Nb/model/Nb-app.h
// -------------------------
#ifndef Nb_APP_H
#define Nb_APP_H

#include "ns3/application.h"
#include "ns3/ptr.h"
#include "ns3/event-id.h"
#include "ns3/packet.h"
#include "ns3/net-device.h"
#include "ns3/type-id.h"
#include "gen_headers.h"
#include "nb_runtime.h"
#include "nb-stack.h"


namespace ns3 {

class NbApp : public Application {
public:
  static TypeId GetTypeId();
  NbApp();
  virtual ~NbApp() {}

  // Configure local device, peer MAC, host/app identifiers
  void Configure(Ptr<NetDevice> dev,
                 uint64_t srcHost,
                 uint64_t dstHost,
                 uint32_t srcApp,
                 uint32_t dstApp);

  virtual void OnNbEvent(int event, nb__connection_t* conn) = 0;
  
protected:

  Ptr<NetDevice> m_dev;
  uint64_t        m_srcHost;
  uint64_t        m_dstHost;
  uint32_t        m_srcApp;
  uint32_t        m_dstApp;
  EventId        m_evt;
  ns3::Ptr<NbStack> m_nbStack; // Pointer to the NbStack instance
};

} // namespace ns3

#endif // Nb_APP_H