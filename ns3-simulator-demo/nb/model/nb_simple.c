#include "nb_runtime.h"
void nb__net_init (void) {
  nb__init_timers();
  nb__net_state = malloc(sizeof(nb__net_state[0]));
  nb__assert(nb__net_state != 0, "malloc failed while allocating net_state");
  nb__net_state->num_conn = 0;
  nb__net_state->routing_table = 0;
  nb__net_state->routing_table_len = 0;
  nb__my_local_host_id = nb__routing_table_lookup_from_global(nb__my_host_id, nb__net_state->routing_table, nb__net_state->routing_table_len);
}

nb__connection_t* nb__establish (unsigned int arg0, unsigned int arg1, unsigned int arg2, void (*arg3)(int, nb__connection_t*)) {
  nb__connection_t* var56;
  unsigned int var57;
  unsigned int var58;
  unsigned int var59;
  nb__connection_t* var8;
  var8 = malloc(sizeof(var8[0]));
  var8->callback_f = arg3;
  var8->last_sent_sequence = 1010;
  var8->last_recv_sequence = 0;
  unsigned long long int var34 = nb__routing_table_lookup_from_global(arg0, nb__net_state->routing_table, nb__net_state->routing_table_len);
  var8->remote_host_id = var34;
  var8->remote_app_id = arg1;
  var8->local_app_id = arg2;
  var8->input_queue = nb__new_data_queue();
  var8->accept_queue = nb__new_accept_queue();
  int var45 = nb__net_state->num_conn;
  nb__net_state->num_conn = var45 + 1;
  nb__net_state->active_local_app_ids[var45] = arg2;
  nb__net_state->active_connections[var45] = var8;
  nb__net_state->active_remote_app_ids[var45] = arg1;
  nb__net_state->active_remote_host_ids[var45] = var34;
  if ((arg0 == nb__wildcard_host_identifier) || (arg1 == 0)) {
    var8->signaling_state = 3;
    var56 = var8;
    var57 = arg0;
    var58 = arg1;
    var59 = arg2;
    return var8;
  } else {
    var8->signaling_state = 1;
    var56 = var8;
    var57 = arg0;
    var58 = arg1;
    var59 = arg2;
    return var8;
  }
}

void nb__destablish (nb__connection_t* arg0) {
  unsigned int var8 = arg0->local_app_id;
  unsigned int var10 = arg0->remote_app_id;
  unsigned long long int var12 = arg0->remote_host_id;
  int var14 = nb__net_state->num_conn;
  for (int var15 = 0; var15 < var14; var15 = var15 + 1) {
    if (!(((nb__net_state->active_local_app_ids[var15] == var8) && (nb__net_state->active_remote_app_ids[var15] == var10)) && (nb__net_state->active_remote_host_ids[var15] == var12))) {
      continue;
    } 
    var14 = var14 - 1;
    nb__net_state->num_conn = var14;
    nb__net_state->active_local_app_ids[var15] = nb__net_state->active_local_app_ids[var14];
    nb__net_state->active_connections[var15] = nb__net_state->active_connections[var14];
    nb__net_state->active_remote_app_ids[var15] = nb__net_state->active_remote_app_ids[var14];
    nb__net_state->active_remote_host_ids[var14] = nb__net_state->active_remote_host_ids[var15];
    break;
  }
  nb__free_data_queue(arg0->input_queue);
  nb__free_accept_queue(arg0->accept_queue);
  free(arg0);
}

int nb__send (nb__connection_t* arg0, char* arg1, int arg2) {
  unsigned char* var9 = nb__request_send_buffer();
  int var10 = 0;
  int* var11 = (&(var10));
  unsigned long long int var20 = 4 + arg2;
  int* var21 = (void*)(var9 + 18);
  var21[0] = (var21[0] & -65536) | var20;
  unsigned long long int var25 = 4 + arg2;
  int* var26 = (void*)(var9 + 0);
  var26[0] = var25;
  var11[0] = arg2;
  memcpy(var9 + 20, arg1, arg2);
  arg0->last_sent_sequence = arg0->last_sent_sequence + 1;
  unsigned long long int var49 = arg0->remote_host_id;
  var49 = var49 - 16777217ll;
  unsigned long long int* var52 = (void*)(var9 + 16);
  var52[0] = (var52[0] & -16ll) | var49;
  unsigned long long int var55 = arg0->remote_app_id;
  var55 = var55 - 8079;
  unsigned short int* var58 = (void*)(var9 + 17);
  var58[0] = (var58[0] & -16) | var55;
  unsigned long long int var60 = nb__my_local_host_id;
  var60 = var60 - 16777217ll;
  unsigned char var62 = var60 & 15ll;
  unsigned char* var63 = (void*)(var9 + 16);
  var63[0] = -241 & var63[0];
  var63[0] = var63[0] | (var62 << 4);
  unsigned long long int var66 = arg0->local_app_id;
  var66 = var66 - 8079;
  unsigned char var68 = var66 & 15ll;
  unsigned char* var69 = (void*)(var9 + 17);
  var69[0] = -4081 & var69[0];
  var69[0] = var69[0] | (var68 << 4);
  unsigned long long int var81;
  int* var83 = (void*)(var9 + 0);
  var81 = var83[0];
  nb__send_packet(var9 + 16, var81);
  return var10;
}

