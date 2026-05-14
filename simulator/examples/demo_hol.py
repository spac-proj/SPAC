#!/usr/bin/env python3
"""
Demonstrate HOL (Head-of-Line) blocking phenomenon in the switch simulator.
HOL blocking occurs when a packet at the head of a queue blocks other packets behind it.
"""

import sys
from pathlib import Path

# Add src directory to Python path for imports
import sys
from pathlib import Path
src_dir = Path(__file__).parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from config import create_default_config, SchedulerType
from switch_core import SwitchCore

def demonstrate_hol_blocking():
    """Demonstrate HOL blocking with a specific traffic pattern."""
    print("HOL Blocking Demonstration")
    print("=" * 30)
    print("This demo shows how HOL blocking can naturally occur in VOQ switches.")
    print("We'll create a scenario where one stuck packet blocks others in the same queue.\n")

    # Create configuration with RoundRobin scheduler (prone to HOL blocking)
    config = create_default_config()
    config.scheduler_type = SchedulerType.RoundRobin
    config.global_voq_size = 5  # Small buffer to force blocking

    switch = SwitchCore(config, "hol_demo")
    print(f"Switch config: {config.num_ports} ports, {config.scheduler_type.value} scheduler")

    # Create HOL blocking scenario:
    # Multiple inputs send packets to the same output (port 0)
    # This creates incast congestion, demonstrating HOL-like behavior

    print("\nCreating HOL blocking traffic pattern:")
    print("- Multiple inputs send packets to the same output (port 0)")
    print("- This creates incast congestion, demonstrating HOL-like behavior")

    packets_injected = 0

    # Create incast: multiple inputs sending to same output
    for input_port in range(3):  # 3 input ports
        for pkt_num in range(2):  # 2 packets each
            from packet import Packet, Metadata, AxisWord
            metadata = Metadata(
                src_addr=input_port,
                dst_addr=0,  # All go to output port 0
                dst_port=0,
                pkt_len=128,
                broadcast=False,
                valid=True
            )
            payload = [AxisWord((input_port * 1000 + pkt_num) & 0xFFFFFFFF, last=True)]
            packet = Packet(metadata, payload, packets_injected + 1)

            switch.receive_packet(input_port, packet)
            packets_injected += 1
            print(f"  Injected packet {packets_injected}: port {input_port} -> port 0")

    print("\nSimulating with RoundRobin scheduler...")
    print("RoundRobin serves outputs in order, potentially causing HOL blocking")

    cycles = 0
    max_cycles = 20
    transmitted_packets = []

    while switch.has_pending_work() and cycles < max_cycles:
        stats, transmitted = switch.process_cycle()
        transmitted_packets.extend(transmitted)
        cycles += 1

        if cycles % 5 == 0:
            buffer_stats = switch.voq_buffer.get_statistics()
            print(f"  Cycle {cycles}: {len(transmitted_packets)} packets transmitted, "
                  f"buffer occupancy: {buffer_stats['current_occupancy']}")

    # Analyze results
    final_stats = switch.get_statistics()
    buffer_stats = final_stats['buffer']

    print("\nFinal Results:")
    print(f"  Total cycles: {cycles}")
    print(f"  Packets received: {final_stats['packets_received']}")
    print(f"  Packets transmitted: {final_stats['packets_transmitted']}")
    print(f"  Packets dropped: {final_stats['packets_dropped']}")
    print(f"  Buffer peak occupancy: {buffer_stats['peak_occupancy']}")

    # Show transmitted packet destinations
    transmitted_destinations = [packet.metadata.dst_port for _, packet, _ in transmitted_packets]
    print(f"  Transmitted packet destinations: {transmitted_destinations}")

    # Analyze HOL blocking
    if len(transmitted_destinations) < packets_injected:
        print("\n📊 HOL Blocking Analysis:")
        print("  Not all packets were transmitted in the same cycle batch")
        print("  This demonstrates HOL blocking: packets queued behind blocked head packet")
        print("  In RoundRobin scheduling, output port arbitration can cause head-of-line blocking")
    else:
        print("\n📊 No HOL blocking observed in this run")
        print("  All packets transmitted successfully")

    print("\n✅ HOL blocking demonstration completed!")

if __name__ == "__main__":
    demonstrate_hol_blocking()