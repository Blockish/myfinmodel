"""Tests for the Monte Carlo simulation engine."""

import pytest
import numpy as np

from simulation.models import GuardrailModel, SimulationParams
from simulation.monte_carlo import MonteCarloSimulator


SEED = 42


class TestMonteCarloSimulator:
    def _params(self, **kwargs) -> SimulationParams:
        defaults = dict(
            initial_portfolio=1_000_000,
            annual_spending=40_000,
            mean_return=0.07,
            return_std=0.12,
            mean_inflation=0.03,
            inflation_std=0.01,
            years=30,
            num_simulations=200,
            random_seed=SEED,
        )
        defaults.update(kwargs)
        return SimulationParams(**defaults)

    def test_run_returns_summary(self):
        sim = MonteCarloSimulator(self._params())
        summary = sim.run()
        assert summary is not None

    def test_correct_number_of_paths(self):
        n = 150
        summary = MonteCarloSimulator(self._params(num_simulations=n)).run()
        assert len(summary.results) == n

    def test_portfolio_values_length(self):
        years = 20
        summary = MonteCarloSimulator(self._params(years=years)).run()
        for result in summary.results:
            # years+1 entries: initial value + one per year
            assert len(result.portfolio_values) == years + 1

    def test_spending_values_length(self):
        years = 20
        summary = MonteCarloSimulator(self._params(years=years)).run()
        for result in summary.results:
            assert len(result.annual_spending) == years

    def test_portfolio_non_negative(self):
        summary = MonteCarloSimulator(self._params()).run()
        for result in summary.results:
            assert all(v >= 0 for v in result.portfolio_values)

    def test_success_rate_bounded(self):
        summary = MonteCarloSimulator(self._params()).run()
        assert 0.0 <= summary.success_rate <= 1.0

    def test_reproducibility_with_seed(self):
        params = self._params(random_seed=SEED)
        s1 = MonteCarloSimulator(params).run()
        s2 = MonteCarloSimulator(params).run()
        assert s1.success_rate == s2.success_rate
        assert s1.results[0].portfolio_values == s2.results[0].portfolio_values

    def test_different_seeds_differ(self):
        s1 = MonteCarloSimulator(self._params(random_seed=1)).run()
        s2 = MonteCarloSimulator(self._params(random_seed=2)).run()
        assert s1.results[0].portfolio_values != s2.results[0].portfolio_values

    def test_certain_success_high_portfolio(self):
        """A very large portfolio with modest spending should always succeed."""
        params = self._params(
            initial_portfolio=100_000_000,
            annual_spending=40_000,
            mean_return=0.07,
            return_std=0.05,
            years=30,
            num_simulations=100,
        )
        summary = MonteCarloSimulator(params).run()
        assert summary.success_rate == pytest.approx(1.0)

    def test_near_certain_failure_tiny_portfolio(self):
        """A tiny portfolio with large spending should almost always fail."""
        params = self._params(
            initial_portfolio=10_000,
            annual_spending=40_000,
            mean_return=0.07,
            return_std=0.12,
            years=30,
            num_simulations=100,
        )
        summary = MonteCarloSimulator(params).run()
        assert summary.success_rate == pytest.approx(0.0)

    def test_depletion_year_set_on_failure(self):
        params = self._params(
            initial_portfolio=10_000,
            annual_spending=40_000,
            years=10,
            num_simulations=50,
        )
        summary = MonteCarloSimulator(params).run()
        for r in summary.results:
            if not r.success:
                assert r.depletion_year is not None
                assert 1 <= r.depletion_year <= params.years

    def test_nominal_fixed_spending_unchanged(self):
        """With NOMINAL_FIXED, all non-depleted paths should spend the same each year."""
        params = self._params(
            guardrail_model=GuardrailModel.NOMINAL_FIXED,
            initial_portfolio=10_000_000,
            annual_spending=40_000,
            years=10,
            num_simulations=10,
        )
        summary = MonteCarloSimulator(params).run()
        for r in summary.results:
            if r.success:
                assert all(
                    abs(s - 40_000) < 1e-6 for s in r.annual_spending
                ), f"Expected fixed 40000 spending, got {r.annual_spending}"

    def test_inflation_adjusted_spending_grows(self):
        """With INFLATION_ADJUSTED, spending in later years should exceed initial."""
        params = self._params(
            guardrail_model=GuardrailModel.INFLATION_ADJUSTED,
            initial_portfolio=10_000_000,
            annual_spending=40_000,
            mean_inflation=0.03,
            inflation_std=0.0,
            years=10,
            num_simulations=5,
        )
        summary = MonteCarloSimulator(params).run()
        for r in summary.results:
            if r.success and len(r.annual_spending) == 10:
                assert r.annual_spending[-1] > r.annual_spending[0]

    def test_guardrails_dynamic_model_runs(self):
        """Dynamic guardrail model should run without errors."""
        params = self._params(
            guardrail_model=GuardrailModel.GUARDRAILS_DYNAMIC,
            years=10,
            num_simulations=50,
        )
        summary = MonteCarloSimulator(params).run()
        assert len(summary.results) == 50

    def test_percentile_paths_all_values_present(self):
        summary = MonteCarloSimulator(self._params(years=10)).run()
        pct = summary.percentile_paths([5, 25, 50, 75, 95])
        assert set(pct.keys()) == {5, 25, 50, 75, 95}
        for vals in pct.values():
            assert len(vals) == 11  # 10 years + initial