unsigned int nb__get_dst_host_id (void* arg0) {
  unsigned long long int var2;
  unsigned long long int* var4 = (void*)(arg0 + 16);
  var2 = var4[0] & 15ll;
  return var2 + 16777217ll;
}

unsigned int nb__get_src_host_id (void* arg0) {
  unsigned long long int var2;
  unsigned char* var4 = (void*)(arg0 + 16);
  var2 = var4[0] >> 4;
  return var2 + 16777217ll;
}

void nb__run_ingress_step (void* arg0, int arg1) {
  unsigned char* var24;
  int var25;
  unsigned long long int var8;
  int* var10 = (void*)(arg0 + 18);
  var8 = var10[0] & 65535ll;
  int* var15 = (void*)(arg0 + 0);
  var15[0] = var8;
  unsigned long long int var19;
  unsigned long long int* var21 = (void*)(arg0 + 16);
  var19 = var21[0] & 15ll;
  if ((var19 + 16777217ll) != nb__my_local_host_id) {
    var24 = arg0;
    var25 = 0;
  } else {
    unsigned long long int var27;
    unsigned short int* var29 = (void*)(arg0 + 17);
    var27 = var29[0] & 15ll;
    unsigned long long int var31 = var27 + 8079;
    unsigned long long int var34;
    unsigned char* var36 = (void*)(arg0 + 17);
    var34 = var36[0] >> 4;
    unsigned long long int var39 = var34 + 8079;
    unsigned long long int var42;
    unsigned char* var44 = (void*)(arg0 + 16);
    var42 = var44[0] >> 4;
    unsigned long long int var47 = var42 + 16777217ll;
    nb__connection_t* var51 = 0;
    for (int var54 = 0; var54 < nb__net_state->num_conn; var54 = var54 + 1) {
      if (!(((nb__net_state->active_local_app_ids[var54] == var31) && (nb__net_state->active_remote_app_ids[var54] == var39)) && (nb__net_state->active_remote_host_ids[var54] == var47))) {
        continue;
      } 
      var51 = nb__net_state->active_connections[var54];
      break;
    }
    if (var51 != 0) {
      unsigned long long int var63 = (unsigned long long)(var51);
      unsigned long long int* var66 = (void*)(arg0 + 8);
      var66[0] = var63;
      unsigned long long int var69;
      unsigned long long int* var71 = (void*)(arg0 + 8);
      var69 = var71[0];
      nb__connection_t* var74 = (void*)(var69);
      unsigned long long int var78;
      int* var80 = (void*)(arg0 + 0);
      var78 = var80[0];
      int var83 = var78 - 4;
      if (var83 != 0) {
        nb__insert_data_queue(var74->input_queue, arg0 + 20, var83);
      } 
      unsigned long long int var89;
      unsigned long long int* var91 = (void*)(arg0 + 8);
      var89 = var91[0];
      nb__connection_t* var94 = (void*)(var89);
      if (var94->signaling_state == 0) {
        var94->signaling_state = 1;
      } 
      unsigned long long int var100;
      int* var102 = (void*)(arg0 + 18);
      var100 = var102[0] & 65535ll;
      int* var107 = (void*)(arg0 + 0);
      var107[0] = var100;
    } else {
      nb__connection_t* var109 = 0;
      for (int var112 = 0; var112 < nb__net_state->num_conn; var112 = var112 + 1) {
        if (!(((nb__net_state->active_local_app_ids[var112] == var31) && (nb__net_state->active_remote_app_ids[var112] == 0)) && (nb__net_state->active_remote_host_ids[var112] == nb__wildcard_host_identifier))) {
          continue;
        } 
        var109 = nb__net_state->active_connections[var112];
        break;
      }
      var51 = var109;
      if (var51 != 0) {
        nb__insert_accept_queue(var51->accept_queue, var39, var47, arg0);
        nb__connection_t* var118 = var51;
        var118->callback_f(2, var51);
      } else {
        nb__assert(0, "Failed to lookup connection");
      }
      var24 = arg0;
      var25 = 0;
    }
  }
}

void nb__reliable_redelivery_timer_cb (nb__timer* arg0, void* arg1, unsigned long long int arg2) {
  unsigned long long int var5;
  int* var7 = (void*)(arg1 + 0);
  var5 = var7[0];
  nb__send_packet(arg1 + 16, var5);
  nb__insert_timer(arg0, arg2 + 50, nb__reliable_redelivery_timer_cb, arg1);
}

