"""
Virtual Output Queue (VOQ) buffer management for network switch simulation.

Implements two buffer organization modes:
- OneBufferPerPort (1b1p): One shared queue per output port (eliminates HOL blocking)
- NBuffersPerPort (nb1p/VOQ): Independent queue per (src,dst) pair (full VOQ)

Buffer Configuration:

1. OneBufferPerPort (1b1p):
   - One queue per output port
   - Total: N queues (where N = number of ports)
   - Eliminates destination-based head-of-line blocking
   - Configuration: global_voq_size (single size) or voq_sizes[N]

2. NBuffersPerPort (nb1p/VOQ):
   - Independent queue per (source, destination) pair
   - Total: N×N queues (where src==dst queues are unused)
   - Complete isolation between flows
   - Configuration: global_voq_size (per-pair size) or voq_sizes[N*N]
   - Index calculation: idx = src * N + dst
"""

from typing import List, Dict, Optional, Deque, Tuple
from collections import deque
import logging
import math

from config import SwitchConfig, BufferType
from packet import Metadata, AxisWord

logger = logging.getLogger(__name__)


class VOQEntry:
    """
    Virtual Output Queue entry wrapper.
    
    Encapsulates packet data for efficient queue management.
    """
    
    def __init__(self, input_port: int, metadata: Metadata, 
                 data_words: List[AxisWord], trace_id: int = None,
                 word_size_bytes: int = 64):
        """
        Initialize VOQ entry.
        
        Args:
            input_port: Input port identifier
            metadata: Packet metadata
            data_words: Payload words
            trace_id: Packet trace ID
            word_size_bytes: Word size in bytes
        """
        self.input_port = input_port
        self.metadata = metadata
        self.data_words = data_words.copy()
        self.trace_id = trace_id
        self.word_size_bytes = word_size_bytes
        self.arrival_time = 0.0
        self.switch_arrival_time = 0.0
        self.enqueue_cycle = 0
        self.accumulated_latency_cycles = 0
        self.retries = 0
        self.backoff_cycles = 0
    
    @property
    def packet_size(self) -> int:
        """Get packet size in bytes."""
        return len(self.data_words) * self.word_size_bytes
    
    @property
    def memory_size(self) -> int:
        """Get memory size consumed in bytes."""
        return self.packet_size
    
    @property
    def is_broadcast(self) -> bool:
        """Check if packet is broadcast."""
        return self.metadata.broadcast
    
    def __repr__(self):
        return (f"VOQEntry(in={self.input_port}, "
                f"dst={self.metadata.dst_addr}:{self.metadata.dst_port}, "
                f"size={self.packet_size}B)")


