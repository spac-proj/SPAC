#!/usr/bin/env python3
"""
Example usage of the network switch simulator.
Demonstrates basic functionality.
"""

import sys
import tempfile
import csv
import os
import logging
from pathlib import Path

# Add src directory to Python path for imports
import sys
from pathlib import Path
src_dir = Path(__file__).parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

# Import modules
from config import create_default_config
from switch_core import SwitchCore
from trace_parser import TraceParser

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

def create_sample_trace() -> str:
    """Create a sample trace file."""
    trace_data = [
        [0.0, 0, 1, 64, 512, 1],      # Packet from host 0 to host 1
        [100.0, 1, 2, 64, 256, 2],    # Packet from host 1 to host 2
        [200.0, 2, 0, 64, 1024, 3],   # Packet from host 2 to host 0
        [300.0, 0, 3, 64, 128, 4],    # Packet from host 0 to host 3
        [400.0, 3, 1, 64, 768, 5],    # Packet from host 3 to host 1
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

def main():
    """Run example simulation."""
    print("Network Switch Simulator Example")
    print("=" * 35)

    # Create configuration
    config = create_default_config()
    print(f"Switch configuration: {config.num_ports} ports, {config.clock_frequency_mhz} MHz")

    # Create switch
    switch = SwitchCore(config, "example_switch")
    print("Created switch with ID: example_switch")

    # Create and load trace
    trace_file = create_sample_trace()
    try:
        parser = TraceParser(trace_file)
        entries = parser.parse_all()

        print(f"Loaded trace with {len(entries)} packets")
        print(f"Trace duration: {parser.get_time_range()[1]:.1f} ns")

        # Inject packets into switch
        for entry in entries:
            # Create packet
            from packet import Packet
            packet = Packet.from_trace_entry(
                entry.time_ns, entry.src_addr, entry.dst_addr,
                entry.header_size, entry.body_size, entry.trace_id,
                config.addr_length, config.num_ports
            )

            # Determine input port (simple hash for demo)
            input_port = entry.src_addr % config.num_ports
            switch.receive_packet(input_port, packet)

        print(f"Injected {len(entries)} packets into switch")

        # Run simulation
        print("\nRunning simulation...")
        cycle_count = 0
        max_cycles = 2000

        while switch.has_pending_work() and cycle_count < max_cycles:
            stats, transmitted_packets = switch.process_cycle()
            cycle_count += 1

            # Progress update every 500 cycles
            if cycle_count % 500 == 0:
                print(f"Cycle {cycle_count}: processed {stats['packets_processed']} packets")
                # Debug: check buffer status
                buffer_stats = switch.voq_buffer.get_statistics()
                print(f"  Buffer occupancy: {buffer_stats['current_occupancy']}")

                # Debug: check hash table
                hash_stats = switch.hash_engine.get_statistics()
                print(f"  Hash table size: {hash_stats['table_size']}")

                # Debug: check port status
                for port in range(config.num_ports):
                    port_stats = switch.get_port_status(port)
                    if port_stats['output_buffer_length'] > 0:
                        print(f"  Port {port} has {port_stats['output_buffer_length']} packets in output buffer")

        print(f"Simulation completed in {cycle_count} cycles")

        # Show final statistics
        final_stats = switch.get_statistics()
        print("\nFinal Statistics:")
        print(f"  Packets received:     {final_stats['packets_received']}")
        print(f"  Packets transmitted:  {final_stats['packets_transmitted']}")
        print(f"  Packets dropped:      {final_stats['packets_dropped']}")
        print(f"  Average latency:      {final_stats['average_latency_ns']:.2f} ns")
        print(f"  Throughput:           {final_stats['throughput_gbps']:.2f} Gbps")
        print(f"  Drop rate:            {final_stats['drop_rate']*100:.2f}%")

        # Show buffer statistics
        buffer_stats = final_stats['buffer']
        print("\nBuffer Statistics:")
        print(f"  Type:                 {buffer_stats['buffer_type']}")
        print(f"  Total enqueued:       {buffer_stats['total_enqueued']}")
        print(f"  Current occupancy:    {buffer_stats['current_occupancy']}")
        print(f"  Peak occupancy:       {buffer_stats['peak_occupancy']}")

        # Verify results
        success = (final_stats['packets_transmitted'] == len(entries) and
                  final_stats['packets_dropped'] == 0)

        if success:
            print("\n✅ Example completed successfully!")
        else:
            print("\n❌ Example had issues")

    finally:
        # Clean up
        Path(trace_file).unlink()

if __name__ == "__main__":
    main()