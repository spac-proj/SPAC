NB_DIR := ../../out_demo/netblocks/
include $(NB_DIR)Makefile.frag

CC ?= cc
CFLAGS := $(NB_CFLAGS)

.PHONY: all clean
all: spac_server spac_client

spac_server: server.o $(NB_OBJS)
	$(CC) $^ -o $@

spac_client: client.o $(NB_OBJS)
	$(CC) $^ -o $@

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean: nb_clean
	rm -f spac_server spac_client server.o client.o
