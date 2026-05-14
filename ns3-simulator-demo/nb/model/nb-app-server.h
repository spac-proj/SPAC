#ifndef Nb_APP_SERVER_H
#define Nb_APP_SERVER_H

#include "nb-app.h"

namespace ns3 {

class NbAppServer : public NbApp {
public:
  static TypeId GetTypeId();
  NbAppServer();
  virtual ~NbAppServer() {}

private:
  int running = 1;
  char send_buf[1024];
  char recv_buf[1024];
  void OnNbEvent(int event, nb__connection_t* conn) override;
  void StartApplication() override;
  void StopApplication() override;
  nb__connection_t* m_conn;
};

} // namespace ns3

#endif // Nb_APP_SERVER_H
