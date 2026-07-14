"""Auto-router with Thompson Sampling for cost-optimized provider selection.

Selects the best provider within a complexity tier using Bayesian bandit
algorithms (Thompson Sampling) to balance exploration vs exploitation.
"""
from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field

from otel_agent.config import Provider


@dataclass
class ProviderScore:
    """Beta distribution parameters for Thompson Sampling."""
    successes: float = 1.0  # Start with 1 to avoid 0/0
    failures: float = 1.0
    seeded: bool = False  # Track whether cost-based seeding has been applied

    def sample(self) -> float:
        """Sample from the Beta distribution."""
        return random.betavariate(self.successes, self.failures)

    def record_success(self) -> None:
        self.successes += 1

    def record_failure(self) -> None:
        self.failures += 1

    @property
    def mean(self) -> float:
        return self.successes / (self.successes + self.failures)


@dataclass
class AutoRouter:
    """Selects providers using Thompson Sampling within tiers.

    Maintains per-tier, per-provider scores. Cheaper providers start with
    a higher prior success rate based on their cost relative to the tier average.
    """

    # tier -> provider_name -> ProviderScore
    scores: dict[str, dict[str, ProviderScore]] = field(
        default_factory=lambda: defaultdict(dict)
    )

    def seed_from_costs(self, tier: str, providers: list[Provider]) -> None:
        """Seed initial scores based on relative cost (only once per provider)."""
        if not providers:
            return

        costs = []
        for p in providers:
            avg_cost = (p.cost_per_1k_input + p.cost_per_1k_output) / 2
            if avg_cost > 0:
                costs.append((p.name, avg_cost))

        if not costs:
            return

        avg_cost = sum(c for _, c in costs) / len(costs)

        for name, cost in costs:
            score = self.scores[tier].setdefault(name, ProviderScore())
            if score.seeded:
                continue  # Already seeded — skip
            score.seeded = True
            cost_ratio = cost / avg_cost if avg_cost > 0 else 1.0
            bonus = max(0, (1.0 - cost_ratio) * 4)
            score.successes += bonus

    def select_provider(
        self,
        tier: str,
        available: list[Provider],
    ) -> Provider | None:
        """Select the best provider for a tier using Thompson Sampling."""
        if not available:
            return None

        # Ensure all providers have scores
        for p in available:
            self.scores[tier].setdefault(p.name, ProviderScore())

        # Sample from each provider's Beta distribution
        samples = [
            (self.scores[tier][p.name].sample(), p)
            for p in available
        ]

        # Select the provider with the highest sample
        samples.sort(key=lambda x: x[0], reverse=True)
        return samples[0][1]

    def record_outcome(
        self,
        provider_name: str,
        tier: str,
        success: bool,
    ) -> None:
        """Record the outcome of a routing decision."""
        score = self.scores[tier].setdefault(provider_name, ProviderScore())
        if success:
            score.record_success()
        else:
            score.record_failure()

    def get_provider_stats(self, tier: str) -> dict[str, dict]:
        """Get statistics for all providers in a tier."""
        if tier not in self.scores:
            return {}
        return {
            name: {
                "successes": score.successes,
                "failures": score.failures,
                "mean": score.mean,
                "sample_count": score.successes + score.failures - 2,
            }
            for name, score in self.scores[tier].items()
        }
