#!/usr/bin/env python3
"""



"""

import sys
import json
from pathlib import Path

# Add src directory to Python path for imports
import sys
from pathlib import Path
src_dir = Path(__file__).parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from config import create_default_config, SchedulerType, BufferType
from simulation import NetworkSimulator


def analyze_switch_performance(stats, switch_id):
""""""
#     print(f"\n[switch] {switch_id} performance summary:")

    switch_stats = stats['switches'][switch_id]

#     print(f"  basic metrics:")
#     print(f"    throughput:   {switch_stats['throughput_gbps']:.2f} Gbps")
#     print(f"    avg latency:  {switch_stats['average_latency_ns']:.2f} ns")
#     print(f"    drop rate:    {switch_stats['drop_rate']:.4f}")
#     print(f"    packet count: {switch_stats['packets_received']} RX / {switch_stats['packets_transmitted']} TX")

    buffer_stats = switch_stats['buffer']
#     print(f"  buffer state:")
#     print(f"    type:                   {buffer_stats['buffer_type']}")
#     print(f"    utilization (overall):  {buffer_stats['overall_utilization']:.3f} (peak: {buffer_stats['peak_utilization']:.3f})")
#     print(f"    average queue length:   {buffer_stats['average_queue_length']:.2f}")
#     print(f"    HOL blocking events:    {buffer_stats['hol_blocking_events']}")

    scheduler_stats = switch_stats['scheduler']
#     print(f"  scheduler performance:")
#     print(f"    algorithm:             {scheduler_stats['scheduler_type']}")
#     print(f"    scheduling efficiency: {scheduler_stats['scheduling_efficiency']:.3f}")
#     print(f"    conflict rate:         {scheduler_stats['conflict_rate']:.3f}")
#     print(f"    fairness index:        {scheduler_stats['fairness_index']:.3f}")

    port_stats = switch_stats['port_statistics']
#     print(f"  port utilization (top 4):")
    port_utilizations = [(port, data['utilization']) for port, data in port_stats.items()]
    port_utilizations.sort(key=lambda x: x[1], reverse=True)

    for port_id, utilization in port_utilizations[:4]:
        data = port_stats[port_id]
        status = "🔴" if utilization > 0.8 else "🟡" if utilization > 0.5 else "🟢"
        print(f"    {status} Port {port_id}: {utilization:.3f} ({data['packets_transmitted']} pkts)")


def analyze_network_topology(stats):
""""""
#     print(f"\n[network] topology analysis:")

    topology = stats['topology']
    network = stats['network']

#     print(f"  topology info:")
#     print(f"    type:           {topology['topology_type']}")
#     print(f"    num switches:   {topology['num_switches']}")
#     print(f"    num hosts:      {topology['num_hosts']}")
#     print(f"    num links:      {topology['num_links']}")

#     print(f"  network performance:")
#     print(f"    total throughput: {network['network_throughput_gbps']:.2f} Gbps")
#     print(f"    avg latency:      {network['avg_packet_latency_ns']:.2f} ns")
#     print(f"    avg hops:         {network.get('avg_hops', 0):.2f}")
#     print(f"    completed pkts:   {network['completed_packets']}")

    if 'end_to_end_metrics' in network:
        e2e = network['end_to_end_metrics']
#         print(f"  end-to-end latency:")
#         print(f"    median: {e2e.get('median_flow_completion_time_ns', 0):.2f} ns")
#         print(f"    p95:    {e2e.get('p95_flow_completion_time_ns', 0):.2f} ns")
#         print(f"    p99:    {e2e.get('p99_flow_completion_time_ns', 0):.2f} ns")


def analyze_host_performance(stats):
""""""
#     print(f"\n[hosts] performance analysis:")

    hosts = stats['hosts']
