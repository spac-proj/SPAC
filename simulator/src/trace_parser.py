"""
Trace file parser for loading simulation traffic and topology.

CSV parsers:
- TraceParser: Parse packet injection trace files
- TopologyParser: Parse network topology files

File Formats:
- Trace: time,src_addr,dst_addr,header_size,body_size,trace_id
- Topology: node_a,port_a,node_b,port_b
"""

import csv
from typing import List, Iterator, Optional
from pathlib import Path
import logging

from packet import TraceEntry, NetworkTopology

logger = logging.getLogger(__name__)


class TraceParser:
    """
    Trace file parser.
    
    Parses CSV trace files containing packet injections:
    - Reads packet arrivals with source/destination
    - Supports header/body size separation
    """
    
    EXPECTED_HEADER = ['time', 'src_addr', 'dst_addr', 'header_size', 'body_size', 'trace_id']
    
    def __init__(self, trace_file: str):
        """
        Initialize trace file parser.
        
        Args:
            trace_file: Path to trace CSV file
        """
        self.trace_file = Path(trace_file)
        if not self.trace_file.exists():
            raise FileNotFoundError(f"Trace file not found: {trace_file}")
        self._validate_format()
    
    def _validate_format(self):
        """Validate CSV header format."""
        with open(self.trace_file, 'r') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            
            if header is None:
                raise ValueError("Trace file is empty")
            if header != self.EXPECTED_HEADER:
                raise ValueError(f"Invalid file header: {header}")
    
    def parse_all(self) -> List[TraceEntry]:
        """Parse all entries from trace file."""
        return list(self.parse_iter())
    
    def parse_iter(self) -> Iterator[TraceEntry]:
        """Parse trace file iteratively."""
        with open(self.trace_file, 'r') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            
            for line_num, row in enumerate(reader, start=2):
                try:
                    yield TraceEntry.from_csv_row(row)
                except (ValueError, IndexError) as e:
                    logger.warning(f"Skipping invalid line {line_num}: {e}")
    
    def get_time_range(self) -> tuple:
        """Get min and max time from trace."""
        times = [e.time_ns for e in self.parse_iter()]
        return (min(times), max(times)) if times else (0, 0)
    
    def get_packet_count(self) -> int:
        """Get total packet count."""
        return sum(1 for _ in self.parse_iter())
    
    def filter_by_time(self, start: float, end: float) -> List[TraceEntry]:
        """Filter entries by time range."""
        return [e for e in self.parse_iter() if start <= e.time_ns <= end]
    
    def filter_by_address(self, src: Optional[List[int]] = None,
                          dst: Optional[List[int]] = None) -> List[TraceEntry]:
        """Filter entries by source/destination address."""
        entries = []
        for e in self.parse_iter():
            if src and e.src_addr not in src:
                continue
            if dst and e.dst_addr not in dst:
                continue
            entries.append(e)
        return entries
    
    def get_statistics(self) -> dict:
        """Get trace file statistics."""
        entries = self.parse_all()
        if not entries:
            return {'packet_count': 0}
        
        total_bytes = sum(e.header_size + e.body_size for e in entries)
        src_addrs = set(e.src_addr for e in entries)
        dst_addrs = set(e.dst_addr for e in entries)
        
        min_time = min(e.time_ns for e in entries)
        max_time = max(e.time_ns for e in entries)
        duration = max_time - min_time
        
        return {
            'packet_count': len(entries),
            'total_bytes': total_bytes,
            'unique_src': len(src_addrs),
            'unique_dst': len(dst_addrs),
            'duration_ns': duration,
            'avg_rate_pps': len(entries) / max(1e-9, duration * 1e-9),
            'avg_bw_gbps': (total_bytes * 8) / max(1e-9, duration)
        }


class TopologyParser:
    """
    Network topology file parser.
    
    Parses CSV topology files describing network connections.
    """
    
    def __init__(self, topology_file: str):
        """
        Initialize topology file parser.
        
        Args:
            topology_file: Path to topology CSV file
        """
        self.topology_file = Path(topology_file)
        if not self.topology_file.exists():
            raise FileNotFoundError(f"Topology file not found: {topology_file}")
        self._validate_format()
    
    def _validate_format(self):
        """Validate topology file format."""
        with open(self.topology_file, 'r') as f:
            reader = csv.reader(f)
            
            for row in reader:
                if not row or row[0].startswith('#'):
                    continue
                if len(row) == 4:
                    NetworkTopology.from_csv_row(row) 
                    return
            
            raise ValueError("No valid topology data found")
    
    def parse_all(self) -> List[NetworkTopology]:
        """Parse all topology connections."""
        connections = []
        with open(self.topology_file, 'r') as f:
            reader = csv.reader(f)
            
            for line_num, row in enumerate(reader, start=1):
                if not row or row[0].startswith('#'):
                    continue
                
                try:
                    connections.append(NetworkTopology.from_csv_row(row))
                except (ValueError, IndexError) as e:
                    logger.warning(f"Skipping invalid line {line_num}: {e}")
        
        return connections
    
    def get_node_types(self) -> dict:
        """Get switches and hosts from topology."""
        switches = set()
        hosts = set()
        
        for conn in self.parse_all():
            for node in [conn.node_a, conn.node_b]:
                if node.startswith('s'):
                    switches.add(node)
                else:
                    hosts.add(node)
        
        return {
            'switches': sorted(switches),
            'hosts': sorted(hosts),
            'num_switches': len(switches),
            'num_hosts': len(hosts)
        }
    
    def get_switch_connections(self, switch_id: str) -> List[NetworkTopology]:
        """Get all connections for a specific switch."""
        return [c for c in self.parse_all() 
                if c.node_a == switch_id or c.node_b == switch_id]
    
    def get_statistics(self) -> dict:
        """Get topology statistics."""
        connections = self.parse_all()
        node_types = self.get_node_types()
        
        s2s = sum(1 for c in connections if c.is_switch_to_switch)
        h2s = sum(1 for c in connections if c.is_host_to_switch)
        
        return {
            'total_connections': len(connections),
            'switch_to_switch': s2s,
            'host_to_switch': h2s,
            **node_types
        }
