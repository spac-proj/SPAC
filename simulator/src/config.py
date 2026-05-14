"""
Switch configuration management module.

This module provides configuration classes and utilities for network switch simulation.
Supports both simple configurations (global_voq_size) and detailed configurations (per-port voq_sizes).

Key Components:
- HashModuleType, BufferType, SchedulerType: Configuration enumerations
- SwitchConfig: Main configuration class with validation
- load_config, save_config: YAML configuration I/O
- LatencyEstimator: HLS-based latency estimation (from estimation.txt)
- BusBandwidthModel: Bus bandwidth calculations

Timing Models (from HLS estimation):
- RX: Latency=2, II=1
- FullLookupTable: Latency=ceil(N/2)+1, II=1  
- MultiBankHash: Latency=max(4,N+2), II=3
- iSLIP (1b1p): Latency=0.679N+6.5, II=4
- RoundRobin (nb1p): Latency=0.679N+3.5, II=1

Buffer Types:
- OneBufferPerPort (1b1p): One shared queue per output port
  - Total: N queues
  - Configuration: global_voq_size (single size) or voq_sizes[N] (per-port sizes)
  
- NBuffersPerPort (nb1p/VOQ): One queue per (src, dst) pair
  - Total: N×N queues (src==dst queues are unused)
  - Configuration: global_voq_size (single size) or voq_sizes[N*N] (per-pair sizes)
  - Index mapping: voq_sizes[src*N + dst] for queue from src to dst
"""

import yaml
from enum import Enum
from typing import Dict, Optional, List, Union
from dataclasses import dataclass, field


class HashModuleType(Enum):
    """Hash module type enumeration."""
    MultiBankHash = "MultiBankHash"
    FullLookupTable = "FullLookupTable"


class BufferType(Enum):
    """Buffer organization type enumeration."""
    OneBufferPerPort = "OneBufferPerPort"
    NBuffersPerPort = "NBuffersPerPort"


class SchedulerType(Enum):
    """Packet scheduler type enumeration."""
    RoundRobin = "RoundRobin"
    iSLIP = "iSLIP"
    EDRRM = "EDRRM"


@dataclass
class SwitchConfig:
    """
    Network switch configuration parameters.
    
    Supports HLS-based timing constraints with configurable:
    - Hash module: FullLookupTable or MultiBankHash
    - Buffer organization: OneBufferPerPort or NBuffersPerPort
    - Scheduler: RoundRobin or iSLIP
    
    Buffer configuration supports two modes:
    - OneBufferPerPort: 
      - global_voq_size: single shared buffer size for all output ports
      - voq_sizes: list of N sizes, voq_sizes[i] = buffer size for output port i
      
    - NBuffersPerPort: (src,dst) pair based queues
      - global_voq_size: single size per (src,dst) queue
      - voq_sizes: list of N*N sizes, voq_sizes[s*N+d] = buffer size from src s to dst d
      - Note: queues where src==dst are unused (zero size)
    """
    

    num_ports: int = 8
    addr_length: int = 4
    hash_bits: int = 7
    axis_data_width: int = 512
    

    hash_module_type: HashModuleType = HashModuleType.FullLookupTable
    buffer_type: BufferType = BufferType.OneBufferPerPort
    scheduler_type: SchedulerType = SchedulerType.iSLIP
    

    max_queue_depth_log: int = 3
    max_queue_depth: int = 8
    



    global_voq_size: int = 4096
    




    voq_sizes: Optional[List[int]] = None
    

    shared_memory_size: int = -1
    

    clock_frequency_mhz: float = 200.0
    simulation_time_ns: float = 1000000.0
    

    max_retries: int = 10
    backoff_base_delay_cycles: int = 10
    backoff_max_delay_cycles: int = 1000
    

    enable_statistics: bool = True
    statistics_interval_cycles: int = 1000
    
    def get_voq_size(self, src_port: int = 0, dst_port: int = 0) -> int:
        """
        Get VOQ size for a specific port or port pair.
        
        Args:
            src_port: Source port (used for NBuffersPerPort buffer type)
            dst_port: Destination port
            
        Returns:
            VOQ size in bytes
        """
        if self.voq_sizes is not None:
            if self.buffer_type == BufferType.OneBufferPerPort:
                # OneBufferPerPort: index by destination port only
                if dst_port < len(self.voq_sizes):
                    return self.voq_sizes[dst_port]
            else:
                # NBuffersPerPort: index by (src, dst) pair
                idx = src_port * self.num_ports + dst_port
                if idx < len(self.voq_sizes):
                    return self.voq_sizes[idx]
        
        return self.global_voq_size
    
    def get_total_buffer_size(self) -> int:
        """
        Calculate total buffer memory required.
        
        Returns:
            Total buffer size in bytes
        """
        if self.voq_sizes is not None:
            return sum(self.voq_sizes)
        
        if self.buffer_type == BufferType.OneBufferPerPort:
            # OneBufferPerPort: N queues
            return self.global_voq_size * self.num_ports
        else:
            # NBuffersPerPort: N×(N-1) queues (excluding src==dst)
            return self.global_voq_size * self.num_ports * (self.num_ports - 1)
    
    def validate_voq_sizes(self) -> bool:
        """
        Validate VOQ sizes configuration.
        
        Returns:
            True: Configuration is valid
            False: Configuration is invalid (size mismatch or negative sizes)
        """
        if self.voq_sizes is None:
            return True
        
        expected_length = self.num_ports if self.buffer_type == BufferType.OneBufferPerPort \
                          else self.num_ports * self.num_ports
        
        if len(self.voq_sizes) != expected_length:
            return False
        
        # Check for negative sizes
        if any(size < 0 for size in self.voq_sizes):
            return False
        
        return True


