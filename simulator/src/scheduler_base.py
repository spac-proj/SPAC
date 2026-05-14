"""
Packet scheduler implementations for output port arbitration.

Supports two scheduling algorithms:
- RoundRobin: Simple round-robin (low latency, good for uniform traffic)
- iSLIP: Slip-based scheduler (high throughput, works better with VOQ)

Pipeline Stages:
1. Request-phase: All VOQs that have packets signal
2. Grant-phase: Arbiter grants winner
3. Accept-phase: Winner VOQ confirms acceptance

Based on HLS estimation.txt timing:
- iSLIP (1b1p): Latency ≈ 0.679·N + 6.5
- RoundRobin (nb1p): Latency ≈ 0.679·N + 3.5
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Tuple, Set
import logging
import random

from config import SwitchConfig, SchedulerType, BufferType, LatencyEstimator
from buffer_voq import VOQBuffer, VOQEntry

logger = logging.getLogger(__name__)


class SchedulerMatch:
    """
    Scheduler match between input and output port.
    
    Represents a potential or confirmed packet transmission.
    """
    
    def __init__(self, input_port: int, output_port: int, priority: int = 0):
        self.input_port = input_port
        self.output_port = output_port
        self.priority = priority
    
    def __repr__(self):
        return f"Match({self.input_port}->{self.output_port})"


class BaseScheduler(ABC):
    """
    Abstract base class for packet schedulers.
    
    Implements request-grant-accept three-stage pipeline:
    - Request phase: VOQs signal availability
    - Grant phase: Arbiter selects winners
    - Accept phase: Winners confirm transmission
    """
    
    def __init__(self, config: SwitchConfig, voq_buffer: VOQBuffer):
        """
        Initialize scheduler.
        
        Args:
            config: Switch configuration
            voq_buffer: VOQ buffer instance
        """
        self.config = config
        self.voq_buffer = voq_buffer
        self.num_ports = config.num_ports
        

        self.latency = self._estimate_latency()
        

        self.output_busy: List[bool] = [False] * self.num_ports
        self.output_grants: List[Optional[int]] = [None] * self.num_ports
        

        self.backoff_counters: Dict[Tuple[int, int], int] = {}
        self.port_congestion: Dict[int, int] = {}
        

        self.current_cycle = 0
        self.total_scheduled = 0
        self.total_conflicts = 0
        self.cycles_with_scheduling = 0
    
    def _estimate_latency(self) -> int:
        """Estimate scheduler latency from configuration."""
        return LatencyEstimator.estimate_scheduler_latency(
            self.config.scheduler_type,
            self.config.buffer_type,
            self.num_ports,
            self.config.max_queue_depth_log
        )
    
    def reset(self):
        """Reset scheduler state."""
        self.current_cycle = 0
        self.output_busy = [False] * self.num_ports
        self.output_grants = [None] * self.num_ports
        self.backoff_counters.clear()
        self.port_congestion.clear()
        self.total_scheduled = 0
        self.total_conflicts = 0
        self.cycles_with_scheduling = 0
    
    @abstractmethod
    def schedule_cycle(self) -> List[SchedulerMatch]:
        """
        Perform one scheduling cycle.
        
        Returns:
            List of scheduler matches
        """
        pass
    
    def process_matches(self, matches: List[SchedulerMatch]) -> List[Tuple[int, VOQEntry]]:
        """
        Process scheduler matches and dequeue packets.
        
        Args:
            matches: List of scheduler matches
            
        Returns:
            List of (output_port, voq_entry) tuples for transmission
        """
        transmissions = []
        self.output_grants = [None] * self.num_ports
        
        for match in matches:
            in_port = match.input_port
            out_port = match.output_port
            

            if self.output_busy[out_port]:
                self.total_conflicts += 1
                continue
            

            backoff_key = (in_port, out_port)
            if backoff_key in self.backoff_counters:
                if self.backoff_counters[backoff_key] > 0:
                    self.backoff_counters[backoff_key] -= 1
                    continue
            

            packet = self.voq_buffer.dequeue_packet(in_port, out_port)
            if packet is None:
                continue
            

            self.output_busy[out_port] = True
            self.output_grants[out_port] = in_port
            
            transmissions.append((out_port, packet))
            self.total_scheduled += 1
            logger.debug(f"Scheduled: {match}, dst_port={packet.metadata.dst_port}")
        

        self._update_backoff()
        
        return transmissions
    
    def _update_backoff(self):
        """Update backoff counters."""
        expired = [k for k, v in self.backoff_counters.items() if v <= 0]
        for k in expired:
            del self.backoff_counters[k]
    
    def end_cycle(self):
        """Mark end of scheduling cycle."""
        self.current_cycle += 1
        self.output_busy = [False] * self.num_ports
    
    def get_statistics(self) -> dict:
        """Get scheduler statistics."""
        total_decisions = self.total_scheduled + self.total_conflicts
        conflict_rate = self.total_conflicts / max(1, total_decisions)
        

        from config import LatencyEstimator
        scheduler_ii = LatencyEstimator.estimate_scheduler_ii(self.config.scheduler_type)
        
        return {
            'scheduler_type': self.config.scheduler_type.value,
            'total_scheduled': self.total_scheduled,
            'total_conflicts': self.total_conflicts,
            'conflict_rate': conflict_rate,
            'latency_cycles': self.latency,
            'ii_cycles': scheduler_ii,
            'current_backoffs': len(self.backoff_counters),
            'cycles_with_scheduling': self.cycles_with_scheduling,
            'scheduling_rate': self.cycles_with_scheduling / max(1, self.current_cycle),
        }


class RoundRobinScheduler(BaseScheduler):
    """
    Simple round-robin scheduler.
    
    Selects input ports in round-robin order:
    - Low complexity
    - Pointer-based arbitration
    - Fair for uniform traffic
    """
    
    def __init__(self, config: SwitchConfig, voq_buffer: VOQBuffer):
        super().__init__(config, voq_buffer)
        

        self.input_pointers: List[int] = [0] * self.num_ports

        self.output_pointer = 0
    
    def reset(self):
        super().reset()
        self.input_pointers = [0] * self.num_ports
        self.output_pointer = 0
    
    def schedule_cycle(self) -> List[SchedulerMatch]:
        """
        Perform round-robin scheduling cycle.
        
        Scans output ports in round-robin order,
        selects input with available packet.
        """
        matches = []
        

        for offset in range(self.num_ports):
            out_port = (self.output_pointer + offset) % self.num_ports
            
            if self.output_busy[out_port]:
                continue
            

            in_port = self._find_ready_input(out_port)
            if in_port is not None:
                matches.append(SchedulerMatch(in_port, out_port))
        

        self.output_pointer = (self.output_pointer + 1) % self.num_ports
        
        if matches:
            self.cycles_with_scheduling += 1
        
        return matches
    
    def _find_ready_input(self, output_port: int) -> Optional[int]:
        """Find ready input port for given output port."""
        start = self.input_pointers[output_port]
        
        for offset in range(self.num_ports):
            in_port = (start + offset) % self.num_ports
            if self.voq_buffer.get_queue_length(in_port, output_port) > 0:

                self.input_pointers[output_port] = (in_port + 1) % self.num_ports
                return in_port
        
        return None


class iSLIPScheduler(BaseScheduler):
    """
    iSLIP (iterative round-robin with priorities) scheduler.
    
    SLIP-based scheduler with multiple iterations:
    1. Request phase: VOQs signal requests
    2. Grant phase: Arbiters grant winners
    3. Accept phase: Winners confirm acceptance
    
    Higher throughput than round-robin through multiple iterations.
    """
    
    def __init__(self, config: SwitchConfig, voq_buffer: VOQBuffer):
        super().__init__(config, voq_buffer)
        

        self.input_grants: List[Optional[int]] = [None] * self.num_ports

        self.max_iterations = 4
    
    def reset(self):
        super().reset()
        self.input_grants = [None] * self.num_ports
    
    def schedule_cycle(self) -> List[SchedulerMatch]:
        """Perform iSLIP scheduling cycle."""
        matches = []
        self.input_grants = [None] * self.num_ports
        

        for _ in range(self.max_iterations):
            iter_matches = self._islip_iteration()
            matches.extend(iter_matches)
            self._accept_matches(iter_matches)
            

            if len(matches) == self.num_ports:
                break
        
        if matches:
            self.cycles_with_scheduling += 1
        
        return matches
    
    def _islip_iteration(self) -> List[SchedulerMatch]:
        """Perform one iSLIP iteration."""
        matches = []
        

        requests: List[Optional[int]] = [None] * self.num_ports
        for in_port in range(self.num_ports):
            if self.input_grants[in_port] is None:
                requests[in_port] = self._get_preferred_output(in_port)
        

        grants: List[Optional[int]] = [None] * self.num_ports
        for out_port in range(self.num_ports):
            if self.output_busy[out_port]:
                continue
            

            requesters = [i for i in range(self.num_ports) 
                          if requests[i] == out_port]
            if requesters:
                grants[out_port] = min(requesters)
        

        for in_port in range(self.num_ports):
            if self.input_grants[in_port] is None:
                for out_port in range(self.num_ports):
                    if grants[out_port] == in_port:
                        matches.append(SchedulerMatch(in_port, out_port))
                        break
        
        return matches
    
    def _get_preferred_output(self, input_port: int) -> Optional[int]:
        """Get preferred output port (longest queue)."""
        max_len = 0
        preferred = None
        
        for out_port in range(self.num_ports):
            length = self.voq_buffer.get_queue_length(input_port, out_port)
            if length > max_len:
                max_len = length
                preferred = out_port
        
        return preferred
    
    def _accept_matches(self, matches: List[SchedulerMatch]):
        """Accept scheduled matches."""
        for match in matches:
            self.input_grants[match.input_port] = match.output_port


class EDRRMScheduler(BaseScheduler):
    """
    Exhaustive Dual Round-Robin Matching (EDRRM) scheduler.

    Uses exhaustive service discipline: once a VOQ starts being served,
    the input pointer stays locked to that destination until the queue
    is drained. This reduces latency under bursty traffic by avoiding
    unnecessary queue switching.

    Differences from iSLIP:
    - Two phases (request + grant) instead of three (request + grant + accept)
    - Typically needs only 1 iteration per cycle
    - Input pointer is NOT advanced when the granted queue still has packets
    """

    def __init__(self, config: SwitchConfig, voq_buffer: VOQBuffer):
        super().__init__(config, voq_buffer)
        self.rr_index_in: List[int] = [0] * self.num_ports
        self.rr_index_out: List[int] = [0] * self.num_ports
        self.max_iterations = 1

    def reset(self):
        super().reset()
        self.rr_index_in = [0] * self.num_ports
        self.rr_index_out = [0] * self.num_ports

    def schedule_cycle(self) -> List[SchedulerMatch]:
        """
        Perform EDRRM scheduling cycle.

        Each iteration:
        1. Request phase: each unmatched input finds preferred output via RR pointer
        2. Grant phase: each output grants one requester via RR pointer,
           with exhaustive service (pointer stays if queue has more packets)
        """
        matches = []
        taken_src: Set[int] = set()
        taken_dst: Set[int] = set()

        for _ in range(self.max_iterations):
            requests = self._request_phase(taken_src, taken_dst)
            iter_matches = self._grant_phase(requests, taken_src, taken_dst)
            matches.extend(iter_matches)
            if len(taken_src) >= self.num_ports:
                break

        if matches:
            self.cycles_with_scheduling += 1
        return matches

    def _request_phase(self, taken_src: Set[int], taken_dst: Set[int]) -> Dict[int, int]:
        """
        Request phase: each input scans from its RR pointer to find
        the first non-empty, non-taken VOQ destination.

        Returns:
            Dict mapping input_port -> requested output_port
        """
        requests: Dict[int, int] = {}
        for p_src in range(self.num_ports):
            if p_src in taken_src:
                continue
            for offset in range(self.num_ports):
                p_dst = (self.rr_index_in[p_src] + offset) % self.num_ports
                if p_dst not in taken_dst and \
                   self.voq_buffer.get_queue_length(p_src, p_dst) > 0:
                    requests[p_src] = p_dst
                    break
        return requests

    def _grant_phase(self, requests: Dict[int, int],
                     taken_src: Set[int], taken_dst: Set[int]) -> List[SchedulerMatch]:
        """
        Grant phase with exhaustive service.

        Each output grants one requesting input using its RR pointer.
        After granting, if the VOQ queue depth > 1 (still has packets
        after the upcoming dequeue), the input pointer is kept at the
        current destination to continue serving the same queue next cycle.
        """
        matches = []

        # Invert requests: dst -> list of requesting srcs
        dst_requesters: Dict[int, List[int]] = {}
        for p_src, p_dst in requests.items():
            dst_requesters.setdefault(p_dst, []).append(p_src)

        for p_dst in range(self.num_ports):
            if p_dst not in dst_requesters:
                continue
            requesters = dst_requesters[p_dst]

            # Scan from output RR pointer to find the first requester
            granted_src = None
            for offset in range(self.num_ports):
                candidate = (self.rr_index_out[p_dst] + offset) % self.num_ports
                if candidate in requesters:
                    granted_src = candidate
                    break

            if granted_src is None:
                continue

            matches.append(SchedulerMatch(granted_src, p_dst))
            taken_src.add(granted_src)
            taken_dst.add(p_dst)

            # --- Exhaustive service logic ---
            # Queue depth is checked BEFORE dequeue (dequeue happens in process_matches).
            # If depth > 1, the queue will still have packets after dequeue,
            # so lock the input pointer to keep serving this destination.
            queue_len = self.voq_buffer.get_queue_length(granted_src, p_dst)
            if queue_len > 1:
                self.rr_index_in[granted_src] = p_dst
            else:
                self.rr_index_in[granted_src] = (p_dst + 1) % self.num_ports

            # Output pointer always advances past the granted input
            self.rr_index_out[p_dst] = (granted_src + 1) % self.num_ports

        return matches


def create_scheduler(config: SwitchConfig, voq_buffer: VOQBuffer) -> BaseScheduler:
    """
    Create scheduler instance based on configuration.
    
    Args:
        config: Switch configuration
        voq_buffer: VOQ buffer instance
        
    Returns:
        BaseScheduler subclass instance
    """
    if config.scheduler_type == SchedulerType.RoundRobin:
        return RoundRobinScheduler(config, voq_buffer)
    elif config.scheduler_type == SchedulerType.iSLIP:
        return iSLIPScheduler(config, voq_buffer)
    elif config.scheduler_type == SchedulerType.EDRRM:
        return EDRRMScheduler(config, voq_buffer)
    else:
        raise ValueError(f"Unsupported scheduler type: {config.scheduler_type}")
