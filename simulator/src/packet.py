"""
Packet and data structure definitions for network simulation.

Core data types for representing packets and metadata in the simulator:
- Metadata: Packet metadata (source, destination, length)
- AxisWord: AXI-Stream format data word (512-bit)
- Packet: Complete packet representation
- TraceEntry: Packet injection trace entry
- NetworkTopology: Network topology connection descriptor

Based on HLS implementation (switch_hls/include/common.hpp).
"""

from dataclasses import dataclass
from typing import List, Optional
import math


@dataclass
class Metadata:
    """
    Packet metadata for routing and classification.
    
    Mirrors HLS metadata_t structure. Contains essential packet information
    for routing, scheduling, and statistics collection.
    
    Attributes:
        src_addr: Source address (ADDR_LENGTH bits)
        dst_addr: Destination address (ADDR_LENGTH bits)
        dst_port: Destination output port number
        pkt_len: Packet length in bytes
        broadcast: Broadcast flag (True if multicast)
        valid: Validity flag
    """
    src_addr: int
    dst_addr: int
    dst_port: int
    pkt_len: int
    broadcast: bool = False
    valid: bool = True
    
    def __post_init__(self):
        """Validate metadata on initialization."""
        if self.src_addr < 0:
            raise ValueError("Source address must be non-negative")
        if self.dst_addr < -1:
            raise ValueError("Destination address must be non-negative or -1 for broadcast")
        if self.pkt_len < 0:
            raise ValueError("Packet length must be non-negative")
        if self.dst_addr == -1:
            object.__setattr__(self, 'broadcast', True)


@dataclass
class AxisWord:
    """
    AXI-Stream data word (512-bit).
    
    Mirrors HLS axis_word_t structure for 512-bit AXIS transfers.
    
    Attributes:
        data: 512-bit payload data
        last: TLAST signal, marks last word of packet
        trace_id: Packet identifier for tracing (optional)
    """
    data: int
    last: bool = False
    trace_id: Optional[int] = None
    
    def __post_init__(self):
        """Validate data value on initialization."""
        if not (0 <= self.data < 2**512):
            raise ValueError("Data must be a 512-bit value")


@dataclass
class Packet:
    """
    Complete packet representation with metadata and payload.
    
    Combines routing metadata with AXI-Stream formatted payload for
    complete packet representation in simulator.

    Attributes:
        metadata: Packet metadata (routing information)
        payload: AXI-Stream format payload words
        trace_id: Packet identifier
        arrival_time_ns: Packet arrival time (ns)
        creation_time_ns: Packet creation time (ns)
        axis_data_width: AXI bus width (bits); default 512
    """
    metadata: Metadata
    payload: List[AxisWord]
    trace_id: Optional[int] = None
    arrival_time_ns: float = 0.0
    creation_time_ns: float = 0.0
    axis_data_width: int = 512 
    
    @property
    def total_bytes(self) -> int:
        """Calculate total packet bytes."""
        word_size_bytes = self.axis_data_width // 8
        return len(self.payload) * word_size_bytes
    
    @property
    def header_size(self) -> int:
        """Get header size in bytes."""
        return 64 if self.payload else 0
    
    @property
    def body_size(self) -> int:
        """Get body size in bytes."""
        return max(0, self.total_bytes - self.header_size)
    
    def get_axis_words(self) -> List[AxisWord]:
        """Get copy of AXIS words payload."""
        return self.payload.copy()
    
    @classmethod
    def from_trace_entry(cls, time_ns: float, src_addr: int, dst_addr: int,
                         header_size: int, body_size: int, trace_id: int,
                         addr_length: int = 4, num_ports: int = 4,
                         axis_data_width: int = 512) -> 'Packet':
        """
        Create packet from trace file entry.

        Args:
            time_ns: Injection time (ns)
            src_addr: Source address
            dst_addr: Destination address
            header_size: Header size (bytes)
            body_size: Body size (bytes)
            trace_id: Packet ID
            addr_length: Address length bits
            num_ports: Number of ports
            axis_data_width: AXI bus width (bits, default 512)

        Returns:
            Packet object
        """
        word_size_bytes = axis_data_width // 8

        total_bytes = header_size + body_size
        num_words = max(1, math.ceil(total_bytes / word_size_bytes))
        is_broadcast = (dst_addr == -1)
        broadcast_bit = 1 if is_broadcast else 0
        payload = []
        for i in range(num_words):
            data = (broadcast_bit << 31) | \
                   ((trace_id & 0x7FFF) << 16) | \
                   ((src_addr & 0xF) << 12) | \
                   ((max(0, dst_addr) & 0xF) << 8) | \
                   (i & 0xFF)
            payload.append(AxisWord(data=data, last=(i == num_words - 1)))

        metadata = Metadata(
            src_addr=src_addr,
            dst_addr=dst_addr,
            dst_port=-1 if is_broadcast else dst_addr, 
            pkt_len=total_bytes,
            broadcast=is_broadcast,
            valid=True
        )

        return cls(
            metadata=metadata,
            payload=payload,
            trace_id=trace_id,
            arrival_time_ns=time_ns,
            creation_time_ns=time_ns,
            axis_data_width=axis_data_width
        )


@dataclass
class TraceEntry:
    """
    Trace file entry representing a packet injection event.
    
    CSV Format: time,src_addr,dst_addr,header_size,body_size,trace_id
    """
    time_ns: float
    src_addr: int
    dst_addr: int
    header_size: int
    body_size: int
    trace_id: int
    
    @classmethod
    def from_csv_row(cls, row: List[str]) -> 'TraceEntry':
        """Parse TraceEntry from CSV row."""
        if len(row) != 6:
            raise ValueError(f"Expected 6 columns, got {len(row)}")
        return cls(
            time_ns=float(row[0]),
            src_addr=int(row[1]),
            dst_addr=int(row[2]),
            header_size=int(row[3]),
            body_size=int(row[4]),
            trace_id=int(row[5])
        )


@dataclass  
class NetworkTopology:
    """
    Network topology connection descriptor.
    
    Represents a link between two nodes (switches or hosts).
    Node ID conventions:
    - Switch: "s0", "s1", ... (prefixed with 's')
    - Host: "0", "1", ... (numeric only)
    """
    node_a: str   
    port_a: int   
    node_b: str   
    port_b: int   
    
    @classmethod
    def from_csv_row(cls, row: List[str]) -> 'NetworkTopology':
        """Parse NetworkTopology from CSV row."""
        if len(row) != 4:
            raise ValueError(f"Expected 4 columns, got {len(row)}")
        return cls(node_a=row[0], port_a=int(row[1]),
                   node_b=row[2], port_b=int(row[3]))
    
    @property
    def is_switch_to_switch(self) -> bool:
        """Check if link connects two switches."""
        return self.node_a.startswith('s') and self.node_b.startswith('s')
    
    @property
    def is_host_to_switch(self) -> bool:
        """Check if link connects host and switch."""
        a_is_host = self.node_a.isdigit()
        b_is_host = self.node_b.isdigit()
        a_is_switch = self.node_a.startswith('s')
        b_is_switch = self.node_b.startswith('s')
        return (a_is_host and b_is_switch) or (b_is_host and a_is_switch)
