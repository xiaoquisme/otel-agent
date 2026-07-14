"""Auto-router with Thompson Sampling for cost-optimized provider selection.

Selects the best provider within a complexity tier using Bayesian bandit
algorithms (Thompson Sampling) to balance exploration vs exploitation.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from otel_agent.config import Provider


@dataclass
class ProviderScore:
    """Beta distribution parameters for Thompson Sampling."""
    successes: float = 1.0  # Start with 1 to avoid 0/0
    failures: float = 1.0

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
    scores: dict[str, dict[str, ProviderScore]] = field(default_factory=dict)

    def _get_or_create_score(self, tier: str, provider_name: str) -> ProviderScore:
        """Get or create a score entry for a provider in a tier."""
        if tier not in self.scores:
            self.scores[tier] = {}
        if provider_name not in self.scores[tier]:
            self.scores[tier][provider_name] = ProviderScore()
        return self.scores[tier][provider_name]

    def seed_from_costs(self, tier: str, providers: list[Provider]) -> None:
        """Seed initial scores based on relative cost.

        Cheaper providers start with higher success priors, giving them
        an advantage in early exploration while still allowing Thompson
        Sampling to correct if they perform poorly.
        """
        if not providers:
            return

        # Calculate average cost for this tier
        costs = []
        for p in providers:
            avg_cost = (p.cost_per_1k_input + p.cost_per_1k_output) / 2
            if avg_cost > 0:
                costs.append((p.name, avg_cost))

        if not costs:
            return

        avg_cost = sum(c for _, c in costs) / len(costs)

        for name, cost in costs:
            score = self._get_or_create_score(tier, name)
            # Cheaper providers get more initial successes
            # cost_ratio: how much cheaper than average (0.5 = half price, 2.0 = double)
            cost_ratio = cost / avg_cost if avg_cost > 0 else 1.0
            # Map cost ratio to success bonus: cheaper = more successes
            # A provider at half the average cost gets +2 success prior
            bonus = max(0, (1.0 - cost_ratio) * 4)
            score.successes += bonus

    def select_provider(
        self,
        tier: str,
        available: list[Provider],
    ) -> Provider | None:
        """Select the best provider for a tier using Thompson Sampling.

        Args:
            tier: The complexity tier (simple, medium, complex, reasoning)
            available: Providers that support this tier and are available

        Returns:
            The selected provider, or None if no providers are available.
        """
        if not available:
            return None

        # Ensure all providers have scores
        for p in available:
            self._get_or_create_score(tier, p.name)

        # Sample from each provider's Beta distribution
        samples = []
        for p in available:
            score = self.scores[tier][p.name]
            sample_value = score.sample()
            samples.append((sample_value, p))

        # Select the provider with the highest sample
        samples.sort(key=lambda x: x[0], reverse=True)
        return samples[0][1]

    def record_outcome(
        self,
        provider_name: str,
        tier: str,
        success: bool,
    ) -> None:
        """Record the outcome of a routing decision.

        Args:
            provider_name: The provider that was used
            tier: The complexity tier
            success: Whether the request succeeded
        """
        score = self._get_or_create_score(tier, provider_name)
        if success:
            score.record_success()
        else:
            score.record_failure()

    def get_provider_stats(self, tier: str) -> dict[str, dict]:
        """Get statistics for all providers in a tier."""
        if tier not in self.scores:
            return {}
        result = {}
        for name, score in self.scores[tier].items():
            total = score.successes + score.failures
            result[name] = {
                "successes": score.successes,
                "failures": score.failures,
                "mean": score.mean,
                "sample_count": total - 2,  # Subtract prior
            }
        return result