class OneBufferPerPortBuffer:
    """
    OneBufferPerPort buffer organization.
    
    Implements one shared buffer per output port:
    - One queue per output port
    - Total: N queues (where N = number of ports)
    - Eliminates destination-based head-of-line blocking
    
    Logically stores voq[input][output], but shares memory per output port.
    Multiple inputs can write to same output port's buffer.
    """
    
    def __init__(self, config: SwitchConfig):
        """
        Initialize OneBufferPerPort buffer manager.
        
        Args:
            config: Switch configuration
        """
        self.config = config
        self.num_ports = config.num_ports
        self.buffer_type = BufferType.OneBufferPerPort
        self.word_size_bytes = config.axis_data_width // 8
        

        self.port_limits_bytes: List[int] = []
        for dst in range(self.num_ports):
            size = config.get_voq_size(src_port=0, dst_port=dst)
            self.port_limits_bytes.append(size)
        

        self.port_used_bytes: List[int] = [0] * self.num_ports
        

        self.port_peak_bytes: List[int] = [0] * self.num_ports
        


        self.voq: List[List[Deque[VOQEntry]]] = [
            [deque() for _ in range(self.num_ports)]
            for _ in range(self.num_ports)
        ]
        
        logger.info(f"OneBufferPerPort buffer initialized: per-port capacities = {self.port_limits_bytes} bytes")
        

        self.total_enqueued = 0
        self.total_dequeued = 0
        self.total_dropped = 0
        self.total_dropped_overflow = 0
        self.current_occupancy = 0
        self.peak_occupancy = 0
        self.peak_memory_used = 0
    
    def reset(self):
        """Reset buffer state."""
        for input_port in range(self.num_ports):
            for output_port in range(self.num_ports):
                self.voq[input_port][output_port].clear()
        
        self.port_used_bytes = [0] * self.num_ports
        self.port_peak_bytes = [0] * self.num_ports
        
        self.total_enqueued = 0
        self.total_dequeued = 0
        self.total_dropped = 0
        self.total_dropped_overflow = 0
        self.current_occupancy = 0
        self.peak_occupancy = 0
        self.peak_memory_used = 0
    
    def enqueue_packet(self, input_port: int, metadata: Metadata,
                       data_words: List[AxisWord], current_time: float = 0.0,
                       trace_id: int = None,
                       switch_arrival_time: float = None,
                       accumulated_latency_cycles: int = 0,
                       current_cycle: int = 0) -> bool:
        """
        Enqueue packet to VOQ.
        
        Args:
            input_port: Input port
            metadata: Packet metadata
            data_words: Payload words
            current_time: Current simulation time (nanoseconds)
            trace_id: Packet trace ID
            switch_arrival_time: Switch arrival time
            accumulated_latency_cycles: Accumulated latency
            current_cycle: Current cycle number
            
        Returns:
            True: Enqueue successful
            False: Enqueue failed (buffer full)
        """

        output_ports = self._get_output_ports(input_port, metadata)
        

        packet_memory = len(data_words) * self.word_size_bytes
        

        for out_port in output_ports:
            if self.port_used_bytes[out_port] + packet_memory > self.port_limits_bytes[out_port]:
                self.total_dropped += 1
                self.total_dropped_overflow += 1
                logger.debug(f"Dropped packet: port {input_port} -> {out_port}, output port {out_port} queue full "
                            f"(used={self.port_used_bytes[out_port]}, need={packet_memory}, "
                            f"limit={self.port_limits_bytes[out_port]})")
                return False
        

        entry = VOQEntry(input_port, metadata, data_words, trace_id, self.word_size_bytes)
        entry.arrival_time = current_time
        entry.switch_arrival_time = switch_arrival_time if switch_arrival_time is not None else current_time
        entry.enqueue_cycle = current_cycle
        entry.accumulated_latency_cycles = accumulated_latency_cycles
        
        for out_port in output_ports:
            self.voq[input_port][out_port].append(entry)
            self.port_used_bytes[out_port] += packet_memory

            self.port_peak_bytes[out_port] = max(
                self.port_peak_bytes[out_port], 
                self.port_used_bytes[out_port]
            )
        
        self.total_enqueued += 1
        self.current_occupancy += len(output_ports)
        
        self.peak_occupancy = max(self.peak_occupancy, self.current_occupancy)
        total_memory = sum(self.port_used_bytes)
        self.peak_memory_used = max(self.peak_memory_used, total_memory)
        
        return True
    
    def _get_output_ports(self, input_port: int, metadata: Metadata) -> List[int]:
        """Get output ports for packet."""
        if metadata.broadcast:
            return [p for p in range(self.num_ports) if p != input_port]
        return [metadata.dst_port]
    
    def dequeue_packet(self, input_port: int, output_port: int) -> Optional[VOQEntry]:
        """
        Dequeue packet from VOQ.
        
        Args:
            input_port: Input port
            output_port: Output port
            
        Returns:
            VOQEntry or None if queue empty
        """
        if not self.voq[input_port][output_port]:
            return None
        
        entry = self.voq[input_port][output_port].popleft()
        self.total_dequeued += 1
        self.current_occupancy -= 1
        

        self.port_used_bytes[output_port] -= entry.memory_size
        self.port_used_bytes[output_port] = max(0, self.port_used_bytes[output_port])
        
        return entry
    
    def peek_packet(self, input_port: int, output_port: int) -> Optional[VOQEntry]:
        """Peek at front packet without removing."""
        queue = self.voq[input_port][output_port]
        return queue[0] if queue else None
    
    def get_queue_length(self, input_port: int, output_port: int) -> int:
        """Get queue length in packets."""
        return len(self.voq[input_port][output_port])
    
    def get_non_empty_queues(self, output_port: int) -> List[int]:
        """Get list of input ports with queued packets for output port."""
        return [i for i in range(self.num_ports) 
                if self.voq[i][output_port]]
    
    def get_total_occupancy(self) -> int:
        """Get total number of packets in all queues."""
        return sum(len(self.voq[i][j]) 
                   for i in range(self.num_ports)
                   for j in range(self.num_ports))
    
    def get_memory_utilization(self) -> float:
        """Get memory utilization ratio (0.0 to 1.0)."""
        total_used = sum(self.port_used_bytes)
        total_capacity = sum(self.port_limits_bytes)
        return total_used / max(1, total_capacity)
    
    def has_backlogged_packets(self) -> bool:
        """Check if any packets are queued."""
        return any(queue for queues in self.voq for queue in queues)
    
    def get_peak_voq_sizes(self) -> Dict[int, int]:
        """
        Get peak VOQ sizes per output port.
        
        Returns:
            Dict[dst_port, peak_bytes]: Peak buffer usage per port
        """
        return {i: self.port_peak_bytes[i] for i in range(self.num_ports)}
    
    def get_statistics(self) -> dict:
        """Get comprehensive buffer statistics."""
        queue_lengths = [len(self.voq[i][j]) 
                         for i in range(self.num_ports)
                         for j in range(self.num_ports)]
        
        total_queues = self.num_ports
        empty_queues = sum(1 for p in range(self.num_ports) if self.port_used_bytes[p] == 0)
        avg_length = sum(queue_lengths) / max(1, len(queue_lengths))
        max_length = max(queue_lengths) if queue_lengths else 0
        

        per_port_stats = {}
        for dst in range(self.num_ports):
            packets = sum(len(self.voq[src][dst]) for src in range(self.num_ports))
            per_port_stats[f'dst_{dst}'] = {
                'limit_bytes': self.port_limits_bytes[dst],
                'used_bytes': self.port_used_bytes[dst],
                'peak_bytes': self.port_peak_bytes[dst],
                'packets': packets,
                'utilization': self.port_used_bytes[dst] / max(1, self.port_limits_bytes[dst])
            }
        
        return {
            'buffer_type': self.buffer_type.value,
            'organization': 'per_output_port',
            'num_logical_queues': self.num_ports,
            

            'total_enqueued': self.total_enqueued,
            'total_dequeued': self.total_dequeued,
            'total_dropped': self.total_dropped,
            'total_dropped_overflow': self.total_dropped_overflow,
            'drop_rate': self.total_dropped / max(1, self.total_enqueued + self.total_dropped),
            

            'current_memory_used': sum(self.port_used_bytes),
            'peak_memory_used': self.peak_memory_used,
            'memory_utilization': self.get_memory_utilization(),
            

            'current_occupancy': self.current_occupancy,
            'peak_occupancy': self.peak_occupancy,
            'average_queue_length': avg_length,
            'max_queue_length': max_length,
            'empty_queues': empty_queues,
            'total_queues': total_queues,
            

            'per_port': per_port_stats,
            

            'peak_voq_sizes': self.get_peak_voq_sizes(),
            

            'enqueue_success_rate': self.total_enqueued / max(1, self.total_enqueued + self.total_dropped)
        }


