"""Circuit breaker for provider failure tracking.

Tracks consecutive failures per provider and excludes providers
that exceed the failure threshold. Supports half-open probes
after a cooldown period.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Provider excluded
    HALF_OPEN = "half_open"  # Probing with one request



@dataclass
class ProviderCircuit:
    """Circuit breaker state for a single provider."""
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    last_failure_time: float = 0.0

    def record_success(self) -> None:
        """Record a successful request — reset the circuit."""
        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0

    def record_failure(self, threshold: int) -> None:
        """Record a failed request — potentially trip the circuit."""
        self.consecutive_failures += 1
        self.last_failure_time = time.monotonic()
        if self.consecutive_failures >= threshold:
            self.state = CircuitState.OPEN

    def should_allow_request(self, cooldown: float) -> bool:
        """Check if a request should be allowed through."""
        if self.state in (CircuitState.CLOSED, CircuitState.HALF_OPEN):
            return True
        # OPEN — check cooldown
        elapsed = time.monotonic() - self.last_failure_time
        if elapsed >= cooldown:
            self.state = CircuitState.HALF_OPEN
            return True
        return False


# Module-level default circuit for unknown providers
_CLOSED_CIRCUIT = ProviderCircuit()


@dataclass
class CircuitBreaker:
    """Tracks circuit breaker state for all providers.

    Default threshold: 5 consecutive failures
    Default cooldown: 60 seconds
    """
    threshold: int = 5
    cooldown: float = 60.0
    circuits: dict[str, ProviderCircuit] = field(default_factory=dict)

    def is_available(self, provider_name: str) -> bool:
        """Check if a provider is available (not circuit-broken)."""
        circuit = self.circuits.get(provider_name, _CLOSED_CIRCUIT)
        return circuit.should_allow_request(self.cooldown)

    def record_success(self, provider_name: str) -> None:
        """Record a successful request to a provider."""
        self.circuits.setdefault(provider_name, ProviderCircuit()).record_success()

    def record_failure(self, provider_name: str) -> None:
        """Record a failed request to a provider."""
        self.circuits.setdefault(provider_name, ProviderCircuit()).record_failure(self.threshold)

    def get_state(self, provider_name: str) -> CircuitState:
        """Get the current circuit state for a provider (no side effects)."""
        return self.circuits.get(provider_name, _CLOSED_CIRCUIT).state

    def get_all_states(self) -> dict[str, str]:
        """Get circuit states for all tracked providers."""
        return {name: circuit.state.value for name, circuit in self.circuits.items()}
