#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import argparse
import csv
from scapy.all import PcapReader, IP, IPv6, Ether

def pcap_to_trace(input_path, output_path, header_size, duration_ns=None):
    if not os.path.exists(input_path):
        return

    addr_to_id = {}
    next_id = 0

    def get_id(addr):
        nonlocal next_id
        if addr == "ff:ff:ff:ff:ff:ff" or addr == "255.255.255.255":
            return -1
        if addr not in addr_to_id:
            addr_to_id[addr] = next_id
            next_id += 1
        return addr_to_id[addr]

    packet_count = 0
    total_raw_size = 0
    total_body_size = 0
    first_ts = None
    last_ts = None

    try:
        with open(output_path, 'w', newline='') as csvfile:
            fieldnames = ['time', 'src_addr', 'dst_addr', 'header_size', 'body_size', 'trace_id']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            with PcapReader(input_path) as reader:
                for i, pkt in enumerate(reader):
                    ts = float(pkt.time)
                    if first_ts is None:
                        first_ts = ts
                    
                    rel_time_ns = int((ts - first_ts) * 1e9)
                    
                    if duration_ns and rel_time_ns > duration_ns:
                        break
                        
                    last_ts = ts

                    src_addr = None
                    dst_addr = None
                    
                    raw_len = len(pkt)
                    total_raw_size += raw_len
                    
                    overhead = 14
                    
                    if IP in pkt:
                        src_addr = pkt[IP].src
                        dst_addr = pkt[IP].dst
                        overhead += (pkt[IP].ihl * 4)
                    elif IPv6 in pkt:
                        src_addr = pkt[IPv6].src
                        dst_addr = pkt[IPv6].dst
                        overhead += 40
                    elif Ether in pkt:
                        src_addr = pkt[Ether].src
                        dst_addr = pkt[Ether].dst
                    else:
                        continue

                    src_id = get_id(src_addr)
                    dst_id = get_id(dst_addr)
                    
                    body_size = max(0, raw_len - overhead)
                    total_body_size += body_size
                    packet_count += 1

                    writer.writerow({
                        'time': float(rel_time_ns),
                        'src_addr': src_id,
                        'dst_addr': dst_id,
                        'header_size': header_size,
                        'body_size': body_size,
                        'trace_id': i + 1
                    })

        duration = last_ts - first_ts if last_ts and first_ts else 0
        avg_raw_size = total_raw_size / packet_count if packet_count > 0 else 0
        avg_body_size = total_body_size / packet_count if packet_count > 0 else 0
        avg_freq = packet_count / duration if duration > 0 else 0

        for addr, aid in list(addr_to_id.items())[:10]:
            print(f"  {addr} -> ID: {aid}")
        
        print(f"Converted {packet_count} packets from {input_path} to {output_path}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert PCAP file to CSV trace format")
    parser.add_argument("input_pcap")
    parser.add_argument("output_csv")
    parser.add_argument("--header_size", type=int, default=64)
    parser.add_argument("--duration", type=int)
    
    args = parser.parse_args()
    pcap_to_trace(args.input_pcap, args.output_csv, args.header_size, args.duration)
