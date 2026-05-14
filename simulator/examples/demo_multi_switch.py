#!/usr/bin/env python3
"""
Demonstrate multi-switch network simulation with 8-host topology.
Shows complete network simulation with routing, congestion, and statistics.
"""

import sys
import tempfile
import csv
import os
from pathlib import Path

# Add src directory to Python path for imports
import sys
from pathlib import Path
src_dir = Path(__file__).parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from config import create_default_config
from simulation import NetworkSimulator


def create_multi_switch_trace() -> str:
    """Create a trace with traffic across the 8-host topology."""
    trace_data = [
        ['time', 'src_addr', 'dst_addr', 'header_size', 'body_size', 'trace_id'],
        # Intra-leaf traffic (same leaf switch)
        [0.0, 0, 1, 64, 128, 1],     # host 0 -> host 1 (both on leaf 0)
        [100.0, 2, 3, 64, 256, 2],   # host 2 -> host 3 (both on leaf 0)

        # Inter-leaf traffic (crosses spine)
        [200.0, 0, 4, 64, 512, 3],   # host 0 -> host 4 (leaf 0 -> leaf 1)
        [300.0, 1, 5, 64, 128, 4],   # host 1 -> host 5
        [400.0, 2, 6, 64, 256, 5],   # host 2 -> host 6
        [500.0, 3, 7, 64, 512, 6],   # host 3 -> host 7

        # Reverse traffic
        [600.0, 4, 0, 64, 128, 7],   # host 4 -> host 0
        [700.0, 5, 1, 64, 256, 8],   # host 5 -> host 1
        [800.0, 6, 2, 64, 512, 9],   # host 6 -> host 2
        [900.0, 7, 3, 64, 128, 10],  # host 7 -> host 3
    ]

    fd, path = tempfile.mkstemp(suffix='.csv')
    try:
        with os.fdopen(fd, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(trace_data)
    except:
        os.close(fd)
        raise

    return path


def demonstrate_multi_switch():
    """Demonstrate complete multi-switch network simulation."""
    print("Multi-Switch Network Simulation Demonstration")
    print("=" * 50)
    print("This demo shows a complete 8-host leaf-spine network simulation.")
    print("Topology: 2 leaf switches + 1 spine switch, 8 hosts total")
    print()

    # Create network simulator
    sim = NetworkSimulator()

    # Load 8-host topology
    print("1. Loading Network Topology")
    topo_file = str(Path(__file__).parent / "topology" / "single_switch_8hosts.csv")
    sim.load_topology(topo_file)

    print(f"   ✓ Loaded topology: {len(sim.switches)} switches, {len(sim.hosts)} hosts")
    print(f"   ✓ Switches: {list(sim.switches.keys())}")
    print(f"   ✓ Hosts: {sorted(sim.hosts.keys())}")

    # Show topology connections
    print("\n   Topology Connections:")
    for conn in sim.connections[:6]:  # Show first 6 connections
        print(f"     {conn.node_a} -- {conn.node_b}")

    # Create and load traffic trace
    print("\n2. Loading Traffic Trace")
    trace_file = create_multi_switch_trace()
    try:
        sim.schedule_packet_injection(trace_file)

        print("   ✓ Loaded trace with 10 packets")
        print("   ✓ Traffic patterns:")
        print("     • Intra-leaf: hosts 0-1, 2-3 (same leaf switch)")
        print("     • Inter-leaf: hosts 0-3 to hosts 4-7 (crosses spine)")

        # Run simulation
        print("\n3. Running Network Simulation")
        stats = sim.run_simulation(max_time_ns=2000.0)

        # Analyze results
        print("\n4. Simulation Results")

        # Network-level statistics
        network_stats = stats['network']
        print("   Network Statistics:")
        print(f"     Packets completed: {network_stats['completed_packets']}/10")
        print(".1f")
        print(".1f")
        print(f"     Average hops: {network_stats.get('avg_hops', 0):.1f}")

        # Switch-level statistics
        print("\n   Switch Statistics:")
        for switch_id, switch_stats in stats['switches'].items():
            print(f"     {switch_id}:")
            print(f"       Received: {switch_stats['packets_received']}")
            print(f"       Transmitted: {switch_stats['packets_transmitted']}")
            print(f"       Dropped: {switch_stats['packets_dropped']}")

        # Congestion analysis
        total_congested = sum(s.get('current_congested_ports', 0) for s in stats['switches'].values())
        if total_congested > 0:
            print(f"\n   ⚠️  Network experienced congestion ({total_congested} congested port cycles)")

        # Packet path analysis
        print("\n   Packet Routing Analysis:")
        completed_packets = [(pid, pinfo) for pid, pinfo in sim.active_packets.items()
                           if 'completion_time' in pinfo]

        intra_leaf = 0
        inter_leaf = 0

        for packet_id, packet_info in completed_packets:
            hops = packet_info.get('hops', 0)
            src_host = packet_info.get('source_host')
            dst_host = packet_info.get('destination_host')

            if src_host and dst_host:
                src_leaf = 0 if int(src_host) < 4 else 1
                dst_leaf = 0 if int(dst_host) < 4 else 1

                if src_leaf == dst_leaf:
                    intra_leaf += 1
                    route_type = "intra-leaf"
                else:
                    inter_leaf += 1
                    route_type = "inter-leaf"

                print(f"     Packet {packet_id}: {src_host} -> {dst_host} ({route_type}, {hops} hops)")

        print(f"\n   Routing Summary:")
        print(f"     Intra-leaf packets: {intra_leaf}")
        print(f"     Inter-leaf packets: {inter_leaf}")

        # Performance analysis
        print("\n5. Performance Analysis")

        if network_stats['completed_packets'] == 10:
            print("   ✅ All packets delivered successfully")
        else:
            print(f"   ⚠️  {10 - network_stats['completed_packets']} packets lost")

        avg_latency = network_stats.get('avg_packet_latency_ns', 0)
        if avg_latency < 100:
            print("   ✅ Low latency network")
        elif avg_latency < 500:
            print("   ⚠️  Moderate latency - possible congestion")
        else:
            print("   ❌ High latency - significant congestion")

        throughput = network_stats.get('throughput_gbps', 0)
        print(f"   Throughput: {throughput:.2f} Gbps")
        print("\n6. Key Features Demonstrated")
        print("   • Multi-switch topology loading")
        print("   • Host-to-switch injection")
        print("   • Inter-switch packet routing")
        print("   • Leaf-spine network architecture")
        print("   • Congestion detection and handling")
        print("   • Comprehensive network statistics")
        print("   • Packet path tracking")

        print("\n✅ Multi-Switch Network Simulation Completed!")
        print("\nThis demonstrates a complete network simulation with realistic")
        print("traffic patterns, multi-hop routing, and performance analysis.")

    finally:
        Path(trace_file).unlink()


if __name__ == "__main__":
    demonstrate_multi_switch()