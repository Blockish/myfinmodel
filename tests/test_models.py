"""Unit tests for simulation.models (Phase 1)."""

from __future__ import annotations

import numpy as np
import pytest

from simulation.models import (
    GuardrailGR1Config,
    GuardrailGR2Config,
    GuardrailGR3Config,
    GuardrailGR4Config,
    HealthInsuranceConfig,
    SimulationInputs,
    SimulationResults,
    SpendingTier,
)


class TestSpendingTier:
    """Tests for SpendingTier dataclass."""

    def test_create_tier(self):
        """Create a valid spending tier."""
        tier = SpendingTier(start_age=65, end_age=75, annual_spend=50_000.0)
        assert tier.start_age == 65
        assert tier.end_age == 75
        assert tier.annual_spend == 50_000.0

    def test_tier_ranges(self):
        """Test various tier ranges."""
        tier1 = SpendingTier(start_age=65, end_age=74, annual_spend=60_000.0)
        tier2 = SpendingTier(start_age=75, end_age=99, annual_spend=40_000.0)
        assert tier1.end_age < tier2.start_age or tier1.end_age + 1 == tier2.start_age


class TestGuardrailConfigs:
    """Tests for guardrail configuration dataclasses."""

    def test_gr1_defaults(self):
        """GR1 has sensible defaults."""
        gr1 = GuardrailGR1Config()
        assert gr1.enabled is True
        assert gr1.floor_pct == 0.50
        assert gr1.ceil_pct == 1.50
        assert gr1.cut_pct == 0.10
        assert gr1.raise_pct == 0.10

    def test_gr2_defaults(self):
        """GR2 thresholds are ordered."""
        gr2 = GuardrailGR2Config()
        assert gr2.enabled is True
        assert gr2.low_rate < gr2.warn_rate < gr2.crit_rate
        assert 0.03 == gr2.low_rate
        assert 0.05 == gr2.warn_rate
        assert 0.065 == gr2.crit_rate

    def test_gr3_defaults(self):
        """GR3 has minimal config."""
        gr3 = GuardrailGR3Config()
        assert gr3.enabled is True

    def test_gr4_defaults(self):
        """GR4 has inflation trigger."""
        gr4 = GuardrailGR4Config()
        assert gr4.enabled is True
        assert gr4.inf_trigger == 0.045


class TestHealthInsuranceConfig:
    """Tests for HealthInsuranceConfig."""

    def test_defaults(self):
        """Medicare and ACA defaults are reasonable."""
        health = HealthInsuranceConfig()
        assert health.medicare_age == 65
        assert health.medicare_premium == 3_600.0
        assert health.aca_guardrail_enabled is True
        assert health.aca_magi_cliff == 62_000.0

    def test_custom_values(self):
        """Can override defaults."""
        health = HealthInsuranceConfig(
            medicare_age=67,
            medicare_premium=5_000.0,
            aca_magi_cliff=80_000.0,
        )
        assert health.medicare_age == 67
        assert health.medicare_premium == 5_000.0
        assert health.aca_magi_cliff == 80_000.0


class TestSimulationInputs:
    """Tests for SimulationInputs dataclass."""

    def test_minimal_inputs(self):
        """Create inputs with only required field."""
        inputs = SimulationInputs(port_start=1_000_000.0)
        assert inputs.port_start == 1_000_000.0
        assert inputs.retire_age == 65
        assert inputs.n_paths == 1_000
        assert inputs.plan_years == 35

    def test_portfolio_breakdown(self):
        """Portfolio can be split by account type."""
        inputs = SimulationInputs(
            port_start=1_000_000.0,
            taxable_value=300_000.0,
            tax_deferred_value=500_000.0,
            roth_value=200_000.0,
        )
        total = inputs.taxable_value + inputs.tax_deferred_value + inputs.roth_value
        assert total == 1_000_000.0

    def test_tax_rates(self):
        """Tax rates default to reasonable values."""
        inputs = SimulationInputs(port_start=1_000_000.0)
        assert inputs.ltcg_rate == 0.15
        assert inputs.ord_income_rate == 0.22

    def test_spending_tiers(self):
        """Can specify multiple spending tiers."""
        tiers = [
            SpendingTier(start_age=65, end_age=74, annual_spend=60_000.0),
            SpendingTier(start_age=75, end_age=99, annual_spend=40_000.0),
        ]
        inputs = SimulationInputs(port_start=1_000_000.0, spending_tiers=tiers)
        assert len(inputs.spending_tiers) == 2
        assert inputs.spending_tiers[0].annual_spend == 60_000.0

    def test_social_security(self):
        """Social Security parameters have defaults."""
        inputs = SimulationInputs(port_start=1_000_000.0)
        assert inputs.ss_enabled is True
        assert inputs.ss_annual == 24_000.0
        assert inputs.ss_cola == 0.025
        assert inputs.ss_start_age == 67

    def test_market_assumptions(self):
        """Market assumptions default to spec values."""
        inputs = SimulationInputs(port_start=1_000_000.0)
        assert inputs.ret_mean == 0.065
        assert inputs.ret_std == 0.12
        assert inputs.inf_mean == 0.03
        assert inputs.inf_std == 0.015
        assert inputs.ret_inf_corr == 0.10
        assert inputs.inf_floor == 0.01

    def test_guardrail_configs_nested(self):
        """Guardrail configs are nested and independently configurable."""
        inputs = SimulationInputs(port_start=1_000_000.0)
        assert isinstance(inputs.gr1, GuardrailGR1Config)
        assert isinstance(inputs.gr2, GuardrailGR2Config)
        assert isinstance(inputs.gr3, GuardrailGR3Config)
        assert isinstance(inputs.gr4, GuardrailGR4Config)

    def test_mutable_mutation(self):
        """Dataclass is mutable (intentional for scenario editing)."""
        inputs = SimulationInputs(port_start=1_000_000.0)
        inputs.n_paths = 2_000
        assert inputs.n_paths == 2_000

    def test_tier_mutation(self):
        """Spending tiers list can be modified."""
        inputs = SimulationInputs(port_start=1_000_000.0)
        tier = SpendingTier(start_age=65, end_age=80, annual_spend=50_000.0)
        inputs.spending_tiers.append(tier)
        assert len(inputs.spending_tiers) == 1


