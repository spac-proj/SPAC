#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/nb-p2p-helper.h"
#include "ns3/nb-p2p-switch-port-device.h"
#include "ns3/nb-p2p-switch-stack.h"
#include "ns3/nb-app-client.h"
#include "ns3/nb-app-server.h"

#include <arpa/inet.h>   // ntohl / inet_addr
#include <stdio.h>
#include <vector>
using namespace ns3;

NS_LOG_COMPONENT_DEFINE("NbP2PSwitchSimple");

// Addresss for the 4 hosts
static const char* g_hostIpStr[4] = {"1.0.0.1", "1.0.0.2", "1.0.0.3", "1.0.0.4"};

int
main(int argc, char* argv[])
{
    CommandLine cmd;
    cmd.Parse(argc, argv);

    // enable needed logs
    LogComponentEnable("NbApp",           LOG_LEVEL_INFO);
    LogComponentEnable("NbP2PSwitchStack",   LOG_LEVEL_INFO);
    // LogComponentEnable("NbP2PNetDevice", LOG_LEVEL_ALL);

    /* ---------- create nodes ---------- */
    NodeContainer hosts;
    hosts.Create(4);
    Ptr<Node> swNode = CreateObject<Node>();

    /* ---------- create switch stack ---------- */
    Ptr<NbP2PSwitchStack> sw = CreateObject<NbP2PSwitchStack>();

    /* ---------- common P2P parameters ---------- */
    NbP2PHelper p2p;
    p2p.SetDeviceAttribute("DataRate", DataRateValue(1000000)); // 1 Mbps for slower simulation
    p2p.SetChannelAttribute("Delay",    TimeValue(MilliSeconds(5)));
    printf("PointToPoint channel : DataRate 1Mbps, Delay 5ms\n");

    /* ---------- create channels and devices for each Host↔Switch link ---------- */
    std::vector< Ptr<NetDevice> > hostDevs(4);  // save host side devices

    for (uint32_t i = 0; i < 4; ++i)
    {
        NetDeviceContainer tmp = p2p.Install4Switch(hosts.Get(i), swNode); // create P2P link
        hostDevs[i] = tmp.Get(0);
        sw->AttachPort(tmp.Get(1)->GetObject<NbP2PSwitchPortDevice>()); // stack attach port
    }

    /* ---------- deploy applications ---------- */
    for (uint32_t i = 0; i < 4; ++i)
    {
        uint64_t srcHost = ntohl(inet_addr(g_hostIpStr[i]));

        if (i < 2)
        {
            // client -> server
            for (uint32_t dstIdx = 2; dstIdx <= 3; dstIdx++)
            {
                uint64_t dstHost = ntohl(inet_addr(g_hostIpStr[dstIdx]));
                uint32_t localAppId = 8080 + i * 4 + dstIdx;   // client-side app id, unique for this connection
                uint32_t remoteApp  = 8080 + i * 4 + dstIdx;   // server-side app id, same as localAppId for simplicity

                Ptr<NbAppClient> cli = CreateObject<NbAppClient>();
                cli->Configure(hostDevs[i], srcHost, dstHost, localAppId, remoteApp);
                hosts.Get(i)->AddApplication(cli);

                cli->SetStartTime(Seconds(1));
                cli->SetStopTime(Seconds(999));

                printf("client host%u -> host%u : srcHost %llu dstHost %llu, local appId: %u\n",
                       i + 1, dstIdx + 1, srcHost, dstHost, localAppId);
            }
        }
        else
        {
            // server listening at two apps
            for (uint32_t cliIdx = 0; cliIdx <= 1; cliIdx++)
            {
                uint32_t localAppId = 8080 + cliIdx * 4 + i; // server-side app id, unique for this connection

                Ptr<NbAppServer> srv = CreateObject<NbAppServer>();
                // Wildcard host identifier is used to listen for any client app, not known in advance
                // Also dst_app_id is set to 0 as wildcard
                // The wildcard should be used at the same time due to implementation of NetBlocks
                srv->Configure(hostDevs[i], srcHost, nb__wildcard_host_identifier, localAppId, 0);
                hosts.Get(i)->AddApplication(srv);

                srv->SetStartTime(Seconds(0));
                srv->SetStopTime(Seconds(1000));

                printf("server host%u, appId: %u\n", i + 1, localAppId);
            }
        }
    }

    // begin running the simulation
    NS_LOG_INFO("Run Simulation.");
    Simulator::Run();
    Simulator::Destroy();
    return 0;
}