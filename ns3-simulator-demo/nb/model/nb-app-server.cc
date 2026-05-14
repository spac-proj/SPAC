#include "nb-app-server.h"
#include "ns3/log.h"
#include "nb_runtime.h" // add include for wildcard constant
#include <map>

namespace ns3 {

NS_LOG_COMPONENT_DEFINE("NbAppServer");
NS_OBJECT_ENSURE_REGISTERED(NbAppServer);

TypeId NbAppServer::GetTypeId() {
  static TypeId tid = TypeId("ns3::NbAppServer")
    .SetParent<NbApp>()
    .SetGroupName("Nb")
    .AddConstructor<NbAppServer>();
  return tid;
}

NbAppServer::NbAppServer() {
  NS_LOG_FUNCTION(this);
}

void NbAppServer::OnNbEvent(int event, nb__connection_t* conn) {
    NS_LOG_FUNCTION(this << event);
    if (event == QUEUE_EVENT_READ_READY) {
        int len = m_nbStack->Read(conn, recv_buf, 1024);
        printf("Hostid: %u, Appid: %u, Server Receive READ_READY, time: %.6f\n", m_srcHost, m_srcApp, Simulator::Now().GetSeconds());
        if (len == 16) { running = 0; return;}
        m_nbStack->Send(conn, recv_buf, len);
    } else if (event == QUEUE_EVENT_ACCEPT_READY) {
        // Accept a new incoming connection and start servicing it
        printf("Hostid: %u, Appid: %u, Server Receive ACCEPT_READY, time: %.6f\n", m_srcHost, m_srcApp, Simulator::Now().GetSeconds());
        m_conn = m_nbStack->Accept(conn, MakeCallback(&NbApp::OnNbEvent, this));
    }
}

void
NbAppServer::StartApplication()
{
  NS_LOG_FUNCTION(this);

  // Ensure the device is set
  NS_ASSERT(m_dev != nullptr);

  static std::map< Ptr<NetDevice>, Ptr<NbStack> > stacks;
  auto it = stacks.find(m_dev);
  if (it == stacks.end()) {
      m_nbStack = Create<NbStack>(m_srcHost, m_dev);
      m_nbStack->StackInit();
      stacks[m_dev] = m_nbStack;
  } else {
      m_nbStack = it->second;
      // printf("Nb stack reused in nb server app! \n");
  }
  m_conn = m_nbStack -> Establish(m_dstHost, m_dstApp, m_srcApp,
                                  MakeCallback(&NbApp::OnNbEvent, this));
}

void
NbAppServer::StopApplication()
{
  m_nbStack->Destablish(m_conn);
  m_nbStack = nullptr;
}

} // namespace ns3