def load_config(config_path: str) -> SwitchConfig:
    """
    Load switch configuration from YAML file.
    
    Args:
        config_path: Path to configuration YAML file
        
    Returns:
        SwitchConfig object
    """
    with open(config_path, 'r') as f:
        config_dict = yaml.safe_load(f)
    
    # Convert string enum values to enum instances
    enum_mappings = {
        'hash_module_type': HashModuleType,
        'buffer_type': BufferType,
        'scheduler_type': SchedulerType
    }
    for key, enum_class in enum_mappings.items():
        if key in config_dict:
            config_dict[key] = enum_class(config_dict[key])
    
    # Convert max_queue_depth_log to max_queue_depth
    if 'max_queue_depth_log' in config_dict:
        config_dict['max_queue_depth'] = 1 << config_dict['max_queue_depth_log']
    
    # Handle voq_sizes configuration (list or dict)
    if 'voq_sizes' in config_dict:
        voq_sizes_raw = config_dict['voq_sizes']
        if isinstance(voq_sizes_raw, list):
            config_dict['voq_sizes'] = voq_sizes_raw
        elif isinstance(voq_sizes_raw, dict):
            # Expand dict to list with default values
            num_ports = config_dict.get('num_ports', 8)
            buffer_type = config_dict.get('buffer_type', BufferType.OneBufferPerPort)
            
            if buffer_type == BufferType.OneBufferPerPort:
                expected_len = num_ports
            else:
                expected_len = num_ports * num_ports
            
            # Initialize with global size, then override specified indices
            default_size = config_dict.get('global_voq_size', 4096)
            voq_sizes_list = [default_size] * expected_len
            
            for key, value in voq_sizes_raw.items():
                idx = int(key)
                if 0 <= idx < expected_len:
                    voq_sizes_list[idx] = value
            
            config_dict['voq_sizes'] = voq_sizes_list
    
    # Handle shared_memory_size (legacy)
    if 'shared_memory_size' in config_dict and config_dict['shared_memory_size'] > 0:
        # If global_voq_size not set, calculate from shared memory
        if 'global_voq_size' not in config_dict or config_dict.get('global_voq_size', 0) <= 0:
            buffer_type = config_dict.get('buffer_type', BufferType.OneBufferPerPort)
            num_ports = config_dict.get('num_ports', 8)
            
            if buffer_type == BufferType.OneBufferPerPort:
                # Shared memory = sum of all per-port buffers
                config_dict['global_voq_size'] = config_dict['shared_memory_size']
            else:
                # Shared memory = sum of all (src,dst) buffers
                config_dict['global_voq_size'] = config_dict['shared_memory_size'] // (num_ports * num_ports)
    
    return SwitchConfig(**config_dict)