class TestSimulationResults:
    """Tests for SimulationResults dataclass."""

    def test_create_results(self):
        """Create SimulationResults with minimal arrays."""
        inputs = SimulationInputs(port_start=1_000_000.0, n_paths=100, plan_years=30)
        n_paths, plan_years = 100, 30

        results = SimulationResults(
            portfolio=np.random.randn(n_paths, plan_years),
            real_portfolio=np.random.randn(n_paths, plan_years),
            spend=np.random.randn(n_paths, plan_years),
            real_spend=np.random.randn(n_paths, plan_years),
            gross_wd=np.random.randn(n_paths, plan_years),
            net_wd=np.random.randn(n_paths, plan_years),
            wr=np.random.randn(n_paths, plan_years),
            cum_inf=np.random.randn(n_paths, plan_years),
            ss_income=np.random.randn(n_paths, plan_years),
            health_cost=np.random.randn(n_paths, plan_years),
            events=np.full((n_paths, plan_years), "", dtype=object),
            ret_draws=np.random.randn(n_paths, plan_years),
            inf_draws=np.random.randn(n_paths, plan_years),
            ages=list(range(65, 95)),
            n_paths=n_paths,
            plan_years=plan_years,
            inputs=inputs,
        )

        assert results.n_paths == 100
        assert results.plan_years == 30
        assert results.portfolio.shape == (100, 30)

    def test_success_rate(self):
        """Success rate calculation."""
        inputs = SimulationInputs(port_start=1_000_000.0, n_paths=10, plan_years=5)
        portfolio = np.ones((10, 5))
        portfolio[0:3, -1] = 0  # 3 paths deplete
        portfolio[3:, -1] = 100  # 7 paths survive

        results = SimulationResults(
            portfolio=portfolio,
            real_portfolio=np.ones((10, 5)),
            spend=np.ones((10, 5)),
            real_spend=np.ones((10, 5)),
            gross_wd=np.ones((10, 5)),
            net_wd=np.ones((10, 5)),
            wr=np.ones((10, 5)),
            cum_inf=np.ones((10, 5)),
            ss_income=np.ones((10, 5)),
            health_cost=np.ones((10, 5)),
            events=np.full((10, 5), "", dtype=object),
            ret_draws=np.ones((10, 5)),
            inf_draws=np.ones((10, 5)),
            ages=list(range(65, 70)),
            n_paths=10,
            plan_years=5,
            inputs=inputs,
        )

        assert results.success_rate() == 0.7
        assert results.success_count() == 7
        assert results.failure_count() == 3

    def test_median_final_value(self):
        """Median final portfolio value."""
        inputs = SimulationInputs(port_start=1_000_000.0, n_paths=5, plan_years=2)
        portfolio = np.array([
            [100, 110],
            [100, 120],
            [100, 130],
            [100, 140],
            [100, 150],
        ])

        results = SimulationResults(
            portfolio=portfolio,
            real_portfolio=np.ones((5, 2)),
            spend=np.ones((5, 2)),
            real_spend=np.ones((5, 2)),
            gross_wd=np.ones((5, 2)),
            net_wd=np.ones((5, 2)),
            wr=np.ones((5, 2)),
            cum_inf=np.ones((5, 2)),
            ss_income=np.ones((5, 2)),
            health_cost=np.ones((5, 2)),
            events=np.full((5, 2), "", dtype=object),
            ret_draws=np.ones((5, 2)),
            inf_draws=np.ones((5, 2)),
            ages=[65, 66],
            n_paths=5,
            plan_years=2,
            inputs=inputs,
        )

        assert results.median_final_value() == 130

    def test_percentile_paths(self):
        """Percentile calculation across paths."""
        inputs = SimulationInputs(port_start=1_000_000.0, n_paths=5, plan_years=2)
        portfolio = np.array([
            [100, 110],
            [100, 120],
            [100, 130],
            [100, 140],
            [100, 150],
        ])

        results = SimulationResults(
            portfolio=portfolio,
            real_portfolio=np.ones((5, 2)),
            spend=np.ones((5, 2)),
            real_spend=np.ones((5, 2)),
            gross_wd=np.ones((5, 2)),
            net_wd=np.ones((5, 2)),
            wr=np.ones((5, 2)),
            cum_inf=np.ones((5, 2)),
            ss_income=np.ones((5, 2)),
            health_cost=np.ones((5, 2)),
            events=np.full((5, 2), "", dtype=object),
            ret_draws=np.ones((5, 2)),
            inf_draws=np.ones((5, 2)),
            ages=[65, 66],
            n_paths=5,
            plan_years=2,
            inputs=inputs,
        )

        percentiles = results.percentile_paths([25, 50, 75])
        assert 25 in percentiles
        assert 50 in percentiles
        assert 75 in percentiles
        assert len(percentiles[50]) == 2
