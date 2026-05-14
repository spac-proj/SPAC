#include "nb-app-client.h"
#include "ns3/log.h"
#include <sys/time.h>
#include <time.h>
#include <map>

static long long get_time_in_ns(void) {
	struct timespec tv;
	clock_gettime(CLOCK_MONOTONIC, &tv);
	return tv.tv_sec * 1000000000 + tv.tv_nsec;
}

namespace ns3 {

NS_LOG_COMPONENT_DEFINE("NbAppClient");
NS_OBJECT_ENSURE_REGISTERED(NbAppClient);

TypeId NbAppClient::GetTypeId() {
  static TypeId tid = TypeId("ns3::NbAppClient")
    .SetParent<NbApp>()
    .SetGroupName("Nb")
    .AddConstructor<NbAppClient>();
  return tid;
}

NbAppClient::NbAppClient() {
  NS_LOG_FUNCTION(this);
}

void NbAppClient::OnNbEvent(int event, nb__connection_t* conn) {
	if (running == 0) return;
  if (event == QUEUE_EVENT_READ_READY) {
    // printf("Hostid: %u, Appid: %u, Server Receive READ_READY, time: %.6f\n", m_srcHost, m_srcApp, Simulator::Now().GetSeconds());
    printf("Hostid: %u, Appid: %u, Client Receive READ_READY, time: %.6f\n", m_srcHost, m_srcApp, Simulator::Now().GetSeconds());
    m_nbStack -> Read(conn, recv_buf, 1024);

    end_time = get_time_in_ns();

    long long elapsed_time = (end_time - start_time) / 100;

    if (elapsed_time < 2000)
      stats[elapsed_time]++;
    count++;
    printf("client send count: %d\n", count);

    if (count == 5) {
      running = 0;
      m_nbStack -> Send(conn, send_buf, 16);
      return;
    }

    start_time = get_time_in_ns();
    m_nbStack -> Send(conn, send_buf, packet_size);
  } else if (event == QUEUE_EVENT_ESTABLISHED) {
    // printf("Host %u, App %u: QUEUE_EVENT_ESTABLISHED\n", m_srcHost, m_srcApp);
    printf("Hostid: %u, Appid: %u, Client Receive ESTABLISHED, time: %.6f\n", m_srcHost, m_srcApp, Simulator::Now().GetSeconds());
    start_time = get_time_in_ns();
    m_nbStack -> Send(conn, send_buf, packet_size);
  }
}

void
NbAppClient::StartApplication()
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
      // printf("Nb stack reused in nb client app! \n");
  }
  m_conn = m_nbStack -> Establish(m_dstHost, m_dstApp, m_srcApp, MakeCallback(&NbApp::OnNbEvent, this));

  memset(send_buf, 'x', packet_size);
}

void
NbAppClient::StopApplication()
{
  // nb__destablish(conn);
  m_nbStack->Destablish(m_conn);
  m_nbStack = nullptr;
  printf("NbClient StopApplication Done!\n");
}

} // namespace ns3