def create_default_config() -> SwitchConfig:
    """Create a default switch configuration."""
    return SwitchConfig()


def save_config(config: SwitchConfig, config_path: str):
    """
    Save switch configuration to YAML file.
    
    Args:
        config: SwitchConfig object to save
        config_path: Output YAML file path
    """
    config_dict = {
        'num_ports': config.num_ports,
        'addr_length': config.addr_length,
        'hash_bits': config.hash_bits,
        'axis_data_width': config.axis_data_width,
        'hash_module_type': config.hash_module_type.value,
        'buffer_type': config.buffer_type.value,
        'scheduler_type': config.scheduler_type.value,
        'max_queue_depth_log': config.max_queue_depth_log,
        'max_queue_depth': config.max_queue_depth,
        'clock_frequency_mhz': config.clock_frequency_mhz,
        'simulation_time_ns': config.simulation_time_ns,
        'global_voq_size': config.global_voq_size,
        'max_retries': config.max_retries,
        'backoff_base_delay_cycles': config.backoff_base_delay_cycles,
        'backoff_max_delay_cycles': config.backoff_max_delay_cycles,
        'enable_statistics': config.enable_statistics,
        'statistics_interval_cycles': config.statistics_interval_cycles
    }
    
    if config.voq_sizes:
        config_dict['voq_sizes'] = config.voq_sizes
    
    with open(config_path, 'w') as f:
        yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False)


class LatencyEstimator:
    """
    Latency and initiation interval (II) estimation based on HLS implementation.
    
    Provides timing models derived from estimation.txt HLS synthesis estimates.
    Enables accurate cycle-accurate simulation of pipeline constraints.
    """
    
    @staticmethod
    def estimate_rx_latency(num_ports: int) -> int:
        """
        RX engine latency (fixed).
        
        From estimation.txt: Latency = 2 cycles
        """
        return 2
    
    @staticmethod
    def estimate_rx_ii(num_ports: int) -> int:
        """
        RX engine initiation interval (can accept new packet every cycle).
        
        From estimation.txt: II = 1 cycle
        """
        return 1
    
    @staticmethod
    def estimate_hash_latency(hash_type: HashModuleType, num_ports: int, hash_bits: int = 7) -> int:
        """
        Hash module latency depends on type.
        
        From estimation.txt:
        - FullLookupTable: BRAM direct lookup, nearly constant (2-6 cycles)
        - MultiBankHash: hash compute + bank access, slow growth (4-12 cycles)
        """
        # Part synthesis latency tables for supported port counts
        fl_table = {2:2, 4:3, 8:5, 10:4, 12:4, 14:4, 16:5, 24:5, 32:6}
        mb_table = {2:4, 4:4, 8:6, 10:6, 12:6, 14:7, 16:7, 24:9, 32:12}

        if hash_type == HashModuleType.FullLookupTable:
            if num_ports in fl_table:
                return fl_table[num_ports]
            return (num_ports + 1) // 2 + 1  # fallback
        else:
            if num_ports in mb_table:
                return mb_table[num_ports]
            return max(4, num_ports + 2)  # fallback
    
    @staticmethod
    def estimate_hash_ii(hash_type: HashModuleType) -> int:
        """
        Hash module initiation interval.
        
        From estimation.txt:
        - FullLookupTable: II = 1 cycle
        - MultiBankHash: II = 3 cycles
        """
        return 1 if hash_type == HashModuleType.FullLookupTable else 3
    
    @staticmethod
    def estimate_scheduler_latency(scheduler_type: SchedulerType, buffer_type: BufferType,
                                   num_ports: int, queue_depth_log: int = 3) -> int:
        """
        Scheduler latency depends on type.
        
        From estimation.txt:
        - iSLIP: parallel arbiter tree, log-depth per iteration (6-15 cycles)
        - RoundRobin: simple priority mux tree (2-6 cycles)
        - EDRRM: single-iteration dual RR with queue-depth check (5-13 cycles)
        """
        import math
        # Part synthesis latency tables for supported port counts
        islip_table =   {2:6, 4:7, 8:9, 10:9, 12:9, 14:10, 16:10, 24:12, 32:15}
        rr_table =      {2:2, 4:3, 8:4, 10:5, 12:5, 14:5, 16:5, 24:6, 32:6}
        edrrm_table =   {2:4, 4:5, 8:7, 10:8, 12:8, 14:9, 16:9, 24:11, 32:13}

        if scheduler_type == SchedulerType.iSLIP:
            if num_ports in islip_table:
                return islip_table[num_ports]
            return int(0.679 * num_ports + 6.5)  # fallback
        elif scheduler_type == SchedulerType.EDRRM:
            if num_ports in edrrm_table:
                return edrrm_table[num_ports]
            return int(0.679 * num_ports + 5.0)  # fallback
        else:
            if num_ports in rr_table:
                return rr_table[num_ports]
            return max(2, math.ceil(math.log2(max(2, num_ports))) + 1)  # fallback
    
    @staticmethod
    def estimate_scheduler_ii(scheduler_type: SchedulerType) -> int:
        """
        Scheduler initiation interval.
        
        From estimation.txt:
        - iSLIP: II = 4 cycles (parallel processing of 4 iterations)
        - RoundRobin: II = 1 cycle (simple sequential)
        - EDRRM: II = 2 cycles (single iteration + queue depth read)
        """
        if scheduler_type == SchedulerType.iSLIP:
            return 4
        elif scheduler_type == SchedulerType.EDRRM:
            return 2
        else:
            return 1