#     print(f"  per-host stats ({len(hosts)} hosts):")

    host_throughput = [(hid, hstats['throughput_gbps']) for hid, hstats in hosts.items()]
    host_throughput.sort(key=lambda x: x[1], reverse=True)

    for host_id, throughput in host_throughput[:5]:  # Top 5
        hstats = hosts[host_id]
        loss_rate = hstats['loss_rate']
        status = "🔴" if loss_rate > 0.1 else "🟡" if loss_rate > 0.01 else "🟢"
        print(f"    {status} Host {host_id}: {throughput:.3f} Gbps, "
              f"={hstats['average_latency_ns']:.2f}ns, "
              f"={loss_rate:.4f}")


def compare_architectures(stats1, stats2, name1, name2):
""""""
#     print(f"\n[compare] architectures: {name1} vs {name2}")

    network1 = stats1['network']
    network2 = stats2['network']

#     print(f"  throughput:")
    print(f"    {name1}: {network1['network_throughput_gbps']:.2f} Gbps")
    print(f"    {name2}: {network2['network_throughput_gbps']:.2f} Gbps")

    throughput_diff = network2['network_throughput_gbps'] - network1['network_throughput_gbps']
    throughput_pct = (throughput_diff / network1['network_throughput_gbps']) * 100 if network1['network_throughput_gbps'] > 0 else 0
#     print(f"    delta: {throughput_diff:+.2f} Gbps ({throughput_pct:+.1f}%)")

#     print(f"  latency:")
    print(f"    {name1}: {network1['avg_packet_latency_ns']:.2f} ns")
    print(f"    {name2}: {network2['avg_packet_latency_ns']:.2f} ns")

    latency_diff = network2['avg_packet_latency_ns'] - network1['avg_packet_latency_ns']
    latency_pct = (latency_diff / network1['avg_packet_latency_ns']) * 100 if network1['avg_packet_latency_ns'] > 0 else 0
#     print(f"    delta: {latency_diff:+.2f} ns ({latency_pct:+.1f}%)")


def main():
""""""
#     print("Enhanced statistics demo")
    print("=" * 50)

#     print("\n[arch 1] single switch (8 ports, iSLIP scheduler)")
    config1 = create_default_config()
    config1.num_ports = 8
    config1.scheduler_type = SchedulerType.iSLIP
    config1.buffer_type = BufferType.NBuffersPerPort

    sim1 = NetworkSimulator(config1)
    sim1.load_topology(str(Path(__file__).parent / "topology" / "single_switch_8hosts.csv"))
    stats1 = sim1.run_simulation(max_time_ns=100000.0)

    analyze_switch_performance(stats1, 'switch_0')
    analyze_network_topology(stats1)
    analyze_host_performance(stats1)

#     print("\n[arch 2] multi-switch leaf-spine (3 switches, iSLIP scheduler)")
    config2 = create_default_config()
    config2.num_ports = 4
    config2.scheduler_type = SchedulerType.iSLIP

    sim2 = NetworkSimulator(config2)
    sim2.load_topology(str(Path(__file__).parent / "topology" / "ring_8hosts.csv"))
    stats2 = sim2.run_simulation(max_time_ns=50000.0)

    for switch_id in stats2['switches']:
        analyze_switch_performance(stats2, switch_id)

    analyze_network_topology(stats2)
    analyze_host_performance(stats2)

    compare_architectures(stats1, stats2, "", "")

    with open('architecture_comparison.json', 'w') as f:
        json.dump({
            'single_switch': stats1,
            'multi_switch_leaf_spine': stats2
        }, f, indent=2)

#     print("\n[saved] detailed stats written to: architecture_comparison.json")
#     print("\n[conclusions]")
#     print("- multi-switch fabrics scale better and balance load more evenly")
#     print("- a single switch has lower latency but bottlenecks under load")
#     print("- buffer utilization reflects network congestion patterns")
#     print("- scheduler efficiency drives end-to-end performance")
#     print("- per-port stats highlight where bottlenecks form")

#     print("\n[done]")


if __name__ == "__main__":
    main()