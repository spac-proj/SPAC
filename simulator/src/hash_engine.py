"""
Address lookup and routing hash module.

Implements two address lookup strategies:
- FullLookupTable: Direct lookup table (simple, fast for small N)
- MultiBankHash: Multi-bank hashing (scalable, better for large N)

Pipeline Operations:
1. Address Extraction: Extract dest_addr from metadata
2. Address Lookup: Look up output port from address/hash

Based on HLS estimation.txt timing:
- FullLookupTable: Latency = ceil(N/2)+1, II=1
- MultiBankHash: Latency = max(4, N+2), II=3
"""

from typing import List, Dict, Optional, Tuple
import logging

from config import SwitchConfig, LatencyEstimator, HashModuleType
from packet import Metadata

logger = logging.getLogger(__name__)


class FullLookupTable:
    """
    Full address lookup table implementation.
    
    Direct mapping from destination address to output port.
    Optimal for small number of ports, simple and fast.
    Stores learned source to port mappings (learning bridge behavior).
    
    Maps address to (valid_bit, output_port).
    """
    
    def __init__(self, config: SwitchConfig, 
                 routing_table: Optional[Dict[int, List[Tuple[str, int, str, int]]]] = None,
                 switch_id: str = "switch_0"):
        """
        Initialize full lookup table address resolution.
        
        Args:
            config: Switch configuration
            routing_table: Routing table (optional)
            switch_id: Switch identifier
        """
        self.config = config
        self.routing_table = routing_table or {}
        self.switch_id = switch_id
        

        self.fwd_table: Dict[int, Tuple[bool, int]] = {}
        

        self.latency = LatencyEstimator.estimate_hash_latency(
            HashModuleType.FullLookupTable, config.num_ports
        )
        self.ii = LatencyEstimator.estimate_hash_ii(HashModuleType.FullLookupTable)
        self.processing_cycles = 0
    
    def reset(self):
        """Reset lookup table and processing state."""
        self.fwd_table.clear()
        self.processing_cycles = 0
    
    def process_metadata(self, metadata_list: List[Optional[Metadata]]) -> List[Optional[Metadata]]:
        """
        Process metadata and perform address lookup.
        
        Steps:
        1. Learn source address from incoming port
        2. Perform address lookup for destination
        
        Args:
            metadata_list: Input metadata list (may contain None)
            
        Returns:
            Metadata list with resolved output port (dst_port)
        """
        if not any(metadata_list):
            return [None] * len(metadata_list)
        

        if self.processing_cycles > 0:
            self.processing_cycles -= 1
            return [None] * len(metadata_list)
        
        results = []
        for port_id, meta in enumerate(metadata_list):
            if meta is None:
                results.append(None)
                continue
            

            self.fwd_table[meta.src_addr] = (True, port_id)
            

            if meta.broadcast or meta.dst_addr == -1:
                meta.broadcast = True
                meta.dst_port = -1
                logger.debug(f"[{self.switch_id}] Broadcast packet: src={meta.src_addr} -> all ports")
                results.append(meta)
                continue
            

            dst_addr = meta.dst_addr
            

            if dst_addr in self.routing_table and self.routing_table[dst_addr]:
                next_hop = self.routing_table[dst_addr][0]
                meta.dst_port = next_hop[1]  # next_hop_port
                meta.broadcast = False
                logger.debug(f"[{self.switch_id}] Route lookup: dst={dst_addr} -> port={meta.dst_port}")
            else:

                entry = self.fwd_table.get(dst_addr, (False, 0))
                if entry[0]:  # valid
                    meta.dst_port = entry[1]
                    meta.broadcast = False
                else:


                    if meta.dst_port < 0 or meta.dst_port >= self.config.num_ports:
                        meta.dst_port = dst_addr % self.config.num_ports
                    meta.broadcast = False
            
            results.append(meta)
        
        self.processing_cycles = self.ii - 1
        return results
    
    def get_table_size(self) -> int:
        """Get current lookup table size."""
        return len(self.fwd_table)


