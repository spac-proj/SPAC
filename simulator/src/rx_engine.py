"""
RX (receive) engine for packet parsing.

Processes incoming AXI-Stream packet data:
- Parses metadata (source, destination, length)
- Extracts packet headers and bodies
- Validates packets for downstream processing

Pipeline State Machine:
  HEADER -> CONSUME -> HEADER (cycle repeats)

Based on HLS estimation.txt timing:
- Latency = 2 cycles
- II = 1 (can accept packet every cycle)
"""

from typing import List, Optional, Tuple
from collections import deque
import logging

from config import SwitchConfig, LatencyEstimator
from packet import Packet, Metadata, AxisWord

logger = logging.getLogger(__name__)


class RxEngine:
    """
    RX pipeline engine.
    
    Implements a state machine processing incoming packet data:
    1. HEADER state: Parse first word containing metadata
    2. CONSUME state: Consume remaining payload words
    
    Each word is a 512-bit AXIS transaction. Extracts metadata (source,
    destination, broadcast flag) from header word and outputs to downstream.
    """
    

    STATE_HEADER = "HEADER"
    STATE_CONSUME = "CONSUME"
    
    def __init__(self, config: SwitchConfig, port_id: int):
        """
        Initialize RX engine for a specific input port.
        
        Args:
            config: Switch configuration
            port_id: Input port identifier
        """
        self.config = config
        self.port_id = port_id
        

        self.latency = LatencyEstimator.estimate_rx_latency(config.num_ports)
        self.ii = LatencyEstimator.estimate_rx_ii(config.num_ports)
        

        self.current_state = self.STATE_HEADER
        self.processing_cycles = 0
        

        self.input_queue: deque[AxisWord] = deque()
        self.output_data_queue: deque[AxisWord] = deque()
        self.output_meta_queue: deque[Metadata] = deque()
        

        self.current_packet_metadata: Optional[Metadata] = None
        self.current_trace_id: Optional[int] = None
        self.current_arrival_time_ns: float = 0.0
        

        self.current_packet_word_count: int = 0
        

        self.packet_complete: bool = False
        

        self.arrival_time_queue: deque[float] = deque()
        

        self.packets_processed = 0
        self.bytes_processed = 0
        self.cycles_active = 0
    
    def reset(self):
        """Reset RX engine to initial state."""
        self.current_state = self.STATE_HEADER
        self.processing_cycles = 0
        self.current_packet_metadata = None
        self.current_trace_id = None
        self.current_arrival_time_ns = 0.0
        self.current_packet_word_count = 0
        self.packet_complete = False
        self.input_queue.clear()
        self.output_data_queue.clear()
        self.output_meta_queue.clear()
        self.arrival_time_queue.clear()
    
    def enqueue_packet(self, packet: Packet):
        """
        Enqueue incoming packet for processing.
        
        Args:
            packet: Packet to enqueue
        """

        self.arrival_time_queue.append(packet.arrival_time_ns)
        

        axis_words = packet.get_axis_words()
        self.input_queue.extend(axis_words)
    
    def process_cycle(self) -> bool:
        """
        Process one cycle of RX engine.
        
        Returns:
            True: Processing is active (input queued or processing)
            False: Engine is idle
        """
        if not self.input_queue:
            return False
        
        self.cycles_active += 1
        

        if self.processing_cycles > 0:
            self.processing_cycles -= 1
            return True
        

        if self.current_state == self.STATE_HEADER:
            self._process_header()
        else:  # STATE_CONSUME
            self._process_consume()
        

        self.processing_cycles = self.ii - 1
        return True
    
    def _process_header(self):
        """
        Process header word of incoming packet.
        
        Extracts metadata from first word:
        - broadcast flag (1 bit @ offset 31)
        - source address (4 bits @ offset 12)
        - destination address (4 bits @ offset 8)
        - trace_id (15 bits @ offset 16)
        
        Output: Creates metadata entry and transitions to CONSUME state
        """
        if not self.input_queue:
            return
        
        header_word = self.input_queue.popleft()
        self.packet_complete = False
        

        if self.arrival_time_queue:
            self.current_arrival_time_ns = self.arrival_time_queue.popleft()
        

        is_broadcast = bool((header_word.data >> 31) & 0x1)
        dst_addr = (header_word.data >> 8) & 0xF
        src_addr = (header_word.data >> 12) & 0xF
        trace_id = (header_word.data >> 16) & 0x7FFF
        self.current_trace_id = trace_id
        



        metadata = Metadata(
            src_addr=src_addr,
            dst_addr=-1 if is_broadcast else dst_addr,
            dst_port=-1,
            pkt_len=64,
            broadcast=is_broadcast,
            valid=True
        )
        self.current_packet_metadata = metadata
        

        self.current_packet_word_count = 1
        

        self.output_meta_queue.append(metadata)
        self.output_data_queue.append(header_word)
        

        if header_word.last:

            self.packet_complete = True
            self.packets_processed += 1
            self.bytes_processed += 64
        else:

            self.current_state = self.STATE_CONSUME
    
    def _process_consume(self):
        """
        Process data word during payload consumption.
        
        Consumes payload words until last flag is seen.
        """
        if not self.input_queue:
            return
        
        data_word = self.input_queue.popleft()
        self.current_packet_word_count += 1
        

        self.output_data_queue.append(data_word)
        
        if data_word.last:

            self.packet_complete = True
            self.current_state = self.STATE_HEADER
            self.packets_processed += 1
            self.bytes_processed += self.current_packet_word_count * 64
    
    def get_output_data(self) -> List[AxisWord]:
        """Get and clear output data queue."""
        result = list(self.output_data_queue)
        self.output_data_queue.clear()
        return result
    
    def get_output_metadata(self) -> List[Metadata]:
        """Get and clear output metadata queue."""
        result = list(self.output_meta_queue)
        self.output_meta_queue.clear()
        return result
    
    def has_pending_work(self) -> bool:
        """Check if RX engine has pending work."""
        return bool(self.input_queue) or self.processing_cycles > 0
    
    def get_statistics(self) -> dict:
        """Get RX engine statistics."""
        return {
            'port_id': self.port_id,
            'packets_processed': self.packets_processed,
            'bytes_processed': self.bytes_processed,
            'cycles_active': self.cycles_active
        }


