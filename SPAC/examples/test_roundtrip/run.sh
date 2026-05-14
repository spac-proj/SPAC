#!/bin/bash
set -u

cd "$(dirname "$0")"
rm -f /tmp/spac_ipc /tmp/spac_srv.log /tmp/spac_cli.log
pkill -9 -f spac_server || true
pkill -9 -f spac_client || true
sleep 0.3

stdbuf -oL ./spac_server > /tmp/spac_srv.log 2>&1 &
SRV=$!
sleep 0.5

timeout 5 stdbuf -oL ./spac_client > /tmp/spac_cli.log 2>&1
RC=$?

sleep 0.3
wait "$SRV" 2>/dev/null || true

echo "=== client rc=$RC ==="
cat /tmp/spac_cli.log
echo "=== server ==="
cat /tmp/spac_srv.log
