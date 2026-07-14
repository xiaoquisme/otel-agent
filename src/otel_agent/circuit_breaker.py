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
    last_probe_time: float = 0.0

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
        """Check if a request should be allowed through.

        Returns True if:
        - Circuit is CLOSED (normal operation)
        - Circuit is HALF_OPEN (probe request allowed)
        - Circuit is OPEN but cooldown has elapsed (transition to HALF_OPEN)
        """
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.HALF_OPEN:
            return True
        # OPEN — check cooldown
        elapsed = time.monotonic() - self.last_failure_time
        if elapsed >= cooldown:
            self.state = CircuitState.HALF_OPEN
            self.last_probe_time = time.monotonic()
            return True
        return False

    def record_probe_result(self, success: bool, threshold: int) -> None:
        """Record the result of a half-open probe."""
        if success:
            self.state = CircuitState.CLOSED
            self.consecutive_failures = 0
        else:
            self.state = CircuitState.OPEN
            self.consecutive_failures += 1
            self.last_failure_time = time.monotonic()


@dataclass
class CircuitBreaker:
    """Tracks circuit breaker state for all providers.

    Default threshold: 5 consecutive failures
    Default cooldown: 60 seconds
    """
    threshold: int = 5
    cooldown: float = 60.0
    circuits: dict[str, ProviderCircuit] = field(default_factory=dict)

    def _get_circuit(self, provider_name: str) -> ProviderCircuit:
        if provider_name not in self.circuits:
            self.circuits[provider_name] = ProviderCircuit()
        return self.circuits[provider_name]

    def is_available(self, provider_name: str) -> bool:
        """Check if a provider is available (not circuit-broken)."""
        circuit = self._get_circuit(provider_name)
        return circuit.should_allow_request(self.cooldown)

    def record_success(self, provider_name: str) -> None:
        """Record a successful request to a provider."""
        circuit = self._get_circuit(provider_name)
        circuit.record_success()

    def record_failure(self, provider_name: str) -> None:
        """Record a failed request to a provider."""
        circuit = self._get_circuit(provider_name)
        circuit.record_failure(self.threshold)

    def get_state(self, provider_name: str) -> CircuitState:
        """Get the current circuit state for a provider."""
        circuit = self._get_circuit(provider_name)
        # Check if OPEN should transition to HALF_OPEN
        if circuit.state == CircuitState.OPEN:
            circuit.should_allow_request(self.cooldown)
        return circuit.state

    def get_all_states(self) -> dict[str, str]:
        """Get circuit states for all tracked providers."""
        return {name: self.get_state(name).value for name in self.circuits}
