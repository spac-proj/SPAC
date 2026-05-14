#!/usr/bin/env python3
"""
Simple example demonstrating basic switch functionality.
This example shows how the simulator works without complex imports.
"""

import sys
import tempfile
import csv
import os
from pathlib import Path
import math

# Add simulator directory to Python path
simulator_dir = Path(__file__).parent
sys.path.insert(0, str(simulator_dir))

def create_sample_config():
    """Create a simple configuration object."""
    class Config:
        def __init__(self):
            self.num_ports = 4
            self.addr_length = 4
            self.hash_bits = 7
            self.axis_data_width = 512
            self.clock_frequency_mhz = 200.0
            self.hash_module_type = "FullLookupTable"
            self.buffer_type = "OneBufferPerPort"
            self.scheduler_type = "RoundRobin"
            self.max_queue_depth_log = 3
            self.max_queue_depth = 8

    return Config()

def create_sample_trace() -> str:
    """Create a sample trace file."""
    trace_data = [
        [0.0, 0, 1, 64, 512, 1],      # Packet from host 0 to host 1
        [100.0, 1, 2, 64, 256, 2],    # Packet from host 1 to host 2
        [200.0, 2, 0, 64, 1024, 3],   # Packet from host 2 to host 0
        [300.0, 0, 3, 64, 128, 4],    # Packet from host 0 to host 3
    ]

    fd, path = tempfile.mkstemp(suffix='.csv')
    try:
        with os.fdopen(fd, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['time', 'src_addr', 'dst_addr', 'header_size', 'body_size', 'trace_id'])
            writer.writerows(trace_data)
    except:
        os.close(fd)
        raise

    return path

def simple_packet_class():
    """Simple packet class for demonstration."""
    class Metadata:
        def __init__(self, src_addr, dst_addr, pkt_len):
            self.src_addr = src_addr
            self.dst_addr = dst_addr
            self.pkt_len = pkt_len
            self.broadcast = False
            self.valid = True

    class AxisWord:
        def __init__(self, data, last=False):
            self.data = data
            self.last = last

    class Packet:
        def __init__(self, metadata, payload, trace_id=None):
            self.metadata = metadata
            self.payload = payload
            self.trace_id = trace_id
            self.arrival_time_ns = 0.0

        @property
        def total_bytes(self):
            return len(self.payload) * 64

    return Metadata, AxisWord, Packet

def main():
    """Run simple example."""
    print("Simple Network Switch Simulator Example")
    print("=" * 40)

    # Create configuration
    config = create_sample_config()
    print(f"Switch configuration: {config.num_ports} ports, {config.clock_frequency_mhz} MHz")

    # Define simple classes
    Metadata, AxisWord, Packet = simple_packet_class()

    # Create sample packets
    packets = []

    # Packet 1: host 0 -> host 1
    meta1 = Metadata(0, 1, 576)  # 64 + 512
    payload1 = [AxisWord(0x10001, False), AxisWord(0x20002, False), AxisWord(0x30003, False),
                AxisWord(0x40004, False), AxisWord(0x50005, False), AxisWord(0x60006, False),
                AxisWord(0x70007, False), AxisWord(0x80008, False), AxisWord(0x90009, True)]
    packet1 = Packet(meta1, payload1, 1)
    packets.append(packet1)

    # Packet 2: host 1 -> host 2
    meta2 = Metadata(1, 2, 320)  # 64 + 256
    payload2 = [AxisWord(0x10001, False), AxisWord(0x20002, False), AxisWord(0x30003, False),
                AxisWord(0x40004, False), AxisWord(0x50005, True)]
    packet2 = Packet(meta2, payload2, 2)
    packets.append(packet2)

    print(f"Created {len(packets)} sample packets")

    # Simple forwarding table (address -> port mapping)
    forwarding_table = {
        0: 0,  # host 0 -> port 0
        1: 1,  # host 1 -> port 1
        2: 2,  # host 2 -> port 2
        3: 3,  # host 3 -> port 3
    }

    # Simulate switch operation
    print("\nSimulating switch operation...")

    # Initialize switch state
    input_queues = [[] for _ in range(config.num_ports)]  # Per-port input queues
    output_queues = [[] for _ in range(config.num_ports)]  # Per-port output queues

    # Inject packets
    for packet in packets:
        dst_port = forwarding_table.get(packet.metadata.dst_addr, 0)
        packet.metadata.dst_port = dst_port
        input_port = packet.metadata.src_addr % config.num_ports
        input_queues[input_port].append(packet)
        print(f"Injected packet {packet.trace_id}: port {input_port} -> port {dst_port}")

    # Simulate processing cycles
    cycle_count = 0
    max_cycles = 50
    processed_packets = 0

    while any(input_queues) and cycle_count < max_cycles:
        cycle_count += 1

        # Simple round-robin scheduling
        for output_port in range(config.num_ports):
            if not input_queues[output_port]:  # No packets waiting for this output
                continue

            # Get packet for this output
            packet = input_queues[output_port].pop(0)
            output_queues[output_port].append(packet)
            processed_packets += 1

            print(f"Cycle {cycle_count}: Scheduled packet {packet.trace_id} on output port {output_port}")
            break  # Only one packet per cycle in this simple example

    print(f"\nSimulation completed in {cycle_count} cycles")
    print(f"Processed {processed_packets} packets")

    # Show results
    total_bytes = sum(packet.total_bytes for packet in packets)
    avg_packet_size = total_bytes / len(packets)
    simulated_time_ns = cycle_count * (1e9 / config.clock_frequency_mhz)
    throughput_gbps = (total_bytes * 8) / simulated_time_ns

    print("\nResults:")
    print(f"  Total packets:        {len(packets)}")
    print(f"  Total bytes:          {total_bytes}")
    print(f"  Average packet size:  {avg_packet_size:.1f} bytes")
    print(f"  Simulated time:       {simulated_time_ns:.1f} ns")
    print(f"  Throughput:           {throughput_gbps:.2f} Gbps")

    # Clean up
    trace_file = create_sample_trace()
    Path(trace_file).unlink()

    print("\n✅ Simple example completed successfully!")

if __name__ == "__main__":
    main()