"""Tests for the simulation models."""

import pytest
from simulation.models import (
    GuardrailModel,
    SimulationParams,
    SimulationResult,
    SimulationSummary,
)


class TestSimulationParams:
    def test_defaults(self):
        p = SimulationParams()
        assert p.initial_portfolio == 1_000_000.0
        assert p.annual_spending == 40_000.0
        assert p.years == 30
        assert p.num_simulations == 1_000

    def test_withdrawal_rate(self):
        p = SimulationParams(initial_portfolio=1_000_000, annual_spending=40_000)
        assert p.withdrawal_rate() == pytest.approx(0.04)

    def test_withdrawal_rate_zero_portfolio(self):
        p = SimulationParams(initial_portfolio=0, annual_spending=40_000)
        assert p.withdrawal_rate() == 0.0

    def test_guardrail_model_enum(self):
        p = SimulationParams(guardrail_model=GuardrailModel.NOMINAL_FIXED)
        assert p.guardrail_model == GuardrailModel.NOMINAL_FIXED


class TestSimulationResult:
    def _make_result(self, values, spending, success=True, depletion_year=None):
        return SimulationResult(
            path_id=0,
            portfolio_values=values,
            annual_spending=spending,
            success=success,
            depletion_year=depletion_year,
        )

    def test_final_value(self):
        r = self._make_result([1_000_000, 900_000, 850_000], [40_000, 40_000])
        assert r.final_value == 850_000

    def test_peak_value(self):
        r = self._make_result([1_000_000, 1_200_000, 900_000], [40_000, 40_000])
        assert r.peak_value == 1_200_000

    def test_trough_value(self):
        r = self._make_result([1_000_000, 900_000, 800_000], [40_000, 40_000])
        assert r.trough_value == 800_000


class TestSimulationSummary:
    def _make_summary(self):
        params = SimulationParams(
            initial_portfolio=1_000_000,
            annual_spending=40_000,
            years=2,
            num_simulations=4,
        )
        results = [
            SimulationResult(0, [1_000_000, 900_000, 800_000], [40_000, 40_000], True),
            SimulationResult(1, [1_000_000, 800_000, 700_000], [40_000, 40_000], True),
            SimulationResult(2, [1_000_000, 500_000, 0], [40_000, 40_000], False, 2),
            SimulationResult(3, [1_000_000, 400_000, 0], [40_000, 40_000], False, 2),
        ]
        return SimulationSummary(params=params, results=results)

    def test_success_rate(self):
        s = self._make_summary()
        assert s.success_rate == pytest.approx(0.5)

    def test_success_count(self):
        s = self._make_summary()
        assert s.success_count == 2

    def test_failure_count(self):
        s = self._make_summary()
        assert s.failure_count == 2

    def test_median_final_value(self):
        s = self._make_summary()
        finals = [800_000, 700_000, 0, 0]
        import numpy as np
        assert s.median_final_value == pytest.approx(float(np.median(finals)))

    def test_percentile_paths_shape(self):
        s = self._make_summary()
        pct_paths = s.percentile_paths([25, 50, 75])
        assert set(pct_paths.keys()) == {25, 50, 75}
        for vals in pct_paths.values():
            # years + 1 entries (initial + one per year)
            assert len(vals) == s.params.years + 1

    def test_depletion_year_distribution(self):
        s = self._make_summary()
        dist = s.depletion_year_distribution()
        assert dist == {2: 2}

    def test_empty_results_success_rate(self):
        params = SimulationParams()
        s = SimulationSummary(params=params, results=[])
        assert s.success_rate == 0.0
