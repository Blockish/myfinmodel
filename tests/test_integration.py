"""End-to-end integration tests for the Monte Carlo retirement planner.

Exercises the full pipeline: SimulationInputs → validate_inputs() →
run_simulation() → SimulationResults, verifying spec §7 edge cases
and cross-module contracts.
"""

from __future__ import annotations

import numpy as np

from simulation.engine import run_simulation
from simulation.models import (
    GuardrailGR1Config,
    GuardrailGR2Config,
    GuardrailGR3Config,
    GuardrailGR4Config,
    SimulationInputs,
    SimulationResults,
    SpendingTier,
)
from validation.validators import validate_inputs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_inputs(**overrides) -> SimulationInputs:
    """Build minimal valid inputs for integration testing."""
    defaults = dict(
        port_start=1_000_000.0,
        taxable_value=1_000_000.0,
        tax_deferred_value=0.0,
        roth_value=0.0,
        unrealized_gain_pct=0.30,
        ltcg_rate=0.15,
        ord_income_rate=0.22,
        current_age=65,
        retire_age=65,
        ss_start_age=67,
        plan_years=35,
        filing_status="Single",
        spending_tiers=[
            SpendingTier(start_age=65, end_age=99, annual_spend=50_000.0),
        ],
        spend_floor=20_000.0,
        spend_ceiling=100_000.0,
        ss_enabled=True,
        ss_annual=24_000.0,
        ss_cola=0.025,
        ret_mean=0.065,
        ret_std=0.12,
        ret_inf_corr=0.10,
        inf_mean=0.03,
        inf_std=0.015,
        inf_floor=0.01,
        n_paths=200,
        random_seed=42,
    )
    defaults.update(overrides)
    return SimulationInputs(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEndToEnd:
    """Full pipeline integration tests."""

    def test_e2e_default_inputs_run(self):
        """Default inputs validate and produce a well-formed SimulationResults."""
        inputs = _default_inputs()
        vr = validate_inputs(inputs)
        assert vr.valid, f"Unexpected validation errors: {vr.errors}"

        results = run_simulation(inputs)
        assert isinstance(results, SimulationResults)
        assert results.portfolio.shape == (200, 35)
        assert results.n_paths == 200
        assert results.plan_years == 35
        assert 0.0 <= results.success_rate() <= 1.0

    def test_e2e_all_paths_survive(self):
        """Spec §7.4: Large portfolio guarantees 100% survival."""
        inputs = _default_inputs(
            port_start=50_000_000.0,
            taxable_value=50_000_000.0,
            spending_tiers=[SpendingTier(65, 74, 30_000.0)],
            n_paths=200,
            plan_years=10,
        )
        vr = validate_inputs(inputs)
        assert vr.valid

        results = run_simulation(inputs)
        assert results.success_rate() == 1.0
        assert np.all(results.portfolio[:, -1] > 0)

    def test_e2e_all_paths_deplete(self):
        """Spec §7.5: Tiny portfolio + high spending → 0% survival."""
        inputs = _default_inputs(
            port_start=1_000.0,
            taxable_value=1_000.0,
            spending_tiers=[SpendingTier(65, 74, 500_000.0)],
            spend_floor=0.0,
            spend_ceiling=1_000_000.0,
            n_paths=200,
            plan_years=10,
        )
        vr = validate_inputs(inputs)
        assert vr.valid

        results = run_simulation(inputs)
        assert results.success_rate() == 0.0
        assert np.all(results.portfolio[:, -1] == 0)

    def test_e2e_ss_disabled(self):
        """Spec §7.3: SS disabled → ss_income is zero everywhere."""
        inputs = _default_inputs(
            ss_enabled=False, n_paths=100, plan_years=10,
            spending_tiers=[SpendingTier(65, 74, 50_000.0)],
        )
        vr = validate_inputs(inputs)
        assert vr.valid

        results = run_simulation(inputs)
        assert np.all(results.ss_income == 0)

    def test_e2e_all_guardrails_disabled(self):
        """All guardrails disabled → only NONE events emitted."""
        inputs = _default_inputs(
            n_paths=100,
            plan_years=10,
            spending_tiers=[SpendingTier(65, 74, 50_000.0)],
            gr1=GuardrailGR1Config(enabled=False),
            gr2=GuardrailGR2Config(enabled=False),
            gr3=GuardrailGR3Config(enabled=False),
            gr4=GuardrailGR4Config(enabled=False),
        )
        vr = validate_inputs(inputs)
        assert vr.valid

        results = run_simulation(inputs)
        assert np.all(results.events == "NONE")

    def test_e2e_validate_then_run(self):
        """Validate → run → results metadata matches inputs."""
        inputs = _default_inputs(
            n_paths=300, plan_years=20, random_seed=99,
            spending_tiers=[SpendingTier(65, 84, 50_000.0)],
        )
        vr = validate_inputs(inputs)
        assert vr.valid

        results = run_simulation(inputs)
        assert results.n_paths == 300
        assert results.plan_years == 20
        assert results.inputs.random_seed == 99
        assert len(results.ages) == 20
        assert results.ages[0] == inputs.retire_age
