#include "nb-app.h"
#include "ns3/log.h"
#include "ns3/simulator.h"
#include "ns3/net-device.h"

namespace ns3 {

NS_LOG_COMPONENT_DEFINE("NbApp");
NS_OBJECT_ENSURE_REGISTERED(NbApp);

TypeId
NbApp::GetTypeId()
{
  static TypeId tid =
    TypeId("ns3::NbApp")
      .SetParent<Application>()
      .SetGroupName("Nb");
  return tid;
}

NbApp::NbApp()
  : m_dev(nullptr),
    m_srcHost(0),
    m_dstHost(0),
    m_srcApp(0),
    m_dstApp(0),
    m_evt()
{
}

void 
NbApp::Configure(Ptr<NetDevice> dev,
  uint64_t srcHost, uint64_t dstHost,
  uint32_t srcApp, uint32_t dstApp) 
{
  m_dev = dev;
  m_srcHost = srcHost;
  m_dstHost = dstHost;
  m_srcApp = srcApp;
  m_dstApp = dstApp;
}

} // namespace ns3
