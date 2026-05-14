#!/usr/bin/env python3

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add src directory to Python path for imports
src_dir = Path(__file__).parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from config import create_default_config, load_config, SwitchConfig, BufferType
from simulation import NetworkSimulator


def load_switch_config(config_file: str):
    """Load and validate switch configuration from YAML file."""
    if not Path(config_file).exists():
        raise FileNotFoundError(f"Configuration file not found: {config_file}")

    config = load_config(config_file)
    
    # Print buffer configuration details
    if config.buffer_type == BufferType.OneBufferPerPort:
        if config.voq_sizes:
            total = sum(config.voq_sizes)
            print(f"   Buffer type: OneBufferPerPort (one shared queue per output)")
            print(f"   Total capacity: {total} bytes ({len(config.voq_sizes)} queues)")
        else:
            print(f"   Buffer type: OneBufferPerPort (one shared queue per output)")
            print(f"   Global capacity: {config.global_voq_size} bytes/queue, total {config.global_voq_size * config.num_ports} bytes")
    else:
        print(f"   Buffer type: NBuffersPerPort (one queue per src-dst pair)")
        if config.voq_sizes:
            total = sum(config.voq_sizes)
            print(f"   Total capacity: {total} bytes ({len(config.voq_sizes)} queues)")
        else:
            n = config.num_ports
            total = config.global_voq_size * n * (n - 1)
            print(f"   Global capacity: {config.global_voq_size} bytes/queue, total {total} bytes")
    
    return config


def load_topology(topology_file: str) -> str:
    """Load network topology from CSV file."""
    if not Path(topology_file).exists():
        raise FileNotFoundError(f"Topology file not found: {topology_file}")

    print(f"Loading network topology: {topology_file}")
    return topology_file


def load_trace_file(trace_file: str) -> str:
    """Load traffic trace from CSV file."""
    if not Path(trace_file).exists():
        raise FileNotFoundError(f"Trace file not found: {trace_file}")

    print(f"Loading traffic trace: {trace_file}")
    return trace_file


def print_buffer_statistics(stats: Dict[str, Any]):
    """Print detailed buffer statistics from simulation results."""
    for switch_id, sw_stats in stats.get('switches', {}).items():
        buffer_stats = sw_stats.get('buffer', {})
        
        print(f"\nBuffer Statistics for {switch_id}:")
        print(f"   Type: {buffer_stats.get('buffer_type', 'Unknown')}")
        print(f"   Organization: {buffer_stats.get('organization', 'Unknown')}")
        print(f"   Total Enqueued: {buffer_stats.get('total_enqueued', 0)}")
        print(f"   Total Dequeued: {buffer_stats.get('total_dequeued', 0)}")
        print(f"   Total Dropped: {buffer_stats.get('total_dropped', 0)} (Overflow: {buffer_stats.get('total_dropped_overflow', 0)})")
        print(f"   Drop Rate: {buffer_stats.get('drop_rate', 0)*100:.2f}%")
        print(f"   Peak Memory Used: {buffer_stats.get('peak_memory_used', buffer_stats.get('peak_occupancy', 0))} bytes")
        
        # Print peak VOQ distribution
        peak_voq = buffer_stats.get('peak_voq_sizes', {})
        if peak_voq:
            print(f"   Peak VOQ Distribution:")
            if buffer_stats.get('organization') == 'per_output_port':
                # OneBufferPerPort
                for dst, peak in peak_voq.items():
                    if peak > 0:
                        print(f"      dst_{dst}: {peak} bytes")
            else:
                # NBuffersPerPort
                for (src, dst), peak in peak_voq.items():
                    if peak > 0:
                        print(f"      {src}->{dst}: {peak} bytes")


def run_simulation(config_file: str, topology_file: str, trace_file: str,
                  max_time_ns: float = 100000.0, output_file: str = None,
                  voq_sizes: Optional[List[int]] = None) -> Dict[str, Any]:
    """
    Run cycle-accurate network switch simulation.

    Args:
        config_file: Path to switch configuration YAML file
        topology_file: Path to network topology CSV file
        trace_file: Path to packet injection trace CSV file
        max_time_ns: Maximum simulation time in nanoseconds (default: 100000)
        output_file: Output file path for JSON results (optional)
        voq_sizes: List of VOQ sizes specified from command line (optional)

    Returns:
        Dictionary containing simulation statistics
    """
    print("Starting network switch simulation...")
    print("=" * 50)

    # Load switch configuration
    config = load_switch_config(config_file)
    
    # Override VOQ sizes if provided from command line
    if voq_sizes:
        config.voq_sizes = voq_sizes
        print(f"   Using command-line specified VOQ sizes: {voq_sizes}")

    # Create simulator with loaded configuration
    sim = NetworkSimulator(config)

    # Load network topology
    topo_path = load_topology(topology_file)
    sim.load_topology(topo_path)

    # Load traffic trace
    trace_path = load_trace_file(trace_file)
    sim.schedule_packet_injection(trace_path)

    # Run simulation
    print(f"Running simulation (max time: {max_time_ns} ns)...")
    stats = sim.run_simulation(max_time_ns=max_time_ns)

    # Output results
    if output_file:
        print(f"Saving results to: {output_file}")
        
        def convert_for_json(obj):
            if isinstance(obj, dict):
                new_dict = {}
                for k, v in obj.items():
                    if isinstance(k, tuple):
                        new_key = f"{k[0]}_{k[1]}"
                    else:
                        new_key = k
                    new_dict[new_key] = convert_for_json(v)
                return new_dict
            elif isinstance(obj, list):
                return [convert_for_json(item) for item in obj]
            else:
                return obj
        
        json_stats = convert_for_json(stats)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(json_stats, f, indent=2, ensure_ascii=False)
    else:
        # Print summary to console
        print("\nSimulation Results Summary:")
        network_stats = stats['network']
        print(f"  Completed packets: {network_stats['completed_packets']}")
        print(f"  Network throughput: {network_stats['network_throughput_gbps']:.2f} Gbps")
        print(f"  Average latency: {network_stats['avg_packet_latency_ns']:.2f} ns")
        print(f"  Average hops: {network_stats.get('avg_hops', 0):.2f}")
        print(f"  Last packet completion time: {network_stats.get('last_packet_completion_time_ns', 0):.2f} ns")

        print(f"  Number of switches: {stats['topology']['num_switches']}")
        print(f"  Number of hosts: {stats['topology']['num_hosts']}")
        
        # Print buffer statistics
        print_buffer_statistics(stats)

    print("Simulation complete!")
    return stats


def create_examples_directory():
    """Create example configuration, topology, and trace directories."""
    examples_dir = Path(__file__).parent.parent / "examples"
    examples_dir.mkdir(exist_ok=True)

    # Create subdirectories
    (examples_dir / "switch_config").mkdir(exist_ok=True)
    (examples_dir / "topology").mkdir(exist_ok=True)
    (examples_dir / "trace").mkdir(exist_ok=True)

    print(f"Creating example directories: {examples_dir}")
    
    # Create example configurations
    _create_example_configs(examples_dir)


def _create_example_configs(examples_dir: Path):
    """Create example switch configuration files."""
    from config import save_config, SwitchConfig, BufferType, HashModuleType, SchedulerType
    
    # Create OneBufferPerPort (1b1p) example configuration
    config_1b1p = SwitchConfig(
        num_ports=8,
        hash_module_type=HashModuleType.FullLookupTable,
        buffer_type=BufferType.OneBufferPerPort,
        scheduler_type=SchedulerType.iSLIP,
        global_voq_size=4096,
        axis_data_width=512,
        clock_frequency_mhz=250.0
    )
    save_config(config_1b1p, str(examples_dir / "switch_config" / "1b1p_8port.yaml"))
    
    # Create NBuffersPerPort (nb1p) example configuration
    config_nb1p = SwitchConfig(
        num_ports=8,
        hash_module_type=HashModuleType.FullLookupTable,
        buffer_type=BufferType.NBuffersPerPort,
        scheduler_type=SchedulerType.iSLIP,
        global_voq_size=1024,
        axis_data_width=512,
        clock_frequency_mhz=250.0
    )
    save_config(config_nb1p, str(examples_dir / "switch_config" / "nb1p_8port.yaml"))
    
    print("Example configuration files created")


def parse_voq_sizes(voq_sizes_str: str) -> List[int]:
    """Parse comma-separated VOQ sizes from command line argument."""
    if not voq_sizes_str:
        return None
    
    try:
        sizes = [int(x.strip()) for x in voq_sizes_str.split(',')]
        return sizes
    except ValueError as e:
        raise ValueError(f"Failed to parse voq_sizes: {voq_sizes_str}, error: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Cycle-accurate network switch simulator with traffic trace support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument('--config', '-c', required=True,
                       help='Path to switch configuration YAML file')
    parser.add_argument('--topology', '-t', required=True,
                       help='Path to network topology CSV file')
    parser.add_argument('--trace', '-r', required=True,
                       help='Path to packet injection trace CSV file')
    parser.add_argument('--output', '-o',
                       help='Path to output JSON file for results')
    parser.add_argument('--max-time', '-m', type=float, default=100000.0,
                       help='Maximum simulation time in nanoseconds (default: 100000)')
    parser.add_argument('--voq-sizes', 
                       help='Comma-separated list of VOQ sizes to override configuration')
    parser.add_argument('--create-examples', action='store_true',
                       help='Create example configuration files and exit')

    args = parser.parse_args()

    try:
        if args.create_examples:
            create_examples_directory()
            return 0

        # Parse VOQ sizes if provided
        voq_sizes = parse_voq_sizes(args.voq_sizes) if args.voq_sizes else None

        # Run simulation
        stats = run_simulation(
            config_file=args.config,
            topology_file=args.topology,
            trace_file=args.trace,
            max_time_ns=args.max_time,
            output_file=args.output,
            voq_sizes=voq_sizes
        )

        return 0

    except Exception as e:
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
