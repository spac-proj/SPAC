#!/usr/bin/env python3
"""
Run user-specified config alongside a baseline and compare latency.

Baseline: NBuffersPerPort + iSLIP + MultiBankHash (same ports/voq/bus/clock).

Usage:
  python baseline_compare.py -t topology.csv -r trace.csv -p 8 \
      --scheduler EDRRM --buffer NBuffersPerPort --hash FullLookupTable

  python baseline_compare.py -t topology.csv -r trace.csv -p 8 \
      --scheduler RoundRobin --buffer OneBufferPerPort --hash FullLookupTable \
      --voq-size 8192 --bus-width 256 --clock 200

  python baseline_compare.py -t topology.csv -r trace.csv --json
"""

import sys
import json
import argparse
from pathlib import Path
from types import SimpleNamespace

src_dir = Path(__file__).parent.parent.parent / "simulator" / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from config import (
    SwitchConfig, HashModuleType, BufferType, SchedulerType,
    LatencyEstimator,
)
from simulation import NetworkSimulator


SCHEDULER_CHOICES = [e.value for e in SchedulerType]
BUFFER_CHOICES = [e.value for e in BufferType]
HASH_CHOICES = [e.value for e in HashModuleType]


def _run_one(topology, trace, max_time, num_ports, voq_size, bus_width,
             clock, scheduler, buffer, hash_mod, label=""):
    """Run a single simulation and return a result dict."""
    import time as _time

    config = SwitchConfig(
        num_ports=num_ports,
        hash_module_type=HashModuleType(hash_mod),
        buffer_type=BufferType(buffer),
        scheduler_type=SchedulerType(scheduler),
        global_voq_size=voq_size,
        axis_data_width=bus_width,
        clock_frequency_mhz=clock,
    )

    tag = f"{scheduler}/{buffer}/{hash_mod}"
    hlat = LatencyEstimator.estimate_hash_latency(config.hash_module_type, num_ports)
    slat = LatencyEstimator.estimate_scheduler_latency(config.scheduler_type, config.buffer_type, num_ports)
    sii = LatencyEstimator.estimate_scheduler_ii(config.scheduler_type)
    print(f"  [{label}] Config: {tag}  Bus={bus_width}b  Ports={num_ports}")
    print(f"  [{label}] Pipeline: HashLat={hlat}  SchedLat={slat}  SchedII={sii}")

    sim = NetworkSimulator(config)
    sim.load_topology(topology)
    sim.schedule_packet_injection(trace)

    total_events = len(sim.event_queue)
    import csv as _csv
    with open(trace) as _f:
        total_pkts = sum(1 for _ in _csv.reader(_f)) - 1
    print(f"  [{label}] Trace loaded: {total_pkts} packets, max_time={max_time:.0f}ns")

    t0 = _time.time()
    stats = sim.run_simulation(max_time_ns=max_time)
    elapsed = _time.time() - t0

    switch_id = list(stats['switches'].keys())[0]
    sw = stats['switches'][switch_id]
    tx = sw.get('packets_transmitted', 0)
    rx = sw.get('packets_received', 0)
    drop = sw.get('packets_dropped', 0)
    cycles = sw.get('current_cycle', 0)
    print(f"  [{label}] Done in {elapsed:.2f}s  "
          f"RX={rx} TX={tx} Drop={drop}")

    mod = sw.get('module_activity', {})
    lr = sw.get('line_rate_stats', {})
    rx_agg = mod.get('rx_engine', {}).get('aggregate', {})
    achieved = lr.get('achieved_cycles', 0)
    missed = lr.get('missed_cycles', 0)

    sched_lat = LatencyEstimator.estimate_scheduler_latency(
        config.scheduler_type, config.buffer_type, config.num_ports)
    sched_ii = LatencyEstimator.estimate_scheduler_ii(config.scheduler_type)

    return {
        'configuration': {
            'scheduler': scheduler,
            'buffer': buffer,
            'hash': hash_mod,
            'num_ports': num_ports,
            'voq_size': voq_size,
            'bus_width': bus_width,
            'clock_mhz': clock,
            'scheduler_latency_cycles': sched_lat,
            'scheduler_ii_cycles': sched_ii,
        },
        'packets': {
            'received': sw.get('packets_received', 0),
            'transmitted': sw.get('packets_transmitted', 0),
            'dropped': sw.get('packets_dropped', 0),
            'drop_rate': sw.get('drop_rate', 0.0),
        },
        'latency': {
            'avg_ns': sw.get('average_latency_ns', 0.0),
            'total_cycles': sw.get('current_cycle', 0),
        },
        'throughput_gbps': sw.get('throughput_gbps', 0.0),
        'utilization': {
            'rx': rx_agg.get('utilization', 0.0),
            'hash': mod.get('hash_engine', {}).get('utilization', 0.0),
            'scheduler': mod.get('scheduler', {}).get('utilization', 0.0),
        },
        'line_rate_achieved_ratio': achieved / max(1, achieved + missed),
    }


def _fmt_config_tag(cfg):
    return f"{cfg['scheduler']}/{cfg['buffer']}/{cfg['hash']}"


def _print_row(label, result):
    cfg = result['configuration']
    lat = result['latency']
    tag = _fmt_config_tag(cfg)
    print(f"  {label:10s}  {tag}  Bus={cfg['bus_width']}b")
    print(f"             SchedLat={cfg['scheduler_latency_cycles']}cyc  II={cfg['scheduler_ii_cycles']}cyc  "
          f"Latency={lat['avg_ns']:.2f}ns")


