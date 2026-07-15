"""Tests for the auto-router with Thompson Sampling."""
import random
from otel_agent.auto_router import AutoRouter, ProviderScore
from otel_agent.config import Provider


def _provider(name: str, cost_in: float = 0.01, cost_out: float = 0.03, tiers: list | None = None) -> Provider:
    return Provider(
        name=name,
        base_url=f"https://{name}.api/v1",
        api_key=f"key-{name}",
        api_format="openai",
        cost_per_1k_input=cost_in,
        cost_per_1k_output=cost_out,
        tiers=tiers or ["simple", "medium", "complex", "reasoning"],
    )


class TestProviderScore:
    def test_initial_state(self):
        score = ProviderScore()
        assert score.successes == 1.0
        assert score.failures == 1.0

    def test_sample_returns_float(self):
        score = ProviderScore()
        result = score.sample()
        assert 0.0 <= result <= 1.0

    def test_record_success(self):
        score = ProviderScore()
        score.record_success()
        assert score.successes == 2.0

    def test_record_failure(self):
        score = ProviderScore()
        score.record_failure()
        assert score.failures == 2.0


class TestAutoRouter:
    def test_select_provider_returns_one(self):
        router = AutoRouter()
        providers = [_provider("openai"), _provider("anthropic")]
        result = router.select_provider("simple", providers)
        assert result is not None
        assert result.name in ("openai", "anthropic")

    def test_select_provider_empty_returns_none(self):
        router = AutoRouter()
        result = router.select_provider("simple", [])
        assert result is None

    def test_seed_from_costs_cheaper_provider_advantaged(self):
        router = AutoRouter()
        cheap = _provider("cheap", cost_in=0.001, cost_out=0.003)
        expensive = _provider("expensive", cost_in=0.01, cost_out=0.03)
        router.seed_from_costs("simple", [cheap, expensive])

        # Run 100 selections — cheap should win more often
        wins = {"cheap": 0, "expensive": 0}
        for _ in range(100):
            result = router.select_provider("simple", [cheap, expensive])
            if result:
                wins[result.name] += 1

        # Cheap should win significantly more (but not 100% due to exploration)
        assert wins["cheap"] > wins["expensive"]

    def test_record_outcome_updates_scores(self):
        router = AutoRouter()
        p = _provider("test")
        router.record_outcome("test", "simple", success=True)
        stats = router.get_provider_stats("simple")
        assert "test" in stats
        assert stats["test"]["successes"] == 2.0  # 1 prior + 1 success

    def test_record_failure_updates_scores(self):
        router = AutoRouter()
        p = _provider("test")
        router.record_outcome("test", "simple", success=False)
        stats = router.get_provider_stats("simple")
        assert "test" in stats
        assert stats["test"]["failures"] == 2.0  # 1 prior + 1 failure

    def test_successful_provider_gets_selected_more(self):
        router = AutoRouter()
        good = _provider("good")
        bad = _provider("bad")

        # Train: good always succeeds, bad always fails
        for _ in range(50):
            router.record_outcome("good", "medium", success=True)
            router.record_outcome("bad", "medium", success=False)

        # Now select — good should win almost every time
        wins = {"good": 0, "bad": 0}
        for _ in range(100):
            result = router.select_provider("medium", [good, bad])
            if result:
                wins[result.name] += 1

        assert wins["good"] > 90  # Should dominate

    def test_get_provider_stats_empty(self):
        router = AutoRouter()
        stats = router.get_provider_stats("nonexistent")
        assert stats == {}
