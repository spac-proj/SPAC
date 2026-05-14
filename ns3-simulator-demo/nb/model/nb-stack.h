#ifndef Nb_STACK_H
#define Nb_STACK_H

#include "nb_runtime.h"
#include "ns3/object.h"
#include "ns3/event-id.h"
#include <cstdint>
#include <functional>
#include <unordered_map>
#include "nb-timer-manager.h"

namespace ns3 {
    class NbStack : public Object {
    public:
        static TypeId GetTypeId ();    

        // initialization & destruction
        NbStack(uint32_t hostId, Ptr<NetDevice> dev = nullptr);
        NbStack();
        ~NbStack();

        // transport initialization for non-ns3 runtime
        void InitTransport();    // calls nb__linux_runtime_init / ipc / mlx5_init
        void DeinitTransport();  // calls ipc_deinit

        // protocol stack initialization
        void StackInit();          // calls nb__net_init()

        // connection management
        using CallbackT = std::function<void(int /*event*/, nb__connection_t*)>;
        nb__connection_t* Establish(
            uint64_t       remoteHostId,
            uint32_t       remoteAppId,
            uint32_t       localAppId,
            CallbackT      cb);
        void       Destablish(nb__connection_t* conn);
        nb__connection_t* Accept(
            nb__connection_t* listeningConn,
            CallbackT           cb);

        // I/O interface
        int  Send(nb__connection_t* conn, const char* buf, int len);  // calls nb__send
        int  Read(nb__connection_t* conn, char* buf, int maxLen);      // calls nb__read

        // user data attachment
        void  SetUserData(nb__connection_t* conn, void* data) { nb__set_user_data(conn, data); }
        void* GetUserData(nb__connection_t* conn)              { return nb__get_user_data(conn); }
        
        void OnEvent(int event, nb__connection_t* conn);

    private:
        // C interface encapsulation
        static char*           RequestSendBuffer()   { return nb__request_send_buffer(); }
        static int             SendPacket(char* b, int l) { return nb__send_packet(b, l); }
        static void            ReturnSendBuffer(char* b) { nb__return_send_buffer(b); }
        static void            IngressStep(void* p, int l) { nb__run_ingress_step(p, l); }
        void SetNbParameters() 
        {
            if (m_hostId != 0) {
                nb__ns3_set_host(m_hostId);
            }
            if (m_localHostId != 0) {
                nb__ns3_set_local_host(m_localHostId);
            }
            if (m_state != nullptr) {
                nb__ns3_set_state(m_state);
            }
            if (m_dev != nullptr) {
                nb__ns3_set_device(m_dev);
            }
            if (m_timerManager != nullptr) {
                nb__ns3_set_timer_manager(m_timerManager);
            }
        }

        // member variables (previously global)
        uint32_t           m_hostId;               // corresponds to nb__my_host_id
        uint64_t           m_localHostId;          // corresponds to nb__my_local_host_id
        nb__net_state_t*   m_state;                // corresponds to nb__net_state
        Ptr<NetDevice> m_dev;  // NetDevice pointer for ns3 transport
        Ptr<NbTimerManager> m_timerManager; // Timer manager for ns3 transport
        bool OnDeviceReceive(Ptr<NetDevice> dev, Ptr<const Packet> p, uint16_t protocol, const Address& from);
        // void CycleConnections ();
        EventId m_cycleEvent; // Event ID for periodic connection cycling
        std::unordered_map<nb__connection_t*, CallbackT> m_callbacks;
    };
}
#endif // Nb_STACK_H