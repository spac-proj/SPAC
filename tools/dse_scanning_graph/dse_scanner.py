#!/usr/bin/env python3


import sys
import csv
import math
import argparse
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional, Tuple, Union
from itertools import product
from copy import deepcopy

try:
    from tqdm import tqdm
except ImportError:
    class tqdm:
        def __init__(self, iterable=None, desc=None, unit=None, **kwargs):
            self.iterable = iterable
            self.desc = desc
            self.total = len(iterable) if iterable else 0
            self.n = 0
        
        def __iter__(self):
            for item in self.iterable:
                yield item
                self.n += 1
                if self.n % 10 == 0 or self.n == self.total:
                    print(f"\r{self.desc}: {self.n}/{self.total}", end="", flush=True)
        
        @staticmethod
        def write(msg):
            print(msg)

src_dir = Path(__file__).parent.parent.parent / "simulator" / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from config import (
    SwitchConfig, HashModuleType, BufferType, SchedulerType,
    LatencyEstimator
)
from simulation import NetworkSimulator


@dataclass
class ResourcePrediction:
    hash_lut: int = 0
    hash_ff: int = 0
    hash_bram: int = 0
    
    rx_lut: int = 0
    rx_ff: int = 0
    rx_bram: int = 0
    
    sched_lut: int = 0
    sched_ff: int = 0
    sched_bram: int = 0
    
    buffer_bram: int = 0
    
    total_lut: int = 0
    total_ff: int = 0
    total_bram: int = 0
    
    buffer_memory_bytes: int = 0


@dataclass
class SimulationResult:
    hash_module_type: str
    buffer_type: str
    scheduler_type: str
    num_ports: int
    global_voq_size: int
    axis_data_width: int
    clock_frequency_mhz: float
    queue_depth_log: int
    
    hash_lut: int
    hash_ff: int
    hash_bram: int
    rx_lut: int
    rx_ff: int
    rx_bram: int
    sched_lut: int
    sched_ff: int
    sched_bram: int
    buffer_bram: int 
    total_lut: int
    total_ff: int
    total_bram: int
    buffer_memory_bytes: int
    
    packets_received: int
    packets_transmitted: int
    packets_dropped: int
    total_cycles: int
    avg_latency_ns: float
    max_latency_ns: float
    throughput_gbps: float
    voq_overflow: bool
    drop_rate: float
    
    rx_utilization: float
    hash_utilization: float
    scheduler_utilization: float
    
    line_rate_achieved_ratio: float
    
    phase: int = 1
    
    voq_sizes_str: str = ""
    
    original_total_memory: int = 0      
    optimized_total_memory: int = 0     
    bram_saving_pct: float = 0.0        
    performance_degradation_pct: float = 0.0 
    
    peak_voq_sizes_str: str = ""


class ResourceEstimator:
    
    BRAM_18K_BITS = 18 * 1024  # BRAM 18Kb = 18432 bits
    BASE_BUS_WIDTH = 512 
    
    @staticmethod
    def _apply_bus_width_scaling(value: int, axis_data_width: int, 
                                 is_bram: bool = False) -> int:
        if is_bram:
            return value 
        
        ratio = axis_data_width / ResourceEstimator.BASE_BUS_WIDTH
        
        if ratio > 1:
            return int(value * ratio * 0.6)
        elif ratio < 1:
            return int(value * ratio * 1.2)
        else:
            return value
    
    @staticmethod
    def estimate_hash_resources(hash_type: HashModuleType, num_ports: int, 
                                hash_bits: int = 7,
                                axis_data_width: int = 512) -> Tuple[int, int, int]:
        n = num_ports
        
        if hash_type == HashModuleType.FullLookupTable:
            lut_base = int(16 * n**2 + 658 * n + 129)
            ff_base = int(91 * n**2 - 200 * n + 300)
            bram = 0
        else:
            lut_base = int(716.5 * n**2 - 900 * n + 1296)
            ff_base = int(198.667 * n**2 - 412.5 * n + 689.333)
            bram = 0 if hash_bits <= 8 else n
        
        lut = ResourceEstimator._apply_bus_width_scaling(lut_base, axis_data_width)
        ff = ResourceEstimator._apply_bus_width_scaling(ff_base, axis_data_width)
        
        return max(0, lut), max(0, ff), max(0, bram)
    
    @staticmethod
    def estimate_rx_resources(num_ports: int,
                              axis_data_width: int = 512) -> Tuple[int, int, int]:
        n = num_ports
        lut_base = int(39 + 51 * n)
        ff_base = int(7 + 557 * n)
        bram = int(8 * n)
        
        lut = ResourceEstimator._apply_bus_width_scaling(lut_base, axis_data_width)
        ff = ResourceEstimator._apply_bus_width_scaling(ff_base, axis_data_width)
        
        return lut, ff, bram
    
    @staticmethod
    def estimate_scheduler_resources(scheduler_type: SchedulerType, 
                                     buffer_type: BufferType,
                                     num_ports: int,
                                     queue_depth_log: int = 3,
                                     axis_data_width: int = 512) -> Tuple[int, int, int]:
        n = num_ports
        
        if scheduler_type == SchedulerType.iSLIP:
            if buffer_type == BufferType.OneBufferPerPort:
                lut_base = int(943.75 * n**2 - 655.5 * n + 137)
                ff_base = int(564.833 * n**2 + 3055.5 * n - 5021.333)
                bram = int(21.286 * n - 20)
            else:
                lut_base = int(744.583 * n**2 - 1000 * n + 1512.667)
                ff_base = int(1023.167 * n**2 - 2398 * n + 5978.333)
                bram = int(92.571 * n - 180)
        elif scheduler_type == SchedulerType.EDRRM:
            # EDRRM: single-iteration dual RR with queue-depth read.
            # Similar structure to iSLIP nb1p but fewer iterations -> ~75% LUT/FF.
            lut_base = int(0.75 * (744.583 * n**2 - 1000 * n + 1512.667))
            ff_base = int(0.75 * (1023.167 * n**2 - 2398 * n + 5978.333))
            bram = int(92.571 * n - 180)
        else:
            lut_base = int(744.583 * n**2 - 1000 * n + 1512.667)
            ff_base = int(1023.167 * n**2 - 2398 * n + 5978.333)
            bram = int(92.571 * n - 180)
        
        lut = ResourceEstimator._apply_bus_width_scaling(lut_base, axis_data_width)
        ff = ResourceEstimator._apply_bus_width_scaling(ff_base, axis_data_width)
        bram = ResourceEstimator._apply_bus_width_scaling(bram, axis_data_width)
        
        return max(0, lut), max(0, ff), max(0, bram)
    
    @staticmethod
    def estimate_buffer_bram(buffer_type: BufferType, num_ports: int,
                             global_voq_size: int,
                             axis_data_width: int = 512,
                             voq_sizes: List[int] = None) -> int:
        if voq_sizes:
            total_bytes = sum(s for s in voq_sizes if s > 0)
        elif buffer_type == BufferType.OneBufferPerPort:
            total_bytes = global_voq_size * num_ports
        else:
            total_bytes = global_voq_size * num_ports * (num_ports - 1)
        
        if total_bytes <= 0:
            return 0
        
        BRAM_18K_CAPACITY_BYTES = 2048
        
        brams_parallel = math.ceil(axis_data_width / 36)
        
        depth_per_group = 512  # entries
        bytes_per_entry = axis_data_width // 8
        capacity_per_group = depth_per_group * bytes_per_entry
        
        groups_needed = math.ceil(total_bytes / capacity_per_group)
        
        total_brams = brams_parallel * groups_needed
        
        return total_brams

    @staticmethod
    def estimate_buffer_memory(buffer_type: BufferType, num_ports: int,
                               global_voq_size: int,
                               voq_sizes: List[int] = None) -> int:
        if voq_sizes:
            return sum(voq_sizes)
        
        if buffer_type == BufferType.OneBufferPerPort:
            return global_voq_size * num_ports
        else:
            return global_voq_size * num_ports * (num_ports - 1)
    
    @classmethod
    def estimate_total_resources(cls, config: SwitchConfig, 
                                 voq_sizes: List[int] = None) -> ResourcePrediction:
        pred = ResourcePrediction()
        
        axis_width = config.axis_data_width
        
        # Hash
        pred.hash_lut, pred.hash_ff, pred.hash_bram = cls.estimate_hash_resources(
            config.hash_module_type, config.num_ports, config.hash_bits, axis_width
        )
        
        # RX
        pred.rx_lut, pred.rx_ff, pred.rx_bram = cls.estimate_rx_resources(
            config.num_ports, axis_width
        )
        
        # Scheduler
        pred.sched_lut, pred.sched_ff, pred.sched_bram = cls.estimate_scheduler_resources(
            config.scheduler_type, config.buffer_type,
            config.num_ports, config.max_queue_depth_log, axis_width
        )
        
        # Buffer BRAM
        pred.buffer_bram = cls.estimate_buffer_bram(
            config.buffer_type, config.num_ports,
            config.global_voq_size, config.axis_data_width, voq_sizes
        )
        
        # Buffer memory
        pred.buffer_memory_bytes = cls.estimate_buffer_memory(
            config.buffer_type, config.num_ports,
            config.global_voq_size, voq_sizes
        )
        
        # Total
        pred.total_lut = pred.hash_lut + pred.rx_lut + pred.sched_lut
        pred.total_ff = pred.hash_ff + pred.rx_ff + pred.sched_ff
        pred.total_bram = pred.hash_bram + pred.rx_bram + pred.buffer_bram
        
        return pred


def calculate_queue_depth_log(global_voq_size: int, axis_data_width: int) -> int:
    queue_depth = global_voq_size
    if queue_depth <= 1:
        return 0
    return max(1, math.ceil(math.log2(queue_depth)))


def next_power_of_2(x: int, minimum: int = 64) -> int:
    if x <= minimum:
        return minimum
    return 1 << (x - 1).bit_length()


def run_single_simulation(config: SwitchConfig, topology_file: str, 
                          trace_file: str, max_time_ns: float) -> Dict[str, Any]:
    sim = NetworkSimulator(config)
    sim.load_topology(topology_file)
    sim.schedule_packet_injection(trace_file)
    stats = sim.run_simulation(max_time_ns=max_time_ns)
    
    switch_id = list(stats['switches'].keys())[0]
    sw_stats = stats['switches'][switch_id]
    
    buffer_stats = sw_stats.get('buffer', {})
    total_dropped_overflow = buffer_stats.get('total_dropped_overflow', 0)
    voq_overflow = total_dropped_overflow > 0
    
    module_activity = sw_stats.get('module_activity', {})
    
    rx_util = 0.0
    if 'rx_engine' in module_activity:
        rx_agg = module_activity['rx_engine'].get('aggregate', {})
        rx_util = rx_agg.get('utilization', 0.0)
    
    hash_util = module_activity.get('hash_engine', {}).get('utilization', 0.0)
    sched_util = module_activity.get('scheduler', {}).get('utilization', 0.0)
    
    line_rate_stats = sw_stats.get('line_rate_stats', {})
    achieved = line_rate_stats.get('achieved_cycles', 0)
    missed = line_rate_stats.get('missed_cycles', 0)
    line_rate_ratio = achieved / max(1, achieved + missed)
    
    peak_voq_sizes = buffer_stats.get('peak_voq_sizes', {})
    peak_voq_sizes_flat = buffer_stats.get('peak_voq_sizes_flat', [])
    
    return {
        'packets_received': sw_stats.get('packets_received', 0),
        'packets_transmitted': sw_stats.get('packets_transmitted', 0),
        'packets_dropped': sw_stats.get('packets_dropped', 0),
        'total_cycles': sw_stats.get('current_cycle', 0),
        'avg_latency_ns': sw_stats.get('average_latency_ns', 0.0),
        'max_latency_ns': 0.0, 
        'throughput_gbps': sw_stats.get('throughput_gbps', 0.0),
        'voq_overflow': voq_overflow,
        'drop_rate': sw_stats.get('drop_rate', 0.0),
        'rx_utilization': rx_util,
        'hash_utilization': hash_util,
        'scheduler_utilization': sched_util,
        'line_rate_achieved_ratio': line_rate_ratio,
        'peak_voq_sizes': peak_voq_sizes,
        'peak_voq_sizes_flat': peak_voq_sizes_flat,
        'buffer_stats': buffer_stats,
    }


def generate_phase1_configurations(num_ports: int, 
                                   large_voq_size: int = 1048576) -> List[SwitchConfig]:
    configs = []
    
    hash_types = [HashModuleType.FullLookupTable, HashModuleType.MultiBankHash]
    buffer_types = [BufferType.OneBufferPerPort, BufferType.NBuffersPerPort]
    scheduler_types = [SchedulerType.RoundRobin, SchedulerType.iSLIP, SchedulerType.EDRRM]
    data_widths = [32, 64, 128, 256, 512, 640]
    clock_freq = 250.0 
    
    for hash_type, buffer_type, sched_type, width in product(
        hash_types, buffer_types, scheduler_types, data_widths
    ):
        queue_depth_log = calculate_queue_depth_log(large_voq_size, width)
        
        config = SwitchConfig(
            num_ports=num_ports,
            hash_module_type=hash_type,
            buffer_type=buffer_type,
            scheduler_type=sched_type,
            global_voq_size=large_voq_size,
            voq_sizes=None,
            axis_data_width=width,
            clock_frequency_mhz=clock_freq,
            max_queue_depth_log=queue_depth_log,
            max_queue_depth=2**queue_depth_log,
        )
        configs.append(config)
    
    return configs


def compute_optimized_voq_sizes(peak_sizes: Union[Dict, List], 
                                buffer_type: BufferType, 
                                num_ports: int,
                                min_voq_size: int = 64) -> List[int]:
    if buffer_type == BufferType.OneBufferPerPort:
        if isinstance(peak_sizes, dict):
            voq_sizes = []
            for dst in range(num_ports):
                peak = peak_sizes.get(dst, 0)
                size = next_power_of_2(peak, min_voq_size) if peak > 0 else min_voq_size
                voq_sizes.append(size)
        else:
            voq_sizes = [next_power_of_2(p, min_voq_size) if p > 0 else min_voq_size 
                        for p in peak_sizes[:num_ports]]
        return voq_sizes
    else:
        if isinstance(peak_sizes, dict):
            voq_sizes = []
            for src in range(num_ports):
                for dst in range(num_ports):
                    if src == dst:
                        voq_sizes.append(0) 
                    else:
                        peak = peak_sizes.get((src, dst), 0)
                        size = next_power_of_2(peak, min_voq_size) if peak > 0 else min_voq_size
                        voq_sizes.append(size)
        else:
            voq_sizes = []
            for i, p in enumerate(peak_sizes):
                src = i // num_ports
                dst = i % num_ports
                if src == dst:
                    voq_sizes.append(0)
                else:
                    size = next_power_of_2(p, min_voq_size) if p > 0 else min_voq_size
                    voq_sizes.append(size)
        return voq_sizes


def run_phase2_optimization(best_config: SwitchConfig,
                            phase1_result: SimulationResult,
                            peak_voq_sizes: Union[Dict, List],
                            topology_file: str,
                            trace_file: str,
                            max_time_ns: float,
                            min_voq_size: int = 64,
                            max_drop_rate: float = 0.01) -> List[SimulationResult]:
    results = []
    num_ports = best_config.num_ports
    buffer_type = best_config.buffer_type
    
    print(f"\n{'='*60}")
    print(f"Phase 2: Buffer Optimization")
    print(f"Config: {best_config.hash_module_type.value}/{best_config.buffer_type.value}/"
          f"{best_config.scheduler_type.value} Width={best_config.axis_data_width}")
    print()
    
    optimized_voq_sizes = compute_optimized_voq_sizes(
        peak_voq_sizes, buffer_type, num_ports, min_voq_size
    )
    
    if buffer_type == BufferType.OneBufferPerPort:
        for dst in range(num_ports):
            peak = peak_voq_sizes.get(dst, 0) if isinstance(peak_voq_sizes, dict) else peak_voq_sizes[dst]
            opt = optimized_voq_sizes[dst]
            print(f"  dst_{dst}: peak={peak}B -> opt={opt}B")
    else:
        for src in range(num_ports):
            for dst in range(num_ports):
                if src != dst:
                    idx = src * num_ports + dst
                    if isinstance(peak_voq_sizes, dict):
                        peak = peak_voq_sizes.get((src, dst), 0)
                    else:
                        peak = peak_voq_sizes[idx]
                    opt = optimized_voq_sizes[idx]
                    if peak > 0 or opt > min_voq_size:
                        print(f"  {src}->{dst}: peak={peak}B -> opt={opt}B")
    
    original_memory = phase1_result.buffer_memory_bytes
    optimized_memory = sum(optimized_voq_sizes)
    saving_pct = (original_memory - optimized_memory) / max(1, original_memory) * 100
    
    
    opt_config = SwitchConfig(
        num_ports=num_ports,
        hash_module_type=best_config.hash_module_type,
        buffer_type=buffer_type,
        scheduler_type=best_config.scheduler_type,
        global_voq_size=min_voq_size, 
        voq_sizes=optimized_voq_sizes,
        axis_data_width=best_config.axis_data_width,
        clock_frequency_mhz=best_config.clock_frequency_mhz,
        max_queue_depth_log=best_config.max_queue_depth_log,
        max_queue_depth=best_config.max_queue_depth,
    )
    
    
    max_iterations = 5
    current_voq_sizes = optimized_voq_sizes.copy()
    
    for iteration in range(max_iterations):
        opt_config.voq_sizes = current_voq_sizes
        
        sim_result = run_single_simulation(opt_config, topology_file, trace_file, max_time_ns)
        
        resources = ResourceEstimator.estimate_total_resources(opt_config, current_voq_sizes)
        
        current_memory = sum(current_voq_sizes)
        current_saving = (original_memory - current_memory) / max(1, original_memory) * 100
        
        perf_change = 0.0
        if phase1_result.avg_latency_ns > 0:
            perf_change = (sim_result['avg_latency_ns'] - phase1_result.avg_latency_ns) / phase1_result.avg_latency_ns * 100
        
        drop_rate = sim_result['drop_rate']
        drops = sim_result['packets_dropped']
        
        print(f"  Iteration {iteration + 1}: Dropped packets = {drops} ({drop_rate*100:.2f}%), "
              f"Latency change = {perf_change:+.1f}%")
        
        result = SimulationResult(
            hash_module_type=opt_config.hash_module_type.value,
            buffer_type=opt_config.buffer_type.value,
            scheduler_type=opt_config.scheduler_type.value,
            num_ports=num_ports,
            global_voq_size=min_voq_size,
            axis_data_width=opt_config.axis_data_width,
            clock_frequency_mhz=opt_config.clock_frequency_mhz,
            queue_depth_log=opt_config.max_queue_depth_log,
            
            hash_lut=resources.hash_lut,
            hash_ff=resources.hash_ff,
            hash_bram=resources.hash_bram,
            rx_lut=resources.rx_lut,
            rx_ff=resources.rx_ff,
            rx_bram=resources.rx_bram,
            sched_lut=resources.sched_lut,
            sched_ff=resources.sched_ff,
            sched_bram=resources.sched_bram,
            buffer_bram=resources.buffer_bram,
            total_lut=resources.total_lut,
            total_ff=resources.total_ff,
            total_bram=resources.total_bram,
            buffer_memory_bytes=current_memory,
            
            packets_received=sim_result['packets_received'],
            packets_transmitted=sim_result['packets_transmitted'],
            packets_dropped=sim_result['packets_dropped'],
            total_cycles=sim_result['total_cycles'],
            avg_latency_ns=sim_result['avg_latency_ns'],
            max_latency_ns=sim_result['max_latency_ns'],
            throughput_gbps=sim_result['throughput_gbps'],
            voq_overflow=sim_result['voq_overflow'],
            drop_rate=drop_rate,
            
            rx_utilization=sim_result['rx_utilization'],
            hash_utilization=sim_result['hash_utilization'],
            scheduler_utilization=sim_result['scheduler_utilization'],
            line_rate_achieved_ratio=sim_result['line_rate_achieved_ratio'],
            
            phase=2,
            voq_sizes_str=",".join(map(str, current_voq_sizes)),
            original_total_memory=original_memory,
            optimized_total_memory=current_memory,
            bram_saving_pct=current_saving,
            performance_degradation_pct=perf_change,
            peak_voq_sizes_str="",
        )
        results.append(result)
        
        if drop_rate <= max_drop_rate:
            print(f"\n✓ Success! Drop rate {drop_rate*100:.2f}% <= {max_drop_rate*100:.1f}%")
            break
        


        new_peaks = sim_result.get('peak_voq_sizes', {})
        new_peaks_flat = sim_result.get('peak_voq_sizes_flat', [])
        
        if new_peaks or new_peaks_flat:

            if buffer_type == BufferType.OneBufferPerPort:
                for dst in range(num_ports):
                    peak = new_peaks.get(dst, 0) if new_peaks else (new_peaks_flat[dst] if dst < len(new_peaks_flat) else 0)
                    if peak > current_voq_sizes[dst]:
                        current_voq_sizes[dst] = next_power_of_2(peak, min_voq_size)
            else:
                for src in range(num_ports):
                    for dst in range(num_ports):
                        if src != dst:
                            idx = src * num_ports + dst
                            if new_peaks:
                                peak = new_peaks.get((src, dst), 0)
                            else:
                                peak = new_peaks_flat[idx] if idx < len(new_peaks_flat) else 0
                            if peak > current_voq_sizes[idx]:
                                current_voq_sizes[idx] = next_power_of_2(peak, min_voq_size)
        else:

            for i in range(len(current_voq_sizes)):
                if current_voq_sizes[i] > 0:
                    current_voq_sizes[i] *= 2
    else:
        print(f"\nWarning: Reached maximum iterations. Current drop rate: {drop_rate*100:.2f}%")
    
    return results


def select_top_n_candidates(results: List[SimulationResult], 
                            sim_results_data: List[Dict],
                            configs: List[SwitchConfig],
                            top_n: int = 1) -> List[Tuple[SwitchConfig, SimulationResult, Union[Dict, List]]]:
    candidates = []
    for i, (result, sim_data, config) in enumerate(zip(results, sim_results_data, configs)):
        if result.packets_dropped == 0: 
            peak_voq = sim_data.get('peak_voq_sizes', {})
            if not peak_voq:
                peak_voq = sim_data.get('peak_voq_sizes_flat', [])
            candidates.append({
                'config': config,
                'result': result,
                'peak_voq': peak_voq,
                'latency': result.avg_latency_ns,
                'throughput': result.throughput_gbps,
            })
    
    if not candidates:
        return []
    
    candidates.sort(key=lambda x: (x['latency'], -x['throughput']))
    
    selected = []
    seen_arch = set()
    
    for c in candidates:
        if len(selected) >= top_n:
            break
        
        arch_key = (c['result'].hash_module_type, 
                   c['result'].buffer_type, 
                   c['result'].scheduler_type,
                   c['result'].axis_data_width)
        
        if arch_key not in seen_arch or len(selected) < top_n // 2:
            selected.append((c['config'], c['result'], c['peak_voq']))
            seen_arch.add(arch_key)
    
    for c in candidates:
        if len(selected) >= top_n:
            break
        item = (c['config'], c['result'], c['peak_voq'])
        if item not in selected:
            selected.append(item)
    
    return selected[:top_n]


def run_dse_scan(topology_file: str, trace_file: str, output_file: str,
                 max_time_ns: float = 100000.0, num_ports: int = 8,
                 enable_phase2: bool = True,
                 phase2_top_n: int = 1,
                 min_voq_size: int = 64,
                 max_drop_rate: float = 0.01,
                 large_voq_size: int = 1048576):
    
    if not Path(topology_file).exists():
        print(f"Error: Topology file not found: {topology_file}")
        return
    if not Path(trace_file).exists():
        print(f"Error: Trace file not found: {trace_file}")
        return
    
    configs = generate_phase1_configurations(num_ports, large_voq_size)
    total_configs = len(configs)
    
    print(f"="*60)
    print(f"Design Space Exploration Scanner")
    print(f"Topology: {topology_file}, Trace: {trace_file}")
    if enable_phase2:
        print(f"Phase 2 Optimization: Enabled (Top {phase2_top_n} candidates)")
    print(f"="*60)
    
    results: List[SimulationResult] = []
    sim_results_data: List[Dict] = [] 
    configs_ran: List[SwitchConfig] = [] 
    
    
    for config in tqdm(configs, desc="Phase 1", unit="config"):
        try:
            resources = ResourceEstimator.estimate_total_resources(config)
            
            sim_result = run_single_simulation(
                config, topology_file, trace_file, max_time_ns
            )
            
            peak_voq_sizes = sim_result.get('peak_voq_sizes', {})
            peak_voq_flat = sim_result.get('peak_voq_sizes_flat', [])
            
            result = SimulationResult(
                hash_module_type=config.hash_module_type.value,
                buffer_type=config.buffer_type.value,
                scheduler_type=config.scheduler_type.value,
                num_ports=config.num_ports,
                global_voq_size=config.global_voq_size,
                axis_data_width=config.axis_data_width,
                clock_frequency_mhz=config.clock_frequency_mhz,
                queue_depth_log=config.max_queue_depth_log,
                
                hash_lut=resources.hash_lut,
                hash_ff=resources.hash_ff,
                hash_bram=resources.hash_bram,
                rx_lut=resources.rx_lut,
                rx_ff=resources.rx_ff,
                rx_bram=resources.rx_bram,
                sched_lut=resources.sched_lut,
                sched_ff=resources.sched_ff,
                sched_bram=resources.sched_bram,
                buffer_bram=resources.buffer_bram,
                total_lut=resources.total_lut,
                total_ff=resources.total_ff,
                total_bram=resources.total_bram,
                buffer_memory_bytes=resources.buffer_memory_bytes,
                
                packets_received=sim_result['packets_received'],
                packets_transmitted=sim_result['packets_transmitted'],
                packets_dropped=sim_result['packets_dropped'],
                total_cycles=sim_result['total_cycles'],
                avg_latency_ns=sim_result['avg_latency_ns'],
                max_latency_ns=sim_result['max_latency_ns'],
                throughput_gbps=sim_result['throughput_gbps'],
                voq_overflow=sim_result['voq_overflow'],
                drop_rate=sim_result['drop_rate'],
                rx_utilization=sim_result['rx_utilization'],
                hash_utilization=sim_result['hash_utilization'],
                scheduler_utilization=sim_result['scheduler_utilization'],
                line_rate_achieved_ratio=sim_result['line_rate_achieved_ratio'],
                
                phase=1,
                voq_sizes_str="",
                original_total_memory=0,
                optimized_total_memory=0,
                bram_saving_pct=0.0,
                performance_degradation_pct=0.0,
                peak_voq_sizes_str=",".join(map(str, peak_voq_flat)) if peak_voq_flat else "",
            )
            results.append(result)
            sim_results_data.append(sim_result)
            configs_ran.append(config)
            
            tqdm.write(f"✓ {config.hash_module_type.value}/{config.buffer_type.value}/"
                      f"{config.scheduler_type.value} Width={config.axis_data_width} -> "
                      f"TX={sim_result['packets_transmitted']} "
                      f"Drop={sim_result['packets_dropped']} "
                      f"Lat={sim_result['avg_latency_ns']:.2f}ns")
            
        except Exception as e:
            tqdm.write(f"✗ Error running config: {e}")
            continue
    
    
    top_candidates = select_top_n_candidates(results, sim_results_data, configs_ran, phase2_top_n)
    
    if top_candidates:
        print(f"\nTop {len(top_candidates)} candidates selected:")
        for i, (cfg, res, _) in enumerate(top_candidates):
            print(f"  #{i+1}: {cfg.hash_module_type.value}/{cfg.buffer_type.value}/"
                  f"{cfg.scheduler_type.value} Width={cfg.axis_data_width} "
                  f"Latency={res.avg_latency_ns:.2f}ns Throughput={res.throughput_gbps:.2f}Gbps")
    else:
        print("No phases matched selection criteria")
    
    phase2_results = []
    
    if enable_phase2 and top_candidates:
        print(f"\nRunning Phase 2 optimization for top candidates...")
        for idx, (best_config, best_result, best_peak_voq) in enumerate(top_candidates):
            opt_results = run_phase2_optimization(
                best_config, best_result, best_peak_voq,
                topology_file, trace_file, max_time_ns,
                min_voq_size, max_drop_rate
            )
            phase2_results.extend(opt_results)
    elif enable_phase2:
        print("Phase 2 skipped: No candidates from Phase 1")
    
    all_results = results + phase2_results
    
    if all_results:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=asdict(all_results[0]).keys())
            writer.writeheader()
            for result in all_results:
                writer.writerow(asdict(result))
        
        print(f"\nResults written to: {output_path}")
        print(f"Total configurations evaluated: {len(all_results)}")
    else:
        print("No valid results to write")


def main():
    parser = argparse.ArgumentParser(
        description="Design Space Exploration (DSE) Scanner - Sweep switch configurations and optimize buffer sizes",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('-t', '--topology', required=True)
    parser.add_argument('-r', '--trace', required=True)
    parser.add_argument('-o', '--output', required=True)
    parser.add_argument('-m', '--max-time', type=float, default=100000.0)
    parser.add_argument('-p', '--ports', type=int, default=8)
    
    parser.add_argument('--no-phase2', action='store_true')
    parser.add_argument('--phase2-top-n', type=int, default=1)
    parser.add_argument('--min-voq-size', type=int, default=64)
    parser.add_argument('--max-drop-rate', type=float, default=0.01)
    parser.add_argument('--large-buffer', type=int, default=1048576)
    
    args = parser.parse_args()
    
    try:
        run_dse_scan(
            topology_file=args.topology,
            trace_file=args.trace,
            output_file=args.output,
            max_time_ns=args.max_time,
            num_ports=args.ports,
            enable_phase2=not args.no_phase2,
            phase2_top_n=args.phase2_top_n,
            min_voq_size=args.min_voq_size,
            max_drop_rate=args.max_drop_rate,
            large_voq_size=args.large_buffer
        )
        return 0
    except Exception as e:
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
