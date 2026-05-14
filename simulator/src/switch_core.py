"""
Switch core engine with cycle-accurate pipeline simulation.

Integrates major switch components into a unified switch model:

   Packet Input → RX Engine → Hash Engine → VOQ Buffer → Scheduler → Output Port

Key Features:
- Cycle-accurate simulation with pipeline profiling
- Configurable hash module (FullLookupTable, MultiBankHash)
- Flexible buffer organization (OneBufferPerPort, NBuffersPerPort)
- Multiple scheduler options (RoundRobin, iSLIP)

Based on estimation.txt HLS timing constraints:
- RX: Latency=2, II=1
- FullLookupTable: Latency=ceil(N/2)+1, II=1
- MultiBankHash: Latency=max(4,N+2), II=3
- iSLIP: Latency=0.679*N+6.5, II=4
- RoundRobin: Latency=0.679*N+3.5, II=1
"""

from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
import logging
import math

from config import SwitchConfig, LatencyEstimator, BusBandwidthModel
from rx_engine import RxEngineWrapper
from hash_engine import HashEngine
from buffer_voq import VOQBuffer, SharedMemoryBuffer, create_buffer
from scheduler_base import BaseScheduler, create_scheduler
from packet import Packet, Metadata, AxisWord, TraceEntry
from pipeline_common import (
    ModuleActivityStats, TransferState, PipelineStageState,
    calculate_transfer_cycles, can_achieve_line_rate, ModuleState
)

logger = logging.getLogger(__name__)


@dataclass
class ModulePipelineState:
    """
    Pipeline state for individual module.
    
    Tracks current and previous state for modules (RX, Hash, Buffer, Scheduler, Output).
    """
    name: str = ""
    latency: int = 1
    ii: int = 1                            # Initiation Interval
    bus_width_bits: int = 512
    

    ii_counter: int = 0
    

    input_busy: bool = False
    input_transfer_remaining: int = 0
    input_data: Any = None
    

    processing: bool = False
    processing_remaining: int = 0
    processing_data: Any = None
    

    output_busy: bool = False
    output_transfer_remaining: int = 0
    output_data: Any = None
    output_ready: bool = False
    output_pending: Any = None
    

    next_ready: bool = False
    next_data: Any = None
    

    stats: ModuleActivityStats = field(default_factory=ModuleActivityStats)
    
    def can_accept_input(self) -> bool:
        """Check if module can accept input data."""
        return self.ii_counter == 0 and not self.input_busy and not self.next_ready
    
    def has_output(self) -> bool:
        """Check if module has output data ready."""
        return self.output_ready or self.next_ready
    
    def tick(self) -> Tuple[bool, bool, bool]:
        """Advance module state by one cycle.
        
        Returns:
            (input_done, processing_done, output_done): Completion status for each stage.
        """
        input_done = False
        processing_done = False
        output_done = False
        

        if self.ii_counter > 0:
            self.ii_counter -= 1
        

        if self.input_busy:
            self.input_transfer_remaining -= 1
            if self.input_transfer_remaining <= 0:
                self.input_busy = False
                input_done = True
        

        if self.processing:
            self.processing_remaining -= 1
            if self.processing_remaining <= 0:
                self.processing = False
                processing_done = True
        

        if self.output_busy:
            self.output_transfer_remaining -= 1
            if self.output_transfer_remaining <= 0:
                self.output_busy = False
                output_done = True
        
        return input_done, processing_done, output_done
    
    def start_input(self, data: Any, size_bytes: int):
        """Start input data transfer."""
        self.input_busy = True
        self.input_data = data
        cycles = calculate_transfer_cycles(size_bytes, self.bus_width_bits)
        self.input_transfer_remaining = cycles
        self.ii_counter = self.ii
    
    def start_processing(self, data: Any):
        """Start processing data through module."""
        self.processing = True
        self.processing_data = data
        self.processing_remaining = self.latency
    
    def start_output(self, data: Any, size_bytes: int):
        """Start output data transfer."""
        self.output_busy = True
        self.output_data = data
        cycles = calculate_transfer_cycles(size_bytes, self.bus_width_bits)
        self.output_transfer_remaining = cycles
        self.output_ready = False
        self.output_pending = None
    
    def set_output_ready(self, data: Any):
        """Mark output as ready for transmission."""
        if self.output_busy:

            self.next_ready = True
            self.next_data = data
        else:
            self.output_ready = True
            self.output_pending = data
    
    def reset(self):
        """Reset pipeline state to initial state."""
        self.ii_counter = 0
        self.input_busy = False
        self.input_transfer_remaining = 0
        self.input_data = None
        self.processing = False
        self.processing_remaining = 0
        self.processing_data = None
        self.output_busy = False
        self.output_transfer_remaining = 0
        self.output_data = None
        self.output_ready = False
        self.output_pending = None
        self.next_ready = False
        self.next_data = None
        self.stats.reset()