class RxEngineWrapper:
    """
    RX engine wrapper managing multiple input ports.
    
    Manages RX engines for all input ports, providing unified interface
    for packet enqueueing and output collection.
    """
    
    def __init__(self, config: SwitchConfig):
        """
        Initialize RX engine wrapper with multiple ports.
        
        Args:
            config: Switch configuration
        """
        self.config = config
        self.rx_engines = [
            RxEngine(config, port_id) 
            for port_id in range(config.num_ports)
        ]
    
    def reset(self):
        """Reset all RX engines."""
        for engine in self.rx_engines:
            engine.reset()
    
    def enqueue_packet(self, port_id: int, packet: Packet):
        """
        Enqueue packet on specific input port.
        
        Args:
            port_id: Input port identifier
            packet: Packet to enqueue
        """
        if 0 <= port_id < self.config.num_ports:
            self.rx_engines[port_id].enqueue_packet(packet)
        else:
            logger.error(f"Invalid port ID: {port_id}")
    
    def process_cycle(self) -> Tuple[List[List[AxisWord]], 
                                     List[List[Metadata]], 
                                     List[Optional[int]]]:
        """
        Process one cycle across all RX engines.
        
        Returns:
            (data_outputs, meta_outputs, trace_ids):
            - data_outputs: Output data words per port
            - meta_outputs: Output metadata per port
            - trace_ids: Current trace_id per port
        """
        data_outputs = []
        meta_outputs = []
        trace_ids = []
        
        for engine in self.rx_engines:
            engine.process_cycle()
            data_outputs.append(engine.get_output_data())
            meta_outputs.append(engine.get_output_metadata())
            trace_ids.append(engine.current_trace_id)
        
        return data_outputs, meta_outputs, trace_ids
    
    def get_statistics(self) -> dict:
        """Get statistics from all RX engines."""
        stats = {}
        total_packets = 0
        total_bytes = 0
        
        for engine in self.rx_engines:
            port_stats = engine.get_statistics()
            stats[f'port_{engine.port_id}'] = port_stats
            total_packets += port_stats['packets_processed']
            total_bytes += port_stats['bytes_processed']
        
        stats['total_packets'] = total_packets
        stats['total_bytes'] = total_bytes
        return stats