class MultiBankHash:
    """
    Multi-bank hash table implementation.
    
    Uses bank hashing for scalable address resolution. 
    Multiple banks provide parallel access, each bank handles
    addresses for different source ports.
    
    Bank index calculation: bank_id = address % num_banks
    """
    
    def __init__(self, config: SwitchConfig,
                 routing_table: Optional[Dict[int, List[Tuple[str, int, str, int]]]] = None,
                 switch_id: str = "switch_0"):
        """
        Initialize multi-bank hash table.
        
        Args:
            config: Switch configuration
            routing_table: Routing table rules
            switch_id: Switch identifier
        """
        self.config = config
        self.num_banks = config.num_ports
        self.hash_bits = config.hash_bits
        self.routing_table = routing_table or {}
        self.switch_id = switch_id
        

        self.fwd_table: List[Dict[int, Tuple[bool, int, int]]] = [
            {} for _ in range(self.num_banks)
        ]
        

        self.save_ptr = [0] * self.num_banks
        self.read_ptr = [0] * self.num_banks
        

        self.saved = [True] * config.num_ports
        self.read_flags = [True] * config.num_ports
        self.buffers: List[Optional[Metadata]] = [None] * config.num_ports
        

        self.latency = LatencyEstimator.estimate_hash_latency(
            HashModuleType.MultiBankHash, config.num_ports, config.hash_bits
        )
        self.ii = LatencyEstimator.estimate_hash_ii(HashModuleType.MultiBankHash)
        self.processing_cycles = 0
    
    def reset(self):
        """Reset all banks and processing state."""
        for bank in self.fwd_table:
            bank.clear()
        self.save_ptr = [0] * self.num_banks
        self.read_ptr = [0] * self.num_banks
        self.saved = [True] * self.config.num_ports
        self.read_flags = [True] * self.config.num_ports
        self.buffers = [None] * self.config.num_ports
        self.processing_cycles = 0
    
    def _get_bank(self, addr: int) -> int:
        """Calculate bank index from address."""
        return addr % self.num_banks
    
    def _get_hash_key(self, addr: int) -> int:
        """Calculate hash key from address."""
        return addr % (1 << self.hash_bits)
    
    def process_metadata(self, metadata_list: List[Optional[Metadata]]) -> List[Optional[Metadata]]:
        """
        Process metadata using multi-bank hash resolution.
        
        Steps:
        1. Save source address lookup
        2. Compute destination bank
        3. Arbitrate bank access
        """
        if not any(metadata_list):
            return [None] * len(metadata_list)
        
        if self.processing_cycles > 0:
            self.processing_cycles -= 1
            return [None] * len(metadata_list)
        
        num_ports = self.config.num_ports
        results = [None] * len(metadata_list)
        

        req_save = [[False] * self.num_banks for _ in range(num_ports)]
        req_read = [[False] * self.num_banks for _ in range(num_ports)]
        
        for sp in range(num_ports):
            if self.saved[sp] and self.read_flags[sp]:

                meta = metadata_list[sp]
                if meta is not None:

                    if meta.broadcast or meta.dst_addr == -1:
                        meta.broadcast = True
                        meta.dst_port = -1
                        results[sp] = meta
                        logger.debug(f"[{self.switch_id}] Broadcast packet: src={meta.src_addr} -> all ports")
                        continue
                    
                    self.buffers[sp] = meta
                    src_bank = self._get_bank(meta.src_addr)
                    dst_bank = self._get_bank(meta.dst_addr)
                    req_save[sp][src_bank] = True
                    req_read[sp][dst_bank] = True
                    self.saved[sp] = False
                    self.read_flags[sp] = False
            else:

                if not self.saved[sp] and self.buffers[sp]:
                    req_save[sp][self._get_bank(self.buffers[sp].src_addr)] = True
                if not self.read_flags[sp] and self.buffers[sp]:
                    req_read[sp][self._get_bank(self.buffers[sp].dst_addr)] = True
        

        grant_save = [-1] * self.num_banks
        grant_read = [-1] * self.num_banks
        
        for bank in range(self.num_banks):

            ptr = self.save_ptr[bank]
            for _ in range(num_ports):
                if req_save[ptr][bank]:
                    grant_save[bank] = ptr
                    break
                ptr = (ptr + 1) % num_ports
            self.save_ptr[bank] = ptr
            

            ptr = self.read_ptr[bank]
            for _ in range(num_ports):
                if req_read[ptr][bank]:
                    grant_read[bank] = ptr
                    break
                ptr = (ptr + 1) % num_ports
            self.read_ptr[bank] = ptr
        

        save_done = [False] * num_ports
        read_done = [False] * num_ports
        
        for bank in range(self.num_banks):

            sp = grant_save[bank]
            if sp != -1 and self.buffers[sp]:
                meta = self.buffers[sp]
                hash_key = self._get_hash_key(meta.src_addr)
                self.fwd_table[bank][hash_key] = (True, meta.src_addr, sp)
                save_done[sp] = True
            

            sp = grant_read[bank]
            if sp != -1 and self.buffers[sp]:
                meta = self.buffers[sp]
                hash_key = self._get_hash_key(meta.dst_addr)
                entry = self.fwd_table[bank].get(hash_key, (False, 0, 0))
                
                if entry[0] and entry[1] == meta.dst_addr:
                    meta.dst_port = entry[2]
                    meta.broadcast = False
                else:



                    if meta.dst_port < 0 or meta.dst_port >= self.config.num_ports:
                        meta.dst_port = meta.dst_addr % self.config.num_ports
                    meta.broadcast = False
                
                results[sp] = meta
                read_done[sp] = True
        

        for sp in range(num_ports):
            if save_done[sp]:
                self.saved[sp] = True
            if read_done[sp]:
                self.read_flags[sp] = True
        
        self.processing_cycles = self.ii - 1
        return results
    
    def get_table_size(self) -> int:
        """Get total hash table size across all banks."""
        return sum(len(bank) for bank in self.fwd_table)


class HashEngine:
    """
    Hash engine wrapper.
    
    Provides unified interface for both FullLookupTable and
    MultiBankHash implementations.
    """
    
    def __init__(self, config: SwitchConfig,
                 routing_table: Optional[Dict[int, List[Tuple[str, int, str, int]]]] = None,
                 switch_id: str = "switch_0"):
        """
        Initialize hash engine.
        
        Args:
            config: Switch configuration
            routing_table: Routing table rules
            switch_id: Switch identifier
        """
        self.config = config
        self.routing_table = routing_table or {}
        self.switch_id = switch_id
        

        if config.hash_module_type == HashModuleType.FullLookupTable:
            self.impl = FullLookupTable(config, routing_table, switch_id)
        else:
            self.impl = MultiBankHash(config, routing_table, switch_id)
    
    def reset(self):
        """Reset hash engine implementation."""
        self.impl.reset()
    
    def process_metadata(self, metadata_list: List[Optional[Metadata]]) -> List[Optional[Metadata]]:
        """Process metadata through hash engine."""
        return self.impl.process_metadata(metadata_list)
    
    def get_statistics(self) -> dict:
        """Get hash engine statistics."""
        return {
            'hash_type': self.config.hash_module_type.value,
            'table_size': self.impl.get_table_size(),
            'latency': self.impl.latency,
            'ii': self.impl.ii
        }
