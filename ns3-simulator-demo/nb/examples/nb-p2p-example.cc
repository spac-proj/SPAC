#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/nb-p2p-helper.h"
#include "ns3/nb-app-server.h"
#include "ns3/nb-app-client.h"
#include "ns3/nb-stack.h"
#include <stdio.h>
#include <unistd.h>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE ("NbExample");

char client_id[] = "1.0.0.2";
char server_id[] = "1.0.0.1";

int
main (int argc, char *argv[])
{
  CommandLine cmd;
  cmd.Parse (argc, argv);

  LogComponentEnable("NbApp", LOG_LEVEL_INFO);

  // Create two nodes
  NodeContainer nodes;
  nodes.Create (2);

  // Install our devices
  NbP2PHelper p2p;
  p2p.SetDeviceAttribute("DataRate", DataRateValue(5000000));
  p2p.SetChannelAttribute("Delay", TimeValue(MilliSeconds(2)));
  NetDeviceContainer devices = p2p.Install (nodes);

  Ptr<NbAppClient> client = CreateObject<NbAppClient> ();
  unsigned int server_id_i = ntohl(inet_addr(server_id));
  unsigned int client_id_i = ntohl(inet_addr(client_id));
  printf("client_id_i=%u, server_id_i=%u\n", client_id_i, server_id_i);
  client->Configure (devices.Get(0), client_id_i,
                     server_id_i, 8080, 8081);
  
  nodes.Get (0)->AddApplication (client);
  client->SetStartTime (Seconds (0.2));
  client->SetStopTime  (Seconds (90.0));

  Ptr<NbAppServer> server = CreateObject<NbAppServer> ();
  server->Configure (devices.Get (1), server_id_i,
                     client_id_i, 8081, 8080);
  nodes.Get (1)->AddApplication (server);
  server->SetStartTime (Seconds (0.1));
  server->SetStopTime  (Seconds (100.0));


  NS_LOG_INFO("Configure Tracing.");
  //
  // Configure ascii tracing of all enqueue, dequeue, and NetDevice receive
  // events on all devices.  Trace output will be sent to the file
  // "p2p-one-subnet.tr"
  //
  AsciiTraceHelper ascii;
  p2p.EnableAsciiAll(ascii.CreateFileStream("nb-p2p-one-subnet.tr"));

  //
  // Also configure some tcpdump traces; each interface will be traced.
  // The output files will be named:
  //
  //     p2p-one-subnet-<node ID>-<device's interface index>.pcap
  //
  // and can be read by the "tcpdump -r" command (use "-tt" option to
  // display timestamps correctly)
  //
  p2p.EnablePcapAll("nb-p2p-one-subnet", false);
  //
  // Now, do the actual simulation.
  //
  NS_LOG_INFO("Run Simulation.");
  Simulator::Run ();
  Simulator::Destroy ();
  return 0;
}