class SwitchCore:
    """Cycle-accurate switch core with pipeline stages.
    
    Implements complete pipeline: RX → Hash → VOQ → Scheduler → Output.
    Features:
    - Cycle-accurate timing with initiation interval and latency modeling
    - Per-port RX engines with configurable bus width
    - Flexible hash engine (FullLookupTable or MultiBankHash)
    - Multiple VOQ buffer types (OneBufferPerPort or NBuffersPerPort)
    """
    
    def __init__(self, config: SwitchConfig, switch_id: str = "switch_0",
                 routing_table: Optional[Dict[int, List[Tuple[str, int, str, int]]]] = None):
        """Initialize switch core with given configuration.
        
        Args:
            config: Switch configuration object with all timing parameters
            switch_id: Unique identifier for this switch instance
            routing_table: Optional pre-configured routing table for packet forwarding
        """
        self.config = config
        self.switch_id = switch_id
        self.num_ports = config.num_ports
        self.routing_table = routing_table or {}
        

        self.rx_engine = RxEngineWrapper(config)
        self.hash_engine = HashEngine(config, self.routing_table, switch_id)
        self.voq_buffer = create_buffer(config)
        self.scheduler = create_scheduler(config, self.voq_buffer)
        

        self.current_cycle = 0
        self.current_time_ns = 0.0
        self.cycle_time_ns = 1e9 / (config.clock_frequency_mhz * 1e6)
        self.bus_width_bits = config.axis_data_width
        

        self.active_packets: Dict[int, Packet] = {}
        


        rx_ii = LatencyEstimator.estimate_rx_ii(config.num_ports)
        rx_latency = LatencyEstimator.estimate_rx_latency(config.num_ports)
        hash_ii = LatencyEstimator.estimate_hash_ii(config.hash_module_type)
        hash_latency = LatencyEstimator.estimate_hash_latency(
            config.hash_module_type, config.num_ports, config.hash_bits)
        sched_ii = LatencyEstimator.estimate_scheduler_ii(config.scheduler_type)
        sched_latency = LatencyEstimator.estimate_scheduler_latency(
            config.scheduler_type, config.buffer_type, config.num_ports)
        

        self.rx_states: List[ModulePipelineState] = [
            ModulePipelineState(
                name=f"RX_{i}", latency=rx_latency, ii=rx_ii,
                bus_width_bits=config.axis_data_width
            ) for i in range(config.num_ports)
        ]
        

        self.hash_state = ModulePipelineState(
            name="Hash", latency=hash_latency, ii=hash_ii,
            bus_width_bits=config.axis_data_width
        )
        

        self.buffer_state = ModulePipelineState(
            name="Buffer", latency=1, ii=1,
            bus_width_bits=config.axis_data_width
        )
        

        self.scheduler_state = ModulePipelineState(
            name="Scheduler", latency=sched_latency, ii=sched_ii,
            bus_width_bits=config.axis_data_width
        )
        

        self.output_states: List[ModulePipelineState] = [
            ModulePipelineState(
                name=f"Output_{i}", latency=1, ii=1,
                bus_width_bits=config.axis_data_width
            ) for i in range(config.num_ports)
        ]
        

        self.packets_received = 0
        self.packets_transmitted = 0
        self.packets_dropped = 0
        self.total_latency_ns = 0.0
        

        self.rx_per_port = [0] * self.num_ports
        self.tx_per_port = [0] * self.num_ports
        self.dropped_per_port = [0] * self.num_ports
        self.latency_per_port = [0.0] * self.num_ports
        

        self.peak_buffer_occupancy = 0
        self.scheduling_cycles = 0
        self.idle_cycles = 0
        

        self.total_active_cycles = 0
        self.total_data_transfer_cycles = 0
        self.total_decision_wait_cycles = 0
        

        self.total_bits_transferred = 0
        self.theoretical_bandwidth_gbps = BusBandwidthModel.calculate_bus_bandwidth_gbps(
            config.axis_data_width, config.clock_frequency_mhz
        )
        

        self.first_packet_arrival_time_ns = None
        self.last_packet_transmit_time_ns = None
        

        self.line_rate_achieved_cycles = 0
        self.line_rate_missed_cycles = 0
        

        self._scheduler_pending_ii_wait = 0
        


        self._rx_to_hash_queue: List[Tuple[int, Metadata, List[AxisWord], int, float, int]] = []
        self._hash_to_buffer_queue: List[Tuple[int, Metadata, List[AxisWord], int, float, int]] = []
    
    def reset(self):
        """Reset all switch modules and statistics to initial state."""
        self.rx_engine.reset()
        self.hash_engine.reset()
        self.voq_buffer.reset()
        self.scheduler.reset()
        
        self.current_cycle = 0
        self.current_time_ns = 0.0
        self.active_packets.clear()
        

        for state in self.rx_states:
            state.reset()
        self.hash_state.reset()
        self.buffer_state.reset()
        self.scheduler_state.reset()
        for state in self.output_states:
            state.reset()
        

        self.packets_received = 0
        self.packets_transmitted = 0
        self.packets_dropped = 0
        self.total_latency_ns = 0.0
        
        self.rx_per_port = [0] * self.num_ports
        self.tx_per_port = [0] * self.num_ports
        self.dropped_per_port = [0] * self.num_ports
        self.latency_per_port = [0.0] * self.num_ports
        
        self.peak_buffer_occupancy = 0
        self.scheduling_cycles = 0
        self.idle_cycles = 0
        
        self.total_active_cycles = 0
        self.total_data_transfer_cycles = 0
        self.total_decision_wait_cycles = 0
        self.total_bits_transferred = 0
        self.first_packet_arrival_time_ns = None
        self.last_packet_transmit_time_ns = None
        self.line_rate_achieved_cycles = 0
        self.line_rate_missed_cycles = 0
        self._scheduler_pending_ii_wait = 0
        
        self._rx_to_hash_queue.clear()
        self._hash_to_buffer_queue.clear()
    
    def receive_packet(self, port_id: int, packet: Packet):
        """Receive a packet on the specified input port.
        
        Args:
            port_id: Input port identifier (0 to num_ports-1)
            packet: Packet object to receive
        """
        if not (0 <= port_id < self.num_ports):
            logger.error(f"Invalid port ID: {port_id}")
            return
        
        self.rx_engine.enqueue_packet(port_id, packet)
        self.packets_received += 1
        self.rx_per_port[port_id] += 1
        

        if self.first_packet_arrival_time_ns is None:
            self.first_packet_arrival_time_ns = self.current_time_ns
        
        if packet.trace_id is not None:
            self.active_packets[packet.trace_id] = packet
        
        logger.debug(f"[{self.switch_id}] Port {port_id} received packet: {packet}")
    
    def set_global_time(self, time_ns: float):
        """Set the current simulation time in nanoseconds."""
        self.current_time_ns = time_ns
    
    def process_cycle(self, global_time_ns: float = None) -> Tuple[Dict[str, Any], List[Tuple[int, Packet, float]]]:
        """Execute one cycle of switch simulation.
        
        Processes all pipeline stages in order:
        1. RX engines parse incoming packets
        2. Hash engine performs address lookup
        3. Packets enqueued to VOQ buffer
        4. Scheduler produces matching
        5. Output stage transmits packets
        
        Args:
            global_time_ns: Global simulation time (optional, nanoseconds)
            
        Returns:
            (cycle_stats, transmitted_packets): Statistics and list of transmitted packets
        """


        if global_time_ns is not None:

            self.current_time_ns = max(self.current_time_ns, global_time_ns)
        stats = {
            'packets_processed': 0,
            'packets_scheduled': 0,
            'packets_transmitted': 0,
            'buffer_occupancy': 0,
            'module_states': {}
        }
        
        transmitted_packets = []
        any_active = False
        any_transferring = False
        

        self._tick_all_modules()
        

        rx_active = self._process_rx_stage(stats)
        any_active = any_active or rx_active
        

        hash_active = self._process_hash_stage(stats)
        any_active = any_active or hash_active
        

        buffer_active = self._process_buffer_enqueue(stats)
        any_active = any_active or buffer_active
        

        sched_active, scheduled = self._process_scheduler_stage(stats)
        any_active = any_active or sched_active
        

        output_active, tx_packets = self._process_output_stage(stats)
        any_active = any_active or output_active
        transmitted_packets.extend(tx_packets)
        

        stats['buffer_occupancy'] = self.voq_buffer.get_total_occupancy()
        self.peak_buffer_occupancy = max(self.peak_buffer_occupancy, stats['buffer_occupancy'])
        

        any_transferring = self._check_any_transferring()
        if any_transferring:
            self.total_data_transfer_cycles += 1
        

        has_pending = self.voq_buffer.has_backlogged_packets()
        if has_pending and not any_transferring:
            self.total_decision_wait_cycles += 1
        
        if any_active:
            self.total_active_cycles += 1
        else:
            self.idle_cycles += 1
        

        

        self.scheduler.end_cycle()
        self.current_cycle += 1
        self.current_time_ns += self.cycle_time_ns
        
        return stats, transmitted_packets
    
    def _tick_all_modules(self):
        """Advance all module pipeline states by one cycle."""

        for rx_state in self.rx_states:
            if rx_state.ii_counter > 0:
                rx_state.ii_counter -= 1
            if rx_state.output_busy:
                rx_state.output_transfer_remaining -= 1
                if rx_state.output_transfer_remaining <= 0:
                    rx_state.output_busy = False
        

        if self.hash_state.ii_counter > 0:
            self.hash_state.ii_counter -= 1
        if self.hash_state.output_busy:
            self.hash_state.output_transfer_remaining -= 1
            if self.hash_state.output_transfer_remaining <= 0:
                self.hash_state.output_busy = False
        

        if self.scheduler_state.ii_counter > 0:
            self.scheduler_state.ii_counter -= 1
    
    def _process_rx_stage(self, stats: dict) -> bool:
        """Process RX stage for all input ports.
        
        Each RX port processes packet metadata and data in parallel.
        Respects RX II (initiation interval) constraints.
        Returns: True if any RX activity occurred
        4. 
        
        Returns:
            
        """
        active = False
        

        for port_id in range(self.num_ports):
            rx_state = self.rx_states[port_id]
            rx_state.stats.total_cycles += 1
            
            rx_engine = self.rx_engine.rx_engines[port_id]
            

            has_input = rx_engine.has_pending_work()
            

            if rx_state.output_ready:
                if self.hash_state.can_accept_input():

                    output_data = rx_state.output_pending
                    if output_data:
                        self._rx_to_hash_queue.append(output_data)
                        data_size = len(output_data[2]) * 64
                        rx_state.output_ready = False
                        rx_state.output_pending = None
                        rx_state.output_busy = True
                        rx_state.output_transfer_remaining = calculate_transfer_cycles(data_size, self.bus_width_bits)
                        rx_state.stats.transmitting_cycles += 1
                        active = True
                        continue
                else:

                    rx_state.stats.waiting_output_cycles += 1
                    active = True
                    continue
            

            if rx_state.output_busy:
                rx_state.stats.transmitting_cycles += 1
                active = True
                continue
            


            if rx_state.processing:
                rx_state.stats.processing_cycles += 1
                active = True
                

                if has_input:
                    rx_engine.process_cycle()
                    data_out = rx_engine.get_output_data()
                    if data_out:

                        proc_data = rx_state.processing_data
                        proc_data[2].extend(data_out)

                        if data_out[-1].last:
                            proc_data[5] = True
                

                if rx_state.processing_remaining > 0:
                    rx_state.processing_remaining -= 1
                

                if rx_state.processing_remaining <= 0 and rx_state.processing_data and rx_state.processing_data[5]:

                    rx_state.processing = False
                    rx_state.output_ready = True

                    proc_data = rx_state.processing_data
                    rx_state.output_pending = (
                        proc_data[0], proc_data[1], proc_data[2], proc_data[3],
                        proc_data[4], 0  # ii_wait_cycles = 0
                    )
                    rx_state.processing_data = None
            elif has_input:

                rx_engine.process_cycle()
                data_out = rx_engine.get_output_data()
                meta_out = rx_engine.get_output_metadata()
                
                if data_out and meta_out:


                    switch_arrival_time = rx_engine.current_arrival_time_ns
                    rx_state.processing = True
                    rx_state.processing_remaining = rx_state.latency - 1
                    

                    packet_complete = data_out[-1].last if data_out else False
                    


                    rx_state.processing_data = [
                        port_id, meta_out[0], list(data_out), rx_engine.current_trace_id,
                        switch_arrival_time, packet_complete
                    ]
                    rx_state.stats.processing_cycles += 1
                    active = True
                    

                    if rx_state.processing_remaining <= 0 and packet_complete:
                        rx_state.processing = False
                        rx_state.output_ready = True
                        rx_state.output_pending = (
                            port_id, meta_out[0], rx_state.processing_data[2], rx_engine.current_trace_id,
                            switch_arrival_time, 0
                        )
                        rx_state.processing_data = None
                elif data_out:

                    rx_state.stats.receiving_cycles += 1
                    active = True
                else:

                    rx_state.stats.receiving_cycles += 1
                    active = True
            else:
                rx_state.stats.idle_cycles += 1
        
        return active
    
    def _process_hash_stage(self, stats: dict) -> bool:
        """Process hash engine stage for address lookup.
        
        Returns: True if any hash activity occurred
        """
        active = False
        hash_state = self.hash_state
        hash_state.stats.total_cycles += 1
        

        if hash_state.output_ready:
            if self.buffer_state.can_accept_input():
                output_data = hash_state.output_pending
                if output_data:
                    self._hash_to_buffer_queue.append(output_data)
                    data_size = len(output_data[2]) * 64
                    hash_state.output_ready = False
                    hash_state.output_pending = None
                    hash_state.output_busy = True
                    hash_state.output_transfer_remaining = calculate_transfer_cycles(data_size, self.bus_width_bits)
                    hash_state.stats.transmitting_cycles += 1
                    active = True
            else:
                hash_state.stats.waiting_output_cycles += 1
                active = True
        elif hash_state.output_busy:
            hash_state.stats.transmitting_cycles += 1
            active = True
        

        if hash_state.processing:
            hash_state.processing_remaining -= 1
            hash_state.stats.processing_cycles += 1
            active = True
            
            if hash_state.processing_remaining <= 0:

                hash_state.processing = False
                hash_state.output_ready = True
                hash_state.output_pending = hash_state.processing_data
                hash_state.processing_data = None

        elif self._rx_to_hash_queue and not hash_state.output_ready and not hash_state.output_busy:

            if hash_state.ii_counter > 0:
                hash_state.stats.waiting_ii_cycles += 1

                if self._rx_to_hash_queue:
                    item = self._rx_to_hash_queue[0]
                    port_id, meta, data, trace_id, arrival_time, ii_wait = item
                    self._rx_to_hash_queue[0] = (port_id, meta, data, trace_id, arrival_time, ii_wait + 1)
                active = True
            else:
                item = self._rx_to_hash_queue.pop(0)
                port_id, meta, data, trace_id, switch_arrival_time, ii_wait_cycles = item
                

                meta_list = [None] * self.num_ports
                meta_list[port_id] = meta
                processed = self.hash_engine.process_metadata(meta_list)
                
                if processed[port_id]:

                    hash_state.ii_counter = hash_state.ii
                    hash_state.stats.processing_cycles += 1
                    active = True
                    

                    output_data = (
                        port_id, processed[port_id], data, trace_id,
                        switch_arrival_time, ii_wait_cycles
                    )
                    
                    if hash_state.latency <= 1:

                        hash_state.output_ready = True
                        hash_state.output_pending = output_data
                    else:

                        hash_state.processing = True
                        hash_state.processing_remaining = hash_state.latency - 1
                        hash_state.processing_data = output_data
                else:

                    self._rx_to_hash_queue.insert(0, (
                        port_id, meta, data, trace_id,
                        switch_arrival_time, ii_wait_cycles + 1
                    ))
                    hash_state.stats.waiting_ii_cycles += 1
                    active = True
        elif not self._rx_to_hash_queue and not hash_state.output_ready and not hash_state.output_busy and not hash_state.processing:
            hash_state.stats.idle_cycles += 1
        
        return active
    
    def _process_buffer_enqueue(self, stats: dict) -> bool:
        """Process buffer enqueue stage.
        
        Returns: True if any buffer activity occurred
        """
        active = False
        buffer_state = self.buffer_state
        buffer_state.stats.total_cycles += 1
        

        if self._hash_to_buffer_queue:
            item = self._hash_to_buffer_queue.pop(0)
            port_id, meta, data, trace_id, switch_arrival_time, ii_wait_cycles = item
            


            success = self.voq_buffer.enqueue_packet(
                port_id, meta, data, self.current_time_ns, trace_id,
                switch_arrival_time=switch_arrival_time,
                accumulated_latency_cycles=ii_wait_cycles,
                current_cycle=self.current_cycle
            )
            
            if success:
                buffer_state.stats.receiving_cycles += 1
                stats['packets_processed'] += 1
                active = True
            else:
                self.packets_dropped += 1
                self.dropped_per_port[port_id] += 1
        elif self.voq_buffer.has_backlogged_packets():
            buffer_state.stats.processing_cycles += 1
            active = True
        else:
            buffer_state.stats.idle_cycles += 1
        
        return active
    
    def _process_scheduler_stage(self, stats: dict) -> Tuple[bool, int]:
        """Process scheduler stage for packet matching and dispatching.
        
        Respects scheduler latency and initiation interval constraints.
        Returns: (active, scheduled_count)
        """
        active = False
        scheduled = 0
        sched_state = self.scheduler_state
        sched_state.stats.total_cycles += 1
        
        has_pending = self.voq_buffer.has_backlogged_packets()
        

        if sched_state.processing:
            sched_state.processing_remaining -= 1
            sched_state.stats.processing_cycles += 1
            active = True
            
            if sched_state.processing_remaining <= 0:

                sched_state.processing = False
                sched_state.output_ready = True

                scheduled = len(sched_state.processing_data) if sched_state.processing_data else 0
                stats['packets_scheduled'] = scheduled
            return active, scheduled
        

        if sched_state.output_ready and sched_state.output_pending:
            transmissions = sched_state.output_pending
            all_dispatched = True
            for out_port, voq_entry in transmissions:
                out_state = self.output_states[out_port]
                if not out_state.input_busy:
                    out_state.input_busy = True
                    out_state.input_data = voq_entry
                    out_state.input_transfer_remaining = calculate_transfer_cycles(
                        voq_entry.packet_size, self.bus_width_bits)
                else:
                    all_dispatched = False

                    voq_entry.accumulated_latency_cycles += 1
            if all_dispatched:
                sched_state.output_ready = False
                sched_state.output_pending = None
                sched_state.stats.transmitting_cycles += 1
            else:
                sched_state.stats.waiting_output_cycles += 1
            active = True
        elif has_pending:

            if sched_state.ii_counter > 0:
                sched_state.stats.waiting_ii_cycles += 1

                self._scheduler_pending_ii_wait += 1
                active = True
            else:

                matches = self.scheduler.schedule_cycle()
                if matches:
                    transmissions = self.scheduler.process_matches(matches)
                    if transmissions:


                        if self._scheduler_pending_ii_wait > 0:
                            for out_port, voq_entry in transmissions:
                                voq_entry.accumulated_latency_cycles += self._scheduler_pending_ii_wait
                            self._scheduler_pending_ii_wait = 0
                        
                        sched_state.ii_counter = sched_state.ii
                        self.scheduling_cycles += 1
                        sched_state.stats.processing_cycles += 1
                        active = True
                        
                        if sched_state.latency <= 1:

                            sched_state.output_ready = True
                            sched_state.output_pending = transmissions
                            scheduled = len(transmissions)
                            stats['packets_scheduled'] = scheduled
                        else:

                            sched_state.processing = True
                            sched_state.processing_remaining = sched_state.latency - 1
                            sched_state.processing_data = transmissions
                            sched_state.output_pending = transmissions
                    else:
                        sched_state.stats.processing_cycles += 1
                        active = True
                else:
                    sched_state.stats.processing_cycles += 1
                    active = True
        else:
            sched_state.stats.idle_cycles += 1
        
        return active, scheduled
    
    def _process_output_stage(self, stats: dict) -> Tuple[bool, List[Tuple[int, Packet, float]]]:
        """Process output stage for all egress ports.
        
        Transmits packets from scheduler and calculates per-packet latency:
        - Real latency: calculated from switch arrival time to transmission time
        - Accumulated cycles: includes initiation interval wait cycles
        
        Measures line-rate achievement based on scheduler II and transfer time.
        Returns: (active, transmitted_packets)
        """
        active = False
        transmitted = []
        
        for port_id in range(self.num_ports):
            out_state = self.output_states[port_id]
            out_state.stats.total_cycles += 1
            

            if out_state.input_busy:
                out_state.stats.transmitting_cycles += 1
                active = True
                

                out_state.input_transfer_remaining -= 1
                

                if out_state.input_transfer_remaining <= 0:
                    voq_entry = out_state.input_data
                    if voq_entry:

                        pkt_size = voq_entry.packet_size
                        transfer_cycles = calculate_transfer_cycles(pkt_size, self.bus_width_bits)
                        



                        latency_ns = self.current_time_ns - voq_entry.switch_arrival_time
                        

                        first_out_time_ns = self.current_time_ns
                        

                        packet = Packet(
                            metadata=voq_entry.metadata,
                            payload=voq_entry.data_words,
                            trace_id=voq_entry.trace_id,
                            arrival_time_ns=voq_entry.switch_arrival_time,
                            creation_time_ns=first_out_time_ns
                        )
                        
                        self.total_latency_ns += latency_ns
                        self.latency_per_port[port_id] += latency_ns
                        
                        self.packets_transmitted += 1
                        self.tx_per_port[port_id] += 1
                        self.total_bits_transferred += pkt_size * 8
                        self.last_packet_transmit_time_ns = self.current_time_ns
                        stats['packets_transmitted'] += 1
                        

                        if can_achieve_line_rate(transfer_cycles, self.scheduler_state.ii):
                            self.line_rate_achieved_cycles += transfer_cycles
                        else:
                            self.line_rate_missed_cycles += transfer_cycles
                        
                        transmitted.append((port_id, packet, latency_ns))
                        logger.debug(f"[{self.switch_id}] Port {port_id} transmission complete: latency={latency_ns:.2f}ns")
                    
                    out_state.input_busy = False
                    out_state.input_data = None
            else:
                out_state.stats.idle_cycles += 1
        
        return active, transmitted
    
    def _check_any_transferring(self) -> bool:
        """Check if any module is currently transferring data.
        
        Returns: True if any data transfer is in progress
        """

        for rx_state in self.rx_states:
            if rx_state.output_busy:
                return True

        if self.hash_state.output_busy:
            return True

        for out_state in self.output_states:
            if out_state.input_busy or out_state.output_busy:
                return True
        return False
    
    def _update_module_stats(self, stats: dict):
        """Update module activity statistics in cycle stats."""
        stats['module_states'] = {
            'rx': [s.stats.to_dict() for s in self.rx_states],
            'hash': self.hash_state.stats.to_dict(),
            'buffer': self.buffer_state.stats.to_dict(),
            'scheduler': self.scheduler_state.stats.to_dict(),
            'output': [s.stats.to_dict() for s in self.output_states],
        }
    
    def has_pending_work(self) -> bool:
        """Check if switch has any pending work in any stage.
        
        Returns: True if there is any ongoing or pending processing
        """

        for i in range(self.num_ports):
            if self.rx_engine.rx_engines[i].has_pending_work():
                return True
            if self.rx_states[i].input_busy or self.rx_states[i].processing:
                return True
            if self.rx_states[i].output_ready:
                return True
        

        if self.hash_state.input_busy or self.hash_state.processing:
            return True
        if self.hash_state.output_ready or self.hash_state.output_busy:
            return True
        if self._rx_to_hash_queue:
            return True
        

        if self._hash_to_buffer_queue:
            return True
        if self.voq_buffer.has_backlogged_packets():
            return True
        

        if self.scheduler_state.processing or self.scheduler_state.output_ready:
            return True
        

        for out_state in self.output_states:
            if out_state.input_busy:
                return True
        
        return False
    
    def get_statistics(self) -> dict:
        """Get comprehensive switch statistics and performance metrics.
        
        Returns: Dictionary with detailed statistics for all modules and ports
        """
        avg_latency = self.total_latency_ns / max(1, self.packets_transmitted)
        


        if self.first_packet_arrival_time_ns is not None and self.last_packet_transmit_time_ns is not None:
            effective_time_ns = self.last_packet_transmit_time_ns - self.first_packet_arrival_time_ns
        else:
            effective_time_ns = self.current_time_ns
        


        throughput_gbps = self.total_bits_transferred / max(1e-9, effective_time_ns)
        

        port_stats = {}
        for p in range(self.num_ports):
            out_state = self.output_states[p]
            port_stats[f'port_{p}'] = {
                'rx': self.rx_per_port[p],
                'tx': self.tx_per_port[p],
                'dropped': self.dropped_per_port[p],
                'avg_latency_ns': self.latency_per_port[p] / max(1, self.tx_per_port[p]),
                'currently_transmitting': out_state.input_busy,
            }
        

        rx_total_stats = ModuleActivityStats()
        for rx_state in self.rx_states:
            rx_total_stats.total_cycles += rx_state.stats.total_cycles
            rx_total_stats.idle_cycles += rx_state.stats.idle_cycles
            rx_total_stats.receiving_cycles += rx_state.stats.receiving_cycles
            rx_total_stats.processing_cycles += rx_state.stats.processing_cycles
            rx_total_stats.transmitting_cycles += rx_state.stats.transmitting_cycles
            rx_total_stats.waiting_ii_cycles += rx_state.stats.waiting_ii_cycles
            rx_total_stats.waiting_output_cycles += rx_state.stats.waiting_output_cycles
        
        output_total_stats = ModuleActivityStats()
        for out_state in self.output_states:
            output_total_stats.total_cycles += out_state.stats.total_cycles
            output_total_stats.idle_cycles += out_state.stats.idle_cycles
            output_total_stats.transmitting_cycles += out_state.stats.transmitting_cycles
        
        return {
            'switch_id': self.switch_id,
            'current_cycle': self.current_cycle,
            'current_time_ns': self.current_time_ns,
            

            'packets_received': self.packets_received,
            'packets_transmitted': self.packets_transmitted,
            'packets_dropped': self.packets_dropped,
            'drop_rate': self.packets_dropped / max(1, self.packets_received),
            'average_latency_ns': avg_latency,
            'throughput_gbps': throughput_gbps,
            

            'port_statistics': port_stats,
            

            'bus_bandwidth_stats': {
                'bus_width_bits': self.bus_width_bits,
                'theoretical_bandwidth_gbps': self.theoretical_bandwidth_gbps,
                'actual_throughput_gbps': throughput_gbps,
                'bandwidth_utilization': throughput_gbps / max(0.001, self.theoretical_bandwidth_gbps),
                'total_bits_transferred': self.total_bits_transferred,
                'first_packet_arrival_time_ns': self.first_packet_arrival_time_ns,
                'last_packet_transmit_time_ns': self.last_packet_transmit_time_ns,
                'effective_time_ns': effective_time_ns,
            },
            

            'cycle_activity_stats': {
                'total_cycles': self.current_cycle,
                'total_active_cycles': self.total_active_cycles,
                'data_transfer_cycles': self.total_data_transfer_cycles,
                'decision_wait_cycles': self.total_decision_wait_cycles,
                'idle_cycles': self.idle_cycles,
                'active_ratio': self.total_active_cycles / max(1, self.current_cycle),
                'transfer_ratio': self.total_data_transfer_cycles / max(1, self.current_cycle),
                'wait_ratio': self.total_decision_wait_cycles / max(1, self.current_cycle),
            },
            

            'line_rate_stats': {
                'achieved_cycles': self.line_rate_achieved_cycles,
                'missed_cycles': self.line_rate_missed_cycles,
                'achievement_ratio': self.line_rate_achieved_cycles / max(1,
                    self.line_rate_achieved_cycles + self.line_rate_missed_cycles),
            },
            

            'module_activity': {
                'rx_engine': {
                    'aggregate': rx_total_stats.to_dict(),
                    'per_port': [s.stats.to_dict() for s in self.rx_states],
                    'ii': self.rx_states[0].ii if self.rx_states else 1,
                    'latency': self.rx_states[0].latency if self.rx_states else 1,
                },
                'hash_engine': {
                    **self.hash_state.stats.to_dict(),
                    'ii': self.hash_state.ii,
                    'latency': self.hash_state.latency,
                },
                'buffer': {
                    **self.buffer_state.stats.to_dict(),
                    'ii': self.buffer_state.ii,
                    'latency': self.buffer_state.latency,
                },
                'scheduler': {
                    **self.scheduler_state.stats.to_dict(),
                    'ii': self.scheduler_state.ii,
                    'latency': self.scheduler_state.latency,
                },
                'output': {
                    'aggregate': output_total_stats.to_dict(),
                    'per_port': [s.stats.to_dict() for s in self.output_states],
                },
            },
            

            'peak_buffer_occupancy': self.peak_buffer_occupancy,
            'scheduling_efficiency': self.scheduling_cycles / max(1, self.current_cycle),
            

            'architecture_metrics': {
                'num_ports': self.num_ports,
                'hash_type': self.config.hash_module_type.value,
                'buffer_type': self.config.buffer_type.value,
                'scheduler_type': self.config.scheduler_type.value,
            },
            

            'rx_engine': self.rx_engine.get_statistics(),
            'hash_engine': self.hash_engine.get_statistics(),
            'buffer': self.voq_buffer.get_statistics(),
            'scheduler': self.scheduler.get_statistics()
        }
    
    def inject_trace_entries(self, trace_entries: List[TraceEntry]):
        """Inject trace entries as packets into the switch.
        
        Args:
            trace_entries: List of TraceEntry objects to be converted to packets
        """
        for entry in trace_entries:
            packet = Packet.from_trace_entry(
                entry.time_ns, entry.src_addr, entry.dst_addr,
                entry.header_size, entry.body_size, entry.trace_id,
                self.config.addr_length, self.num_ports,
                self.config.axis_data_width
            )
            input_port = entry.src_addr % self.num_ports
            self.receive_packet(input_port, packet)