class BusBandwidthModel:
    """
    Data bus bandwidth and transfer time calculations.
    
    Models packet transfer over fixed-width data bus.
    Accounts for packet size and bus width to calculate transfer cycles.
    """
    
    @staticmethod
    def calculate_transfer_cycles(packet_size_bytes: int, bus_width_bits: int) -> int:
        """
        Calculate cycles needed to transfer packet over bus.
        
        Args:
            packet_size_bytes: Packet size in bytes (includes header and body)
            bus_width_bits: Data bus width in bits (default 512)
            
        Returns:
            Transfer cycles (minimum 1)
            
        Formula:
            cycles = ceil(packet_size_bytes * 8 / bus_width_bits)
        """
        import math
        packet_size_bits = packet_size_bytes * 8
        return max(1, math.ceil(packet_size_bits / bus_width_bits))
    
    @staticmethod
    def calculate_bus_bandwidth_gbps(bus_width_bits: int, clock_freq_mhz: float) -> float:
        """
        Calculate bus bandwidth in Gbps.
        
        Args:
            bus_width_bits: Bus width in bits
            clock_freq_mhz: Clock frequency in MHz
            
        Returns:
            Bandwidth in Gbps
        """
        return (bus_width_bits * clock_freq_mhz) / 1000.0
    
    @staticmethod
    def can_achieve_line_rate(packet_transfer_cycles: int, decision_latency_cycles: int,
                              decision_ii: int) -> bool:
        """
        Check if design can achieve line rate.
        
        Line rate is achievable when scheduling decision completes before
        or at the same time as packet transfer, accounting for II constraints.
        
        Args:
            packet_transfer_cycles: Cycles to transfer one packet
            decision_latency_cycles: Latency of scheduling decision
            decision_ii: Initiation interval of scheduler
            
        Returns:
            True: Can achieve line rate
            False: Cannot sustain line rate
            
        Note:
            - If decision_ii <= packet_transfer_cycles, line rate is achievable
            - Scheduling latency less critical when II amortized over transfer time
        """
        # Line rate achievable when scheduler II fits within transfer time
        return decision_ii <= packet_transfer_cycles
