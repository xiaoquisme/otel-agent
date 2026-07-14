"""Tests for circuit breaker and session cache."""
from otel_agent.circuit_breaker import CircuitBreaker, CircuitState
from otel_agent.session_cache import SessionCache


class TestCircuitBreaker:
    def test_new_provider_is_available(self):
        cb = CircuitBreaker()
        assert cb.is_available("openai")

    def test_recording_success_resets(self):
        cb = CircuitBreaker()
        cb.record_failure("openai")
        cb.record_success("openai")
        assert cb.get_state("openai") == CircuitState.CLOSED

    def test_consecutive_failures_trip_circuit(self):
        cb = CircuitBreaker(threshold=3)
        for _ in range(3):
            cb.record_failure("openai")
        assert cb.get_state("openai") == CircuitState.OPEN
        assert not cb.is_available("openai")

    def test_half_open_after_cooldown(self):
        cb = CircuitBreaker(threshold=2, cooldown=0.01)  # 10ms cooldown
        cb.record_failure("openai")
        cb.record_failure("openai")
        assert cb.get_state("openai") == CircuitState.OPEN

        import time
        time.sleep(0.02)  # Wait for cooldown

        assert cb.is_available("openai")
        assert cb.get_state("openai") == CircuitState.HALF_OPEN

    def test_probe_success_closes_circuit(self):
        cb = CircuitBreaker(threshold=2, cooldown=0.01)
        cb.record_failure("openai")
        cb.record_failure("openai")

        import time
        time.sleep(0.02)

        cb.is_available("openai")  # Transitions to HALF_OPEN
        cb.record_success("openai")
        assert cb.get_state("openai") == CircuitState.CLOSED

    def test_probe_failure_reopens_circuit(self):
        cb = CircuitBreaker(threshold=2, cooldown=0.01)
        cb.record_failure("openai")
        cb.record_failure("openai")

        import time
        time.sleep(0.02)

        cb.is_available("openai")  # Transitions to HALF_OPEN
        cb.record_failure("openai")
        assert cb.get_state("openai") == CircuitState.OPEN

    def test_independent_providers(self):
        cb = CircuitBreaker(threshold=2)
        cb.record_failure("openai")
        cb.record_failure("openai")
        assert cb.get_state("openai") == CircuitState.OPEN
        assert cb.get_state("anthropic") == CircuitState.CLOSED

    def test_get_all_states(self):
        cb = CircuitBreaker(threshold=2)
        cb.record_failure("openai")
        states = cb.get_all_states()
        assert "openai" in states


class TestSessionCache:
    def test_get_returns_none_for_missing(self):
        cache = SessionCache()
        result = cache.get("session-1", [{"role": "user", "content": "hi"}])
        assert result is None

    def test_set_and_get(self):
        cache = SessionCache()
        msgs = [{"role": "user", "content": "hi"}]
        cache.set("session-1", msgs, "openai", "simple")
        result = cache.get("session-1", msgs)
        assert result is not None
        assert result.provider_name == "openai"
        assert result.tier == "simple"

    def test_different_sessions_independent(self):
        cache = SessionCache()
        msgs = [{"role": "user", "content": "hi"}]
        cache.set("session-1", msgs, "openai", "simple")
        cache.set("session-2", msgs, "anthropic", "complex")
        assert cache.get("session-1", msgs).provider_name == "openai"
        assert cache.get("session-2", msgs).provider_name == "anthropic"

    def test_ttl_expires(self):
        cache = SessionCache(ttl_minutes=0.001)  # ~0.06 seconds
        msgs = [{"role": "user", "content": "hi"}]
        cache.set("session-1", msgs, "openai", "simple")

        import time
        time.sleep(0.1)

        result = cache.get("session-1", msgs)
        assert result is None

    def test_hash_based_key(self):
        cache = SessionCache()
        msgs = [{"role": "user", "content": "unique message"}]
        cache.set(None, msgs, "openai", "simple")
        result = cache.get(None, msgs)
        assert result is not None

    def test_different_messages_different_keys(self):
        cache = SessionCache()
        msgs1 = [{"role": "user", "content": "message one"}]
        msgs2 = [{"role": "user", "content": "message two"}]
        cache.set(None, msgs1, "openai", "simple")
        cache.set(None, msgs2, "anthropic", "complex")
        assert cache.get(None, msgs1).provider_name == "openai"
        assert cache.get(None, msgs2).provider_name == "anthropic"

    def test_record_failure(self):
        cache = SessionCache()
        msgs = [{"role": "user", "content": "hi"}]
        cache.set("s1", msgs, "openai", "simple")
        count = cache.record_failure("s1", msgs)
        assert count == 1
        count = cache.record_failure("s1", msgs)
        assert count == 2

    def test_clear(self):
        cache = SessionCache()
        msgs = [{"role": "user", "content": "hi"}]
        cache.set("s1", msgs, "openai", "simple")
        cache.clear()
        assert cache.get("s1", msgs) is None

    def test_cleanup(self):
        cache = SessionCache(ttl_minutes=0.001)
        msgs = [{"role": "user", "content": "hi"}]
        cache.set("s1", msgs, "openai", "simple")

        import time
        time.sleep(0.1)

        removed = cache.cleanup()
        assert removed == 1