def print_comparison(user_result, baseline_result):
    u_lat = user_result['latency']['avg_ns']
    b_lat = baseline_result['latency']['avg_ns']

    if b_lat > 0:
        improvement = (b_lat - u_lat) / b_lat * 100.0
    else:
        improvement = 0.0

    print(f"\n{'='*72}")
    print(f"  Result")
    _print_row("User", user_result)
    _print_row("Baseline", baseline_result)
    print(f"  Avg Latency Custom: {u_lat:.2f} ns   "
          f"Baseline: {b_lat:.2f} ns")
    print(f"{'='*72}")


def main():
    parser = argparse.ArgumentParser(
        description="Compare user config against baseline "
                    "(NBuffersPerPort + iSLIP + MultiBankHash)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""\
Baseline is always: NBuffersPerPort + iSLIP + MultiBankHash
with the same ports, voq-size, bus-width, and clock as the user config.

Available choices:
  --scheduler : {', '.join(SCHEDULER_CHOICES)}
  --buffer    : {', '.join(BUFFER_CHOICES)}
  --hash      : {', '.join(HASH_CHOICES)}

Examples:
  %(prog)s -t topo.csv -r trace.csv --scheduler EDRRM
  %(prog)s -t topo.csv -r trace.csv --scheduler EDRRM --hash FullLookupTable
  %(prog)s -t topo.csv -r trace.csv --scheduler RoundRobin --buffer OneBufferPerPort --json
"""
    )

    parser.add_argument('-t', '--topology', required=True,
                        help='Topology CSV file')
    parser.add_argument('-r', '--trace', required=True,
                        help='Traffic trace CSV file')
    parser.add_argument('--baseline-trace', default=None,
                        help='Separate trace for baseline (e.g. with larger headers)')
    parser.add_argument('-p', '--ports', type=int, default=8,
                        help='Number of switch ports (default: 8)')
    parser.add_argument('-m', '--max-time', type=float, default=5000000.0,
                        help='Max simulation time in ns (default: 5000000)')

    parser.add_argument('--scheduler', choices=SCHEDULER_CHOICES,
                        default='EDRRM',
                        help='Scheduler algorithm (default: EDRRM)')
    parser.add_argument('--buffer', choices=BUFFER_CHOICES,
                        default='NBuffersPerPort',
                        help='Buffer type (default: NBuffersPerPort)')
    parser.add_argument('--hash', choices=HASH_CHOICES,
                        default='FullLookupTable',
                        help='Hash/lookup module (default: FullLookupTable)')

    parser.add_argument('--voq-size', type=int, default=1048576,
                        help='Per-VOQ buffer size in bytes (default: 1048576)')
    parser.add_argument('--baseline-voq-size', type=int, default=None,
                        help='Baseline VOQ size in bytes (default: same as --voq-size)')
    parser.add_argument('--bus-width', type=int, default=512,
                        help='AXIS data bus width in bits (default: 512)')
    parser.add_argument('--baseline-bus-width', type=int, default=256,
                        help='Baseline bus width in bits (default: 256)')
    parser.add_argument('--clock', type=float, default=250.0,
                        help='Clock frequency in MHz (default: 250)')

    parser.add_argument('--json', action='store_true',
                        help='Output as JSON')

    args = parser.parse_args()

    for tag, path in [('topology', args.topology), ('trace', args.trace)]:
        if not Path(path).exists():
            print(f"Error: {tag} file not found: {path}")
            return 1

    baseline_voq = args.baseline_voq_size if args.baseline_voq_size else args.voq_size
    baseline_trace = args.baseline_trace if args.baseline_trace else args.trace

    print(f"{'='*72}")
    print(f"  Topology: {args.topology}")
    print(f"  CU Trace:    {args.trace}")
    if args.baseline_trace:
        print(f"  ETH Trace: {args.baseline_trace}")
    print(f"{'='*72}")

    print(f"\n[1/2] Running user config ...")
    user_result = _run_one(
        topology=args.topology, trace=args.trace,
        max_time=args.max_time, num_ports=args.ports,
        voq_size=args.voq_size, bus_width=args.bus_width,
        clock=args.clock,
        scheduler=args.scheduler,
        buffer=args.buffer,
        hash_mod=args.hash,
        label="User",
    )

    print(f"\n[2/2] Running baseline ...")
    baseline_result = _run_one(
        topology=args.topology, trace=baseline_trace,
        max_time=args.max_time, num_ports=args.ports,
        voq_size=baseline_voq, bus_width=args.baseline_bus_width,
        clock=args.clock,
        scheduler='iSLIP',
        buffer='NBuffersPerPort',
        hash_mod='MultiBankHash',
        label="Base",
    )

    if args.json:
        u_lat = user_result['latency']['avg_ns']
        b_lat = baseline_result['latency']['avg_ns']
        improvement = (b_lat - u_lat) / b_lat * 100.0 if b_lat > 0 else 0.0
        out = {
            'user': user_result,
            'baseline': baseline_result,
            'comparison': {
                'user_avg_latency_ns': u_lat,
                'baseline_avg_latency_ns': b_lat,
                'improvement_pct': round(improvement, 4),
            },
        }
        print(json.dumps(out, indent=2))
    else:
        print_comparison(user_result, baseline_result)

    return 0


if __name__ == "__main__":
    sys.exit(main())
