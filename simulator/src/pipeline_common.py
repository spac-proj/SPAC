"""
Common pipeline utilities for cycle-accurate simulation.

Provides timing and state models for switch pipeline.

Key Concepts:
1. II (Initiation Interval): Cycles before next input can be accepted
2. Latency: Cycles from input to output availability
3. State Machine: Track pipeline progress (idle, processing, transmitting)
4. Bandwidth: Bus width effects on transfer cycles (base=1 cycle)
"""

from dataclasses import dataclass, field
from typing import Optional, Any, List
from enum import Enum
import math


class ModuleState(Enum):
    """Pipeline module state enumeration."""
    IDLE = "idle"
    RECEIVING = "receiving"
    PROCESSING = "processing"
    TRANSMITTING = "transmitting"
    WAITING_II = "waiting_ii"
    WAITING_OUTPUT = "waiting_output"


@dataclass
class TransferState:
    """Transfer state for data movement through bus.
    
    Tracks active data transfers with timing based on bus width.
    """
    is_active: bool = False
    total_cycles: int = 0
    remaining_cycles: int = 0
    data_size_bytes: int = 0
    data: Any = None
    
    def start_transfer(self, data: Any, size_bytes: int, bus_width_bits: int):
        """Begin a data transfer on the bus.
        
        Calculates the number of cycles required based on data size and bus width.
        """
        self.is_active = True
        self.data = data
        self.data_size_bytes = size_bytes
        self.total_cycles = max(1, math.ceil(size_bytes * 8 / bus_width_bits))
        self.remaining_cycles = self.total_cycles
    
    def tick(self) -> bool:
        """Advance transfer state by one cycle.
        
        Returns:
            True: Transfer completed
            False: Transfer still in progress
        """
        if not self.is_active:
            return False
        
        self.remaining_cycles -= 1
        if self.remaining_cycles <= 0:
            self.is_active = False
            return True
        return False
    
    def reset(self):
        """Reset transfer state to initial conditions."""
        self.is_active = False
        self.total_cycles = 0
        self.remaining_cycles = 0
        self.data_size_bytes = 0
        self.data = None


@dataclass
class ModuleActivityStats:
    """Track activity statistics for pipeline stages.
    
    Records cycle counts for different operational states and provides
    utilization and efficiency metrics.
    """

    total_cycles: int = 0
    

    idle_cycles: int = 0
    receiving_cycles: int = 0
    processing_cycles: int = 0
    transmitting_cycles: int = 0
    waiting_ii_cycles: int = 0
    waiting_output_cycles: int = 0
    

    @property
    def active_cycles(self) -> int:
        """Total cycles spent in active processing."""
        return self.receiving_cycles + self.processing_cycles + self.transmitting_cycles
    
    @property 
    def busy_cycles(self) -> int:
        """Total cycles spent in non-idle states."""
        return self.active_cycles + self.waiting_ii_cycles + self.waiting_output_cycles
    
    def get_utilization(self) -> float:
        """Calculate active utilization ratio."""
        return self.active_cycles / max(1, self.total_cycles)
    
    def get_efficiency(self) -> float:
        """Calculate processing efficiency ratio."""
        return self.active_cycles / max(1, self.busy_cycles)
    
    def to_dict(self) -> dict:
        """Convert statistics to dictionary format."""
        return {
            'total_cycles': self.total_cycles,
            'idle_cycles': self.idle_cycles,
            'receiving_cycles': self.receiving_cycles,
            'processing_cycles': self.processing_cycles,
            'transmitting_cycles': self.transmitting_cycles,
            'waiting_ii_cycles': self.waiting_ii_cycles,
            'waiting_output_cycles': self.waiting_output_cycles,
            'active_cycles': self.active_cycles,
            'busy_cycles': self.busy_cycles,
            'utilization': self.get_utilization(),
            'efficiency': self.get_efficiency(),
        }
    
    def reset(self):
        """Reset all statistics counters to zero."""
        self.total_cycles = 0
        self.idle_cycles = 0
        self.receiving_cycles = 0
        self.processing_cycles = 0
        self.transmitting_cycles = 0
        self.waiting_ii_cycles = 0
        self.waiting_output_cycles = 0


@dataclass
class PipelineStageState:
    """Pipeline stage state and control tracking.
    
    Manages input/output transfers, processing state, and II constraints
    for a single pipeline stage.
    """

    latency: int = 1
    ii: int = 1                        # Initiation Interval
    bus_width_bits: int = 512
    

    ii_counter: int = 0
    

    processing_counter: int = 0
    has_processing_data: bool = False
    processing_data: Any = None
    

    next_decision_ready: bool = False
    next_decision_data: Any = None
    

    input_transfer: TransferState = field(default_factory=TransferState)
    

    output_transfer: TransferState = field(default_factory=TransferState)
    

    output_ready: bool = False
    output_data: Any = None
    

    stats: ModuleActivityStats = field(default_factory=ModuleActivityStats)
    
    def can_accept_input(self) -> bool:
        """Check if stage can accept new input.
        
        Returns True if all the following conditions are met:
        1. II counter is zero (initiation interval satisfied)
        2. Input transfer is not active
        3. Next decision is not pending
        """
        return (self.ii_counter == 0 and 
                not self.input_transfer.is_active and
                not self.next_decision_ready)
    
    def can_output(self) -> bool:
        """Check if stage has valid output ready to transmit."""
        return self.output_ready and not self.output_transfer.is_active
    
    def start_input(self, data: Any, size_bytes: int):
        """Start accepting input data and set initiation interval counter."""
        self.input_transfer.start_transfer(data, size_bytes, self.bus_width_bits)

        self.ii_counter = self.ii
    
    def start_output(self, data: Any, size_bytes: int):
        """Begin transmitting output data."""
        self.output_transfer.start_transfer(data, size_bytes, self.bus_width_bits)
        self.output_ready = False
        self.output_data = None
    
    def tick_ii(self):
        """Decrement initiation interval counter."""
        if self.ii_counter > 0:
            self.ii_counter -= 1
    
    def tick_processing(self) -> bool:
        """Advance processing state by one cycle.
        
        Returns:
            True: Processing completed
        """
        if self.has_processing_data and self.processing_counter > 0:
            self.processing_counter -= 1
            if self.processing_counter == 0:
                return True
        return False
    
    def reset(self):
        """Reset all pipeline stage state to initial values."""
        self.ii_counter = 0
        self.processing_counter = 0
        self.has_processing_data = False
        self.processing_data = None
        self.next_decision_ready = False
        self.next_decision_data = None
        self.input_transfer.reset()
        self.output_transfer.reset()
        self.output_ready = False
        self.output_data = None
        self.stats.reset()


def calculate_transfer_cycles(size_bytes: int, bus_width_bits: int) -> int:
    """Calculate number of bus cycles to transfer data.
    
    Args:
        size_bytes: Data size in bytes
        bus_width_bits: Bus width in bits
        
    Returns:
        Minimum 1 cycle, ceil(size_bytes * 8 / bus_width_bits) otherwise
    """
    return max(1, math.ceil(size_bytes * 8 / bus_width_bits))


def can_achieve_line_rate(transfer_cycles: int, module_ii: int) -> bool:
    """Check if transfer can sustain line-rate throughput.
    
    Args:
        transfer_cycles: Number of cycles for one transfer
        module_ii: Module initiation interval in cycles
        
    Returns:
        True: Transfer cycles >= II (can maintain line rate)
    """
    return transfer_cycles >= module_ii

