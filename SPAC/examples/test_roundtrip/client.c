#include "nb_runtime.h"
#include <stdio.h>
#include <unistd.h>

static const char CLIENT_MSG[8] = {'C','L','I','E','N','T','0','1'};

// 8-bit host IDs: inet_addr() values would alias on the low byte.
static const unsigned int CLIENT_ID = 2;
static const unsigned int SERVER_ID = 1;

static int running = 1;

static void cb(int event, nb__connection_t* c) {
    if (event == QUEUE_EVENT_READ_READY) {
        char buf[16];
        int len = nb__read(c, buf, sizeof(buf));
        printf("Client received %d bytes: ", len);
        for (int i = 0; i < len; i++) printf("%02x ", (unsigned char)buf[i]);
        printf("\n");
        running = 0;
    }
}

int main(void) {
    nb__ipc_init("/tmp/spac_ipc", 0);
    printf("[client] IPC initialized\n");

    nb__my_host_id = CLIENT_ID;
    nb__net_init();

    nb__connection_t* conn = nb__establish(SERVER_ID, 8080, 8081, cb);
    nb__send(conn, (char*)CLIENT_MSG, sizeof(CLIENT_MSG));

    while (running) {
        nb__main_loop_step();
        usleep(100 * 1000);
    }
    nb__destablish(conn);
    return 0;
}
