"""
Network Simulation Framework

This module provides cycle-accurate network simulation functionality:
- Single and multi-switch topology support
- Event-driven simulation engine
- Packet tracing and statistics collection

Simulation flow:
1. Load topology configuration
2. Schedule packet injection events
3. Run event loop
4. Collect statistical results
"""

import logging
from typing import List, Dict, Optional, Any, Callable, Tuple
from collections import defaultdict, deque
import time as time_module
import heapq

from config import SwitchConfig
from switch_core import SwitchCore
from trace_parser import TraceParser, TopologyParser
from packet import Packet, TraceEntry, NetworkTopology

logger = logging.getLogger(__name__)


class SimulationEvent:
    """
    Simulation Event
    
    Events are sorted by time, with events at the same time sorted by priority (higher priority processed first)
    """
    
    def __init__(self, time_ns: float, event_type: str, 
                 data: Any = None, priority: int = 0):
        self.time_ns = time_ns
        self.event_type = event_type
        self.data = data
        self.priority = priority
    
    def __lt__(self, other):
        if self.time_ns != other.time_ns:
            return self.time_ns < other.time_ns
        return self.priority > other.priority
    
    def __repr__(self):
        return f"Event({self.time_ns}ns, {self.event_type})"


class NetworkSimulator:
    """
    Network Simulator
    
    Supports cycle-accurate simulation for single and multi-switch topologies
    """
    
    def __init__(self, config: Optional[SwitchConfig] = None):
        """
        Initialize the simulator
        
        Args:
            config: Switch configuration (optional)
        """
        self.config = config or SwitchConfig()
        self.cycle_time_ns = 1e9 / (self.config.clock_frequency_mhz * 1e6)
        
        # Switches
        self.switches: Dict[str, SwitchCore] = {}
        
        # Event queue
        self.event_queue: List[SimulationEvent] = []
        self.current_time_ns = 0.0
        
        # Topology information
        self.topology: Dict[str, Dict[str, Any]] = {}
        self.connections: List[NetworkTopology] = []
        self.hosts: Dict[str, Dict[str, Any]] = {}
        self.link_delays_ns: Dict[Tuple[str, int, str, int], float] = {}
        
        # Routing table
        self.routing_table: Dict[str, Dict[int, List[Tuple[str, int, str, int]]]] = {}
        
        # Packet tracing
        self.active_packets: Dict[int, Dict[str, Any]] = {}
        self.host_stats: Dict[str, Dict[str, Any]] = {}
        
        # Statistics
        self.total_events_processed = 0
        self.simulation_start_time = 0.0
        self.simulation_end_time = 0.0
        
        # Callbacks
        self.event_callbacks: Dict[str, List[Callable]] = defaultdict(list)
    
    def add_switch(self, switch_id: str, config: Optional[SwitchConfig] = None) -> SwitchCore:
        """Add a switch to the simulator"""
        cfg = config or self.config
        routing_info = self.routing_table.get(switch_id, {})
        switch = SwitchCore(cfg, switch_id, routing_info)
        self.switches[switch_id] = switch
        logger.info(f"Added switch {switch_id} with {cfg.num_ports} ports")
        return switch
    
    def load_topology(self, topology_file: str):
        """
        Load network topology
        
        Args:
            topology_file: Path to topology CSV file
        """
        parser = TopologyParser(topology_file)
        self.connections = parser.parse_all()
        
        # Initialize nodes
        for conn in self.connections:
            for node in [conn.node_a, conn.node_b]:
                if node in self.topology:
                    continue
                    
                if node.startswith('s'):
                    # Switch node
                    switch_id = f"switch_{node[1:]}"
                    self.topology[node] = {
                        'type': 'switch',
                        'id': switch_id,
                        'ports': {}
                    }
                    if switch_id not in self.switches:
                        self.add_switch(switch_id)
                else:
                    # Host node
                    self.topology[node] = {
                        'type': 'host',
                        'id': node,
                        'connected_switch': None,
                        'connected_port': None
                    }
                    self.hosts[node] = self.topology[node]
                    self.host_stats[node] = {
                        'packets_sent': 0,
                        'packets_received': 0,
                        'total_latency_ns': 0.0,
                        'total_hops': 0
                    }
        
        # Setup connections
        for conn in self.connections:
            if conn.is_switch_to_switch:
                self._setup_switch_link(conn)
            else:
                self._setup_host_link(conn)
        
        # Build routing table and update switches
        self._build_routing_table()
        self._update_switch_routing()
        
        logger.info(f"Loaded topology: {len(self.switches)} switches, {len(self.hosts)} hosts")
    
    def _setup_switch_link(self, conn: NetworkTopology):
        """Setup inter-switch link"""
        src_switch = f"switch_{conn.node_a[1:]}"
        dst_switch = f"switch_{conn.node_b[1:]}"
        
        self.topology[conn.node_a]['ports'][conn.port_a] = {
            'type': 'switch', 'switch_id': dst_switch
        }
        self.topology[conn.node_b]['ports'][conn.port_b] = {
            'type': 'switch', 'switch_id': src_switch
        }
        
        # Bidirectional link delay
        delay_ns = 10.0
        self.link_delays_ns[(src_switch, conn.port_a, dst_switch, conn.port_b)] = delay_ns
        self.link_delays_ns[(dst_switch, conn.port_b, src_switch, conn.port_a)] = delay_ns
    
    def _setup_host_link(self, conn: NetworkTopology):
        """Setup host-switch link"""
        if conn.node_a.startswith('s'):
            switch_node, host_node = conn.node_a, conn.node_b
            switch_port, host_port = conn.port_a, conn.port_b
        else:
            switch_node, host_node = conn.node_b, conn.node_a
            switch_port, host_port = conn.port_b, conn.port_a
        
        switch_id = f"switch_{switch_node[1:]}"
        
        self.hosts[host_node]['connected_switch'] = switch_id
        self.hosts[host_node]['connected_port'] = switch_port
        
        self.topology[switch_node]['ports'][switch_port] = {
            'type': 'host', 'host_id': host_node
        }
        
        # Host-switch link delay
        delay_ns = 1.0
        self.link_delays_ns[(switch_id, switch_port, host_node, 0)] = delay_ns
        self.link_delays_ns[(host_node, 0, switch_id, switch_port)] = delay_ns
    
    def _build_routing_table(self):
        """Build routing table using BFS"""
        for switch_id in self.switches:
            self.routing_table[switch_id] = {}
            self._build_routing_for_switch(switch_id)
    
    def _build_routing_for_switch(self, switch_id: str):
        """Build routing table for a single switch"""
        switch_topo = f"s{switch_id.split('_')[1]}"
        
        visited = {switch_topo}
        queue = deque([(switch_topo, None, None)])
        parent_map = {switch_topo: (None, None, None)}
        
        while queue:
            node, _, _ = queue.popleft()
            
            # If it is a host, record the path
            if node in self.hosts:
                path = self._reconstruct_path(node, switch_topo, parent_map)
                try:
                    dst_addr = int(node)
                    self.routing_table[switch_id][dst_addr] = path
                except ValueError:
                    pass
                continue
            
            # Explore neighbors
            for conn in self.connections:
                neighbor, n_port, c_port = None, None, None
                
                if conn.node_a == node:
                    neighbor, n_port, c_port = conn.node_b, conn.port_b, conn.port_a
                elif conn.node_b == node:
                    neighbor, n_port, c_port = conn.node_a, conn.port_a, conn.port_b
                
                if neighbor and neighbor not in visited:
                    visited.add(neighbor)
                    parent_map[neighbor] = (node, c_port, n_port)
                    queue.append((neighbor, c_port, n_port))
    
    def _reconstruct_path(self, dst: str, src: str, parent_map: dict) -> List[Tuple]:
        """Reconstruct path from source to destination"""
        path = []
        node = dst
        
        while node != src and node in parent_map:
            parent, p_port, c_port = parent_map[node]
            if parent is None:
                break
            
            from_node = f"switch_{parent[1:]}" if parent.startswith('s') else parent
            to_node = f"switch_{node[1:]}" if node.startswith('s') else node
            path.insert(0, (from_node, p_port, to_node, c_port))
            node = parent
        
        return path if node == src else []
    
    def _update_switch_routing(self):
        """Update routing table for all switches"""
        for switch_id, switch in self.switches.items():
            routing_info = self.routing_table.get(switch_id, {})
            switch.hash_engine.routing_table = routing_info
            switch.hash_engine.impl.routing_table = routing_info
    
    def schedule_packet_injection(self, trace_file: str):
        """
        Schedule packet injection from trace file
        
        Args:
            trace_file: Path to trace CSV file
        """
        parser = TraceParser(trace_file)
        entries = parser.parse_all()
        
        for entry in entries:
            src_host = str(entry.src_addr)
            
            if src_host not in self.hosts:
                logger.warning(f"Source host {src_host} does not exist")
                continue
            
            host_info = self.hosts[src_host]
            if not host_info['connected_switch']:
                continue
            
            event = SimulationEvent(
                time_ns=entry.time_ns,
                event_type="host_inject",
                data={
                    'trace_entry': entry,
                    'target_switch': host_info['connected_switch'],
                    'target_port': host_info['connected_port'],
                    'inject_from_host': src_host
                }
            )
            heapq.heappush(self.event_queue, event)
        
        logger.info(f"Scheduled {len(entries)} packet injection events")
    
    def run_simulation(self, max_time_ns: Optional[float] = None,
                       max_cycles: Optional[int] = None) -> dict:
        """
        Run simulation
        
        Args:
            max_time_ns: Maximum simulation time (ns)
            max_cycles: Maximum number of cycles
            
        Returns:
            Simulation statistics results
        """
        self.simulation_start_time = time_module.time()

        logger.info("Starting simulation...")

        cycle_count = 0
        max_cycle_limit = max_cycles
        if max_time_ns is not None:
            max_cycle_limit = int(max_time_ns / self.cycle_time_ns)

        # Progress tracking: print every 1000 transmitted packets
        _last_tx_printed = 0

        while self.event_queue:
            if max_cycle_limit and cycle_count >= max_cycle_limit:
                break

            event = heapq.heappop(self.event_queue)
            self.current_time_ns = event.time_ns

            # Process events
            if event.event_type in ("packet_inject", "host_inject", "switch_inject"):
                self._process_injection(event)
            elif event.event_type == "packet_transmission":
                self._process_transmission(event)
            elif event.event_type == "switch_cycle":
                self._process_switch_cycle(event)

            # Trigger callbacks
            for callback in self.event_callbacks.get(event.event_type, []):
                callback(event)

            # Schedule pending switch cycles
            self._schedule_pending_cycles()

            cycle_count += 1

            # Print progress every 1000 TX packets
            tx = sum(sw.packets_transmitted for sw in self.switches.values())
            if tx >= _last_tx_printed + 1000:
                elapsed = time_module.time() - self.simulation_start_time
                print(f"    TX={tx}  sim_t={self.current_time_ns/1e6:.3f}ms  "
                      f"({elapsed:.1f}s)")
                _last_tx_printed = (tx // 1000) * 1000

        self.simulation_end_time = time_module.time()

        stats = self._collect_statistics()
        stats.update({
            'simulation_time_seconds': self.simulation_end_time - self.simulation_start_time,
            'cycles_simulated': cycle_count,
            'final_time_ns': self.current_time_ns
        })

        logger.info("Simulation completed")
        return stats
    
    def _process_injection(self, event: SimulationEvent):
        """Process packet injection event"""
        data = event.data
        entry = data['trace_entry']
        switch_id = data['target_switch']
        port = data.get('target_port', 0)
        
        switch = self.switches[switch_id]
        packet = Packet.from_trace_entry(
            entry.time_ns, entry.src_addr, entry.dst_addr,
            entry.header_size, entry.body_size, entry.trace_id,
            switch.config.addr_length, switch.config.num_ports,
            switch.config.axis_data_width
        )
        
        switch.receive_packet(port, packet)
        
        # Update statistics
        src_host = data.get('inject_from_host')
        if src_host and src_host in self.host_stats:
            self.host_stats[src_host]['packets_sent'] += 1
        
        self.active_packets[entry.trace_id] = {
            'injection_time': entry.time_ns,
            'current_switch': switch_id,
            'source_host': src_host,
            'hops': 0,
            'path': [switch_id]
        }
    
    def _process_transmission(self, event: SimulationEvent):
        """Process packet transmission event"""
        data = event.data
        packet = data['packet']
        to_switch = data['to_switch']
        to_port = data['to_port']
        
        # Check if packet has reached destination host
        if to_switch in self.hosts:
            self._deliver_to_host(packet, to_switch)
    
    def _deliver_to_host(self, packet: Packet, host_id: str):
        """Deliver packet to host"""
        if packet.trace_id in self.active_packets:
            info = self.active_packets[packet.trace_id]
            info['completion_time'] = self.current_time_ns
            info['total_latency'] = self.current_time_ns - info['injection_time']
            
            if host_id in self.host_stats:
                stats = self.host_stats[host_id]
                stats['packets_received'] += 1
                stats['total_latency_ns'] += info['total_latency']
                stats['total_hops'] += info.get('hops', 0)
    
    def _process_switch_cycle(self, event: SimulationEvent):
        """Process switch cycle event"""
        switch_id = event.data['switch_id']
        switch = self.switches[switch_id]
        
        # Pass global time to maintain synchronization
        _, transmitted = switch.process_cycle(global_time_ns=event.time_ns)
        
        for out_port, packet, _ in transmitted:
            self._route_packet(switch_id, out_port, packet)
    
    def _route_packet(self, from_switch: str, from_port: int, packet: Packet):
        """Route packet to next hop"""
        # Find switch node
        switch_node = None
        for node_id, node_info in self.topology.items():
            if node_info['type'] == 'switch' and node_info['id'] == from_switch:
                switch_node = node_id
                break
        
        if not switch_node:
            return
        
        port_info = self.topology[switch_node]['ports'].get(from_port)
        if not port_info:
            return
        
        dst_addr = packet.metadata.dst_addr
        
        if port_info['type'] == 'host':
            host_id = port_info['host_id']
            # Check if it is the destination host
            try:
                if int(host_id.lstrip('h')) == int(str(dst_addr).lstrip('h')):
                    self._schedule_delivery(from_switch, from_port, packet, host_id)
                    return
            except ValueError:
                pass
        
        if port_info['type'] == 'switch':
            next_switch = port_info['switch_id']
            next_port = packet.metadata.dst_port
            self._schedule_transmission(from_switch, from_port, packet, next_switch, next_port)
    
    def _schedule_delivery(self, from_switch: str, from_port: int, 
                          packet: Packet, host_id: str):
        """Schedule packet delivery to host"""
        delay = self.link_delays_ns.get((from_switch, from_port, host_id, 0), 1.0)
        
        event = SimulationEvent(
            time_ns=self.current_time_ns + delay,
            event_type="packet_transmission",
            priority=1,
            data={
                'packet': packet,
                'from_switch': from_switch,
                'from_port': from_port,
                'to_switch': host_id,
                'to_port': from_port
            }
        )
        heapq.heappush(self.event_queue, event)
    
    def _schedule_transmission(self, from_switch: str, from_port: int,
                               packet: Packet, next_switch: str, next_port: int):
        """Schedule packet transmission to next switch"""
        delay = self.link_delays_ns.get((from_switch, from_port, next_switch, next_port), 10.0)
        
        event = SimulationEvent(
            time_ns=self.current_time_ns + delay,
            event_type="packet_transmission",
            data={
                'packet': packet,
                'from_switch': from_switch,
                'from_port': from_port,
                'to_switch': next_switch,
                'to_port': next_port
            }
        )
        heapq.heappush(self.event_queue, event)
    
    def _schedule_pending_cycles(self):
        """Schedule switch cycles with pending work"""
        for switch_id, switch in self.switches.items():
            if switch.has_pending_work():
                event = SimulationEvent(
                    time_ns=self.current_time_ns + self.cycle_time_ns,
                    event_type="switch_cycle",
                    data={'switch_id': switch_id}
                )
                heapq.heappush(self.event_queue, event)
    
    def _collect_statistics(self) -> dict:
        """Collect simulation statistics"""
        stats = {
            'switches': {},
            'hosts': {},
            'network': {
                'completed_packets': 0,
                'avg_packet_latency_ns': 0.0,
                'network_throughput_gbps': 0.0,
                'total_hops': 0,
                'avg_hops': 0.0,
                'last_packet_completion_time_ns': 0.0
            },
            'topology': {
                'num_switches': len(self.switches),
                'num_hosts': len(self.hosts),
                'num_links': len(self.connections)
            }
        }
        
        # Switch statistics
        total_bytes = 0
        for switch_id, switch in self.switches.items():
            switch_stats = switch.get_statistics()
            stats['switches'][switch_id] = switch_stats
            total_bytes += switch_stats.get('packets_transmitted', 0) * 64
        
        # Host statistics
        for host_id in self.hosts:
            host_stat = self.host_stats.get(host_id, {})
            rx = host_stat.get('packets_received', 0)
            stats['hosts'][host_id] = {
                'packets_sent': host_stat.get('packets_sent', 0),
                'packets_received': rx,
                'avg_latency_ns': host_stat.get('total_latency_ns', 0) / max(1, rx)
            }
        
        # Network-level statistics
        completed = 0
        total_latency = 0.0
        total_hops = 0
        last_completion_time = 0.0
        
        for p in self.active_packets.values():
            if 'completion_time' in p:
                completed += 1
                total_latency += p.get('total_latency', 0)
                total_hops += p.get('hops', 0)
                last_completion_time = max(last_completion_time, p['completion_time'])
        
        stats['network']['completed_packets'] = completed
        stats['network']['avg_packet_latency_ns'] = total_latency / max(1, completed)
        stats['network']['total_hops'] = total_hops
        stats['network']['avg_hops'] = total_hops / max(1, completed)
        stats['network']['last_packet_completion_time_ns'] = last_completion_time
        
        # Calculate network throughput
        sim_time_s = max(1e-9, self.current_time_ns * 1e-9)
        stats['network']['network_throughput_gbps'] = (total_bytes * 8) / sim_time_s / 1e9
        
        return stats
    
    def reset(self):
        """Reset the simulator"""
        self.event_queue.clear()
        self.current_time_ns = 0.0
        self.active_packets.clear()
        
        for switch in self.switches.values():
            switch.reset()
        
        for host_id in self.host_stats:
            self.host_stats[host_id] = {
                'packets_sent': 0,
                'packets_received': 0,
                'total_latency_ns': 0.0,
                'total_hops': 0
            }
        
        logger.info("Simulator reset")
