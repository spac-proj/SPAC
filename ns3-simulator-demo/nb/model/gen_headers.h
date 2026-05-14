#pragma once
#include "nb_data_queue.h"
struct dynamic_struct_0;
typedef struct dynamic_struct_0 nb__connection_t;
struct dynamic_struct_0 {
  nb__accept_queue_t* accept_queue;
  void (*callback_f)(int, nb__connection_t*);
  nb__data_queue_t* input_queue;
  unsigned int last_recv_sequence;
  unsigned int last_sent_sequence;
  unsigned int local_app_id;
  unsigned int remote_app_id;
  unsigned long long int remote_host_id;
  int signaling_state;
  void* user_data;
};
struct dynamic_struct_1;
typedef struct dynamic_struct_1 nb__net_state_t;
struct dynamic_struct_1 {
  nb__connection_t* active_connections[512];
  unsigned int active_local_app_ids[512];
  unsigned int active_remote_app_ids[512];
  unsigned long long int active_remote_host_ids[512];
  int num_conn;
  struct routing_table_entry* routing_table;
  int routing_table_len;
};
static const int nb__packet_headroom = 16;