class NBuffersPerPortBuffer:
    """
    NBuffersPerPort (VOQ) buffer organization.
    
    Implements independent queue per (source, destination) pair:
    - One queue per (src, dst) pair
    - Total: N×N queues (src==dst queues have zero size)
    - Complete isolation between flows
    
    Index: voq[src][dst] stores queue from source src to port dst
    """
    
    def __init__(self, config: SwitchConfig):
        """
        Initialize NBuffersPerPort (VOQ) buffer manager.
        
        Args:
            config: Switch configuration
        """
        self.config = config
        self.num_ports = config.num_ports
        self.buffer_type = BufferType.NBuffersPerPort
        self.word_size_bytes = config.axis_data_width // 8
        

        self.voq: List[List[Deque[VOQEntry]]] = [
            [deque() for _ in range(self.num_ports)]
            for _ in range(self.num_ports)
        ]
        


        self.voq_limits_bytes: List[List[int]] = []
        for src in range(self.num_ports):
            row = []
            for dst in range(self.num_ports):
                if src == dst:

                    row.append(0)
                else:
                    size = config.get_voq_size(src_port=src, dst_port=dst)
                    row.append(size)
            self.voq_limits_bytes.append(row)
        

        self.voq_used_bytes: List[List[int]] = [
            [0] * self.num_ports for _ in range(self.num_ports)
        ]
        

        self.voq_peak_bytes: List[List[int]] = [
            [0] * self.num_ports for _ in range(self.num_ports)
        ]
        
        logger.info(f"NBuffersPerPort buffer initialized: {self.num_ports}x{self.num_ports} queues")
        

        self.total_enqueued = 0
        self.total_dequeued = 0
        self.total_dropped = 0
        self.total_dropped_overflow = 0
        self.current_occupancy = 0
        self.peak_occupancy = 0
    
    def reset(self):
        """Reset buffer state."""
        for src in range(self.num_ports):
            for dst in range(self.num_ports):
                self.voq[src][dst].clear()
                self.voq_used_bytes[src][dst] = 0
                self.voq_peak_bytes[src][dst] = 0
        
        self.total_enqueued = 0
        self.total_dequeued = 0
        self.total_dropped = 0
        self.total_dropped_overflow = 0
        self.current_occupancy = 0
        self.peak_occupancy = 0
    
    def enqueue_packet(self, input_port: int, metadata: Metadata,
                       data_words: List[AxisWord], current_time: float = 0.0,
                       trace_id: int = None,
                       switch_arrival_time: float = None,
                       accumulated_latency_cycles: int = 0,
                       current_cycle: int = 0) -> bool:
        """
        Enqueue packet to VOQ.
        
        Args:
            input_port: Input port of packet source
            metadata: Packet metadata
            data_words: Payload words
            current_time: Current simulation time (nanoseconds)
            trace_id: Packet trace ID
            switch_arrival_time: Switch arrival time
            accumulated_latency_cycles: Accumulated latency
            current_cycle: Current cycle number
            
        Returns:
            True: Enqueue successful
            False: Enqueue failed (buffer full)
        """

        output_ports = self._get_output_ports(input_port, metadata)
        

        entry = VOQEntry(input_port, metadata, data_words, trace_id, self.word_size_bytes)
        entry.arrival_time = current_time
        entry.switch_arrival_time = switch_arrival_time if switch_arrival_time is not None else current_time
        entry.enqueue_cycle = current_cycle
        entry.accumulated_latency_cycles = accumulated_latency_cycles
        
        packet_size = entry.packet_size
        

        for dst in output_ports:
            limit = self.voq_limits_bytes[input_port][dst]
            used = self.voq_used_bytes[input_port][dst]
            
            if used + packet_size > limit:
                self.total_dropped += 1
                self.total_dropped_overflow += 1
                logger.debug(f"Dropped packet: port {input_port} -> {dst}, VOQ full "
                           f"(used={used}B + {packet_size}B > limit={limit}B)")
                return False
        

        for dst in output_ports:
            self.voq[input_port][dst].append(entry)
            self.voq_used_bytes[input_port][dst] += packet_size

            self.voq_peak_bytes[input_port][dst] = max(
                self.voq_peak_bytes[input_port][dst],
                self.voq_used_bytes[input_port][dst]
            )
        
        self.total_enqueued += 1
        self.current_occupancy += len(output_ports)
        self.peak_occupancy = max(self.peak_occupancy, self.current_occupancy)
        
        return True
    
    def _get_output_ports(self, input_port: int, metadata: Metadata) -> List[int]:
        """
        Get output ports for packet.
        
        Returns multiple ports for broadcast, single port otherwise.
        """
        if metadata.broadcast:
            return [p for p in range(self.num_ports) if p != input_port]
        return [metadata.dst_port]
    
    def dequeue_packet(self, input_port: int, output_port: int) -> Optional[VOQEntry]:
        """
        Dequeue packet from specific VOQ.
        
        Args:
            input_port: Source port of packet
            output_port: Destination port of packet
            
        Returns:
            VOQEntry or None if queue empty
        """
        if not self.voq[input_port][output_port]:
            return None
        
        entry = self.voq[input_port][output_port].popleft()
        

        self.voq_used_bytes[input_port][output_port] -= entry.packet_size
        self.voq_used_bytes[input_port][output_port] = max(
            0, self.voq_used_bytes[input_port][output_port]
        )
        
        self.total_dequeued += 1
        self.current_occupancy -= 1
        return entry
    
    def peek_packet(self, input_port: int, output_port: int) -> Optional[VOQEntry]:
        """Peek at front packet without removing."""
        queue = self.voq[input_port][output_port]
        return queue[0] if queue else None
    
    def get_queue_length(self, input_port: int, output_port: int) -> int:
        """Get queue length in packets."""
        return len(self.voq[input_port][output_port])
    
    def get_non_empty_queues(self, output_port: int) -> List[int]:
        """Get list of input ports with queued packets for output port."""
        return [i for i in range(self.num_ports) 
                if self.voq[i][output_port]]
    
    def get_total_occupancy(self) -> int:
        """Get total number of packets in all queues."""
        return sum(len(self.voq[i][j]) 
                   for i in range(self.num_ports)
                   for j in range(self.num_ports))
    
    def get_voq_occupancy(self, src: int, dst: int) -> Dict[str, int]:
        """Get occupancy of specific VOQ."""
        return {
            'packets': len(self.voq[src][dst]),
            'limit_bytes': self.voq_limits_bytes[src][dst],
            'used_bytes': self.voq_used_bytes[src][dst],
            'peak_bytes': self.voq_peak_bytes[src][dst]
        }
    
    def has_backlogged_packets(self) -> bool:
        """Check if any packets are queued."""
        return any(queue for queues in self.voq for queue in queues)
    
    def get_peak_voq_sizes(self) -> Dict[Tuple[int, int], int]:
        """
        Get peak VOQ sizes per (source, destination) pair.
        
        Returns:
            Dict[(src, dst), peak_bytes]: Peak buffer usage per VOQ
        """
        result = {}
        for src in range(self.num_ports):
            for dst in range(self.num_ports):
                if src != dst:
                    result[(src, dst)] = self.voq_peak_bytes[src][dst]
        return result
    
    def get_peak_voq_sizes_flat(self) -> List[int]:
        """
        Get peak VOQ sizes as flattened list.
        
        Returns:
             List of N*N values, index i = src * N + dst
        """
        result = []
        for src in range(self.num_ports):
            for dst in range(self.num_ports):
                result.append(self.voq_peak_bytes[src][dst])
        return result
    
    def get_statistics(self) -> dict:
        """Get comprehensive buffer statistics."""

        queue_lengths = [len(self.voq[i][j]) 
                         for i in range(self.num_ports)
                         for j in range(self.num_ports)]
        
        total_queues = self.num_ports * self.num_ports
        empty_queues = sum(1 for l in queue_lengths if l == 0)
        avg_length = sum(queue_lengths) / max(1, total_queues)
        max_length = max(queue_lengths) if queue_lengths else 0
        

        total_capacity_bytes = sum(
            self.voq_limits_bytes[i][j] 
            for i in range(self.num_ports) 
            for j in range(self.num_ports)
        )
        total_used_bytes = sum(
            self.voq_used_bytes[i][j] 
            for i in range(self.num_ports) 
            for j in range(self.num_ports)
        )
        

        per_voq_stats = {}
        for src in range(self.num_ports):
            for dst in range(self.num_ports):
                if src != dst:
                    key = f'voq_{src}_{dst}'
                    per_voq_stats[key] = {
                        'limit_bytes': self.voq_limits_bytes[src][dst],
                        'used_bytes': self.voq_used_bytes[src][dst],
                        'peak_bytes': self.voq_peak_bytes[src][dst],
                        'packets': len(self.voq[src][dst]),
                        'utilization': self.voq_used_bytes[src][dst] / max(1, self.voq_limits_bytes[src][dst])
                    }
        
        return {
            'buffer_type': self.buffer_type.value,
            'organization': 'per_src_dst_pair',
            'num_logical_queues': self.num_ports * (self.num_ports - 1),
            

            'total_enqueued': self.total_enqueued,
            'total_dequeued': self.total_dequeued,
            'total_dropped': self.total_dropped,
            'total_dropped_overflow': self.total_dropped_overflow,
            'drop_rate': self.total_dropped / max(1, self.total_enqueued + self.total_dropped),
            

            'current_occupancy': self.current_occupancy,
            'peak_occupancy': self.peak_occupancy,
            'total_capacity_bytes': total_capacity_bytes,
            'total_used_bytes': total_used_bytes,
            'overall_utilization': total_used_bytes / max(1, total_capacity_bytes),
            

            'average_queue_length': avg_length,
            'max_queue_length': max_length,
            'empty_queues': empty_queues,
            'total_queues': total_queues,
            

            'per_voq': per_voq_stats,
            

            'peak_voq_sizes': self.get_peak_voq_sizes(),
            'peak_voq_sizes_flat': self.get_peak_voq_sizes_flat(),
            

            'enqueue_success_rate': self.total_enqueued / max(1, self.total_enqueued + self.total_dropped)
        }



SharedMemoryBuffer = OneBufferPerPortBuffer
VOQBuffer = NBuffersPerPortBuffer


def create_buffer(config: SwitchConfig):
    """
    Create buffer instance based on configuration.
    
    Args:
        config: Switch configuration
        
    Returns:
        OneBufferPerPortBuffer or NBuffersPerPortBuffer instance
    """
    if config.buffer_type == BufferType.OneBufferPerPort:
        return OneBufferPerPortBuffer(config)
    else:
        return NBuffersPerPortBuffer(config)
