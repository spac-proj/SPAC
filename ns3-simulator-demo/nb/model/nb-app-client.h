#ifndef Nb_APP_Client_H
#define Nb_APP_Client_H

#include "nb-app.h"

namespace ns3 {

class NbAppClient : public NbApp {
public:
  static TypeId GetTypeId();
  NbAppClient();
  virtual ~NbAppClient() {}

private:
  int running = 1;
  char send_buf[1024];
  char recv_buf[1024];
  long long start_time;
  long long end_time;

  long long stats[2000] = {0}; // 0 - 200 microsecond at granularity of 0.1 microsecond

  int count = 0;
  int packet_size = 256;
  void OnNbEvent(int event, nb__connection_t* conn) override;
  void StartApplication() override;
  void StopApplication() override;
  nb__connection_t* m_conn;
};

} // namespace ns3

#endif // Nb_APP_Client_H
