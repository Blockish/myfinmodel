"""Unit tests for simulation.engine (Phase 2).

Tests the full vectorized Monte Carlo engine against spec §3.1–3.7,
covering determinism, result structure, bivariate draws, guardrail
integration, tax gross-up, ruin-state handling, and performance.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from simulation.engine import run_simulation
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _simple_inputs(**overrides) -> SimulationInputs:
    """Build a minimal valid SimulationInputs for testing.

    Defaults:
    - 1M portfolio, 100% taxable, 65→99, single tier 50k, SS 24k at 67
    - All guardrails enabled at spec defaults
    - 200 paths, seed 42
    """
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
# Result Structure
# ---------------------------------------------------------------------------


class TestResultStructure:
    """Verify engine returns correctly shaped SimulationResults."""

    def test_returns_simulation_results(self):
        inputs = _simple_inputs(n_paths=100, plan_years=10)
        result = run_simulation(inputs)
        assert isinstance(result, SimulationResults)

    def test_array_shapes(self):
        n, T = 100, 10
        inputs = _simple_inputs(n_paths=n, plan_years=T)
        r = run_simulation(inputs)

        for name in (
            "portfolio", "real_portfolio", "spend", "real_spend",
            "gross_wd", "net_wd", "wr", "cum_inf", "ss_income",
            "health_cost", "events", "ret_draws", "inf_draws",
        ):
            arr = getattr(r, name)
            assert arr.shape == (n, T), f"{name} shape mismatch: {arr.shape}"

    def test_metadata(self):
        inputs = _simple_inputs(n_paths=100, plan_years=10)
        r = run_simulation(inputs)

        assert r.n_paths == 100
        assert r.plan_years == 10
        assert r.ages == list(range(65, 75))
        assert isinstance(r.inputs, SimulationInputs)

    def test_events_dtype(self):
        r = run_simulation(_simple_inputs(n_paths=100, plan_years=5))
        assert r.events.dtype == object
        valid_codes = {"NONE", "PV-DOWN", "PV-UP", "WR-WARN", "WR-CRIT",
                       "WR-LOW", "ACA-BREACH", "INF"}
        unique_events = set(r.events.flat)
        assert unique_events.issubset(valid_codes)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Same seed + inputs must produce identical results."""

    def test_same_seed_same_results(self):
        inputs = _simple_inputs(n_paths=200, plan_years=10, random_seed=99)
        r1 = run_simulation(inputs)
        r2 = run_simulation(inputs)

        np.testing.assert_array_equal(r1.portfolio, r2.portfolio)
        np.testing.assert_array_equal(r1.spend, r2.spend)
        np.testing.assert_array_equal(r1.ret_draws, r2.ret_draws)
        np.testing.assert_array_equal(r1.inf_draws, r2.inf_draws)
        np.testing.assert_array_equal(r1.events, r2.events)

    def test_different_seed_different_results(self):
        base = dict(n_paths=200, plan_years=10)
        r1 = run_simulation(_simple_inputs(random_seed=1, **base))
        r2 = run_simulation(_simple_inputs(random_seed=2, **base))

        assert not np.array_equal(r1.portfolio, r2.portfolio)


# ---------------------------------------------------------------------------
# Bivariate Normal Draws
# ---------------------------------------------------------------------------


class TestDraws:
    """Verify bivariate normal draw generation and inflation floor."""

    def test_inflation_floor_applied(self):
        inputs = _simple_inputs(inf_floor=0.01, n_paths=1000, plan_years=20)
        r = run_simulation(inputs)
        assert np.all(r.inf_draws >= 0.01)

    def test_draws_have_correct_mean_approx(self):
        inputs = _simple_inputs(
            n_paths=5000, plan_years=30,
            ret_mean=0.07, inf_mean=0.03, inf_floor=0.0,
        )
        r = run_simulation(inputs)
        # With 5000 × 30 = 150k draws, means should be close
        assert abs(r.ret_draws.mean() - 0.07) < 0.005
        assert abs(r.inf_draws.mean() - 0.03) < 0.005

    def test_draws_correlated(self):
        """Return and inflation draws should exhibit the specified correlation."""
        inputs = _simple_inputs(
            n_paths=5000, plan_years=30,
            ret_inf_corr=0.40, inf_floor=0.0,
        )
        r = run_simulation(inputs)
        corr = np.corrcoef(r.ret_draws.flat, r.inf_draws.flat)[0, 1]
        assert abs(corr - 0.40) < 0.05


# ---------------------------------------------------------------------------
# Cumulative Inflation
# ---------------------------------------------------------------------------


class TestCumulativeInflation:
    """Verify cumulative inflation index computation."""

    def test_cum_inf_year_zero(self):
        """Year 0 cum_inf = 1 + inf[0]."""
        inputs = _simple_inputs(n_paths=100, plan_years=5)
        r = run_simulation(inputs)
        expected_y0 = 1.0 + r.inf_draws[:, 0]
        np.testing.assert_array_almost_equal(r.cum_inf[:, 0], expected_y0)

    def test_cum_inf_is_product(self):
        """cum_inf[y] = product of (1 + inf[k]) for k=0..y."""
        inputs = _simple_inputs(n_paths=50, plan_years=10)
        r = run_simulation(inputs)
        expected = np.cumprod(1.0 + r.inf_draws, axis=1)
        np.testing.assert_array_almost_equal(r.cum_inf, expected)


# ---------------------------------------------------------------------------
# Social Security
# ---------------------------------------------------------------------------


class TestSocialSecurity:
    """Verify SS income calculation per spec §3.3 Step 2."""

    def test_ss_zero_before_start_age(self):
        inputs = _simple_inputs(
            retire_age=60, ss_start_age=67, plan_years=10,
            current_age=60,
            spending_tiers=[SpendingTier(60, 69, 50_000.0)],
        )
        r = run_simulation(inputs)
        # Ages 60–66: no SS; age 67–69: SS active
        for y in range(7):  # ages 60–66
            assert r.ss_income[0, y] == 0.0
        assert r.ss_income[0, 7] > 0.0  # age 67

    def test_ss_cola_growth(self):
        inputs = _simple_inputs(
            retire_age=67, ss_start_age=67, plan_years=5,
            ss_annual=24_000.0, ss_cola=0.025,
            spending_tiers=[SpendingTier(67, 71, 50_000.0)],
        )
        r = run_simulation(inputs)
        # Year 0: age=67, years_since_ss=0 → 24000 * 1.025^0 = 24000
        assert r.ss_income[0, 0] == pytest.approx(24_000.0)
        # Year 1: 24000 * 1.025^1
        assert r.ss_income[0, 1] == pytest.approx(24_000.0 * 1.025)
        # Year 3: 24000 * 1.025^3
        assert r.ss_income[0, 3] == pytest.approx(24_000.0 * 1.025**3)

    def test_ss_disabled(self):
        inputs = _simple_inputs(ss_enabled=False, n_paths=100, plan_years=5)
        r = run_simulation(inputs)
        assert np.all(r.ss_income == 0.0)

    def test_ss_uniform_across_paths(self):
        """SS income is deterministic — same value for all paths at a given year."""
        inputs = _simple_inputs(n_paths=100, plan_years=5)
        r = run_simulation(inputs)
        for y in range(5):
            assert np.all(r.ss_income[:, y] == r.ss_income[0, y])


# ---------------------------------------------------------------------------
# Health Insurance
# ---------------------------------------------------------------------------


class TestHealthInsurance:
    """Verify Medicare / ACA health cost routing."""

    def test_medicare_premium_at_medicare_age(self):
        inputs = _simple_inputs(
            retire_age=64, plan_years=3, current_age=64,
            spending_tiers=[SpendingTier(64, 66, 50_000.0)],
            health=HealthInsuranceConfig(
                medicare_age=65, medicare_premium=3_600.0,
                aca_guardrail_enabled=False,
            ),
            gr3=GuardrailGR3Config(enabled=False),
        )
        r = run_simulation(inputs)
        # Age 64: no Medicare, no GR3 → health=0
        assert r.health_cost[0, 0] == 0.0
        # Age 65: Medicare → medicare_premium * cum_inf
        assert r.health_cost[0, 1] == pytest.approx(3_600.0 * r.cum_inf[0, 1])

    def test_no_health_cost_when_gr3_disabled_pre_medicare(self):
        inputs = _simple_inputs(
            retire_age=60, plan_years=3, current_age=60,
            spending_tiers=[SpendingTier(60, 62, 50_000.0)],
            health=HealthInsuranceConfig(
                medicare_age=65, aca_guardrail_enabled=False,
            ),
            gr3=GuardrailGR3Config(enabled=False),
        )
        r = run_simulation(inputs)
        # All 3 years are pre-Medicare (ages 60–62) with GR3 disabled → 0
        assert np.all(r.health_cost == 0.0)


# ---------------------------------------------------------------------------
# Tax Gross-Up
# ---------------------------------------------------------------------------


class TestTaxGrossUp:
    """Verify effective rate and gross-up calculation."""

    def test_all_roth_no_gross_up(self):
        """100% Roth → effective_rate = 0 → gross = net."""
        inputs = _simple_inputs(
            roth_value=1_000_000.0, taxable_value=0.0, tax_deferred_value=0.0,
            n_paths=100, plan_years=5,
            # Disable guardrails to simplify
            gr1=GuardrailGR1Config(enabled=False),
            gr2=GuardrailGR2Config(enabled=False),
            gr3=GuardrailGR3Config(enabled=False),
            gr4=GuardrailGR4Config(enabled=False),
            ss_enabled=False,
        )
        r = run_simulation(inputs)
        # Where net_wd > 0, gross_wd should equal net_wd (no tax)
        mask = r.net_wd > 0
        np.testing.assert_array_almost_equal(
            r.gross_wd[mask], r.net_wd[mask],
        )

    def test_all_ira_gross_up(self):
        """100% IRA → effective_rate = ord_income_rate → gross = net / (1 - rate)."""
        ord_rate = 0.22
        inputs = _simple_inputs(
            taxable_value=0.0, tax_deferred_value=1_000_000.0, roth_value=0.0,
            ord_income_rate=ord_rate,
            n_paths=100, plan_years=3,
            gr1=GuardrailGR1Config(enabled=False),
            gr2=GuardrailGR2Config(enabled=False),
            gr3=GuardrailGR3Config(enabled=False),
            gr4=GuardrailGR4Config(enabled=False),
            ss_enabled=False,
        )
        r = run_simulation(inputs)
        mask = r.net_wd > 0
        expected_gross = r.net_wd[mask] / (1.0 - ord_rate)
        # gross_wd may be capped at portfolio_start; filter those out
        not_capped = r.gross_wd[mask] < r.portfolio[mask]  # approximate
        if not_capped.any():
            np.testing.assert_array_almost_equal(
                r.gross_wd[mask][not_capped],
                expected_gross[not_capped],
                decimal=2,
            )


# ---------------------------------------------------------------------------
# Ruin State / Depletion
# ---------------------------------------------------------------------------


class TestRuinState:
    """Verify portfolio depletion handling per spec §7.1–7.2."""

    def test_depleted_portfolio_stays_zero(self):
        """Once portfolio hits 0, it remains 0 for all subsequent years."""
        # Use high spending + low portfolio to force depletion
        inputs = _simple_inputs(
            port_start=100_000.0, taxable_value=100_000.0,
            spending_tiers=[SpendingTier(65, 99, 80_000.0)],
            spend_floor=0.0, spend_ceiling=200_000.0,
            n_paths=100, plan_years=20,
            ss_enabled=False,
            gr1=GuardrailGR1Config(enabled=False),
            gr2=GuardrailGR2Config(enabled=False),
            gr3=GuardrailGR3Config(enabled=False),
            gr4=GuardrailGR4Config(enabled=False),
        )
        r = run_simulation(inputs)

        # Find paths that deplete
        for p in range(r.n_paths):
            depleted = False
            for y in range(r.plan_years):
                if r.portfolio[p, y] <= 0:
                    depleted = True
                if depleted:
                    assert r.portfolio[p, y] == 0.0, (
                        f"Path {p}, year {y}: portfolio should be 0 after depletion"
                    )

    def test_depleted_spending_equals_ss(self):
        """After depletion with SS active, spending = SS income."""
        inputs = _simple_inputs(
            port_start=50_000.0, taxable_value=50_000.0,
            spending_tiers=[SpendingTier(65, 99, 80_000.0)],
            spend_floor=0.0, spend_ceiling=200_000.0,
            n_paths=100, plan_years=10,
            ss_enabled=True, ss_annual=24_000.0, ss_start_age=65,
            gr1=GuardrailGR1Config(enabled=False),
            gr2=GuardrailGR2Config(enabled=False),
            gr3=GuardrailGR3Config(enabled=False),
            gr4=GuardrailGR4Config(enabled=False),
        )
        r = run_simulation(inputs)

        for p in range(r.n_paths):
            for y in range(1, r.plan_years):
                # If portfolio was 0 at start of year (previous year end was 0)
                if r.portfolio[p, y - 1] <= 0:
                    assert r.spend[p, y] == pytest.approx(r.ss_income[p, y]), (
                        f"Path {p}, year {y}: depleted spending should equal SS income"
                    )
                    assert r.net_wd[p, y] == 0.0
                    assert r.gross_wd[p, y] == 0.0

    def test_depleted_no_ss_spending_zero(self):
        """After depletion with SS disabled, spending = 0."""
        inputs = _simple_inputs(
            port_start=50_000.0, taxable_value=50_000.0,
            spending_tiers=[SpendingTier(65, 99, 80_000.0)],
            spend_floor=0.0, spend_ceiling=200_000.0,
            n_paths=100, plan_years=10,
            ss_enabled=False,
            gr1=GuardrailGR1Config(enabled=False),
            gr2=GuardrailGR2Config(enabled=False),
            gr3=GuardrailGR3Config(enabled=False),
            gr4=GuardrailGR4Config(enabled=False),
        )
        r = run_simulation(inputs)

        for p in range(r.n_paths):
            for y in range(1, r.plan_years):
                if r.portfolio[p, y - 1] <= 0:
                    assert r.spend[p, y] == 0.0
                    assert r.net_wd[p, y] == 0.0

    def test_gross_wd_capped_at_portfolio(self):
        """Gross withdrawal cannot exceed portfolio_start (spec §7.2)."""
        inputs = _simple_inputs(n_paths=500, plan_years=20)
        r = run_simulation(inputs)
        # Reconstruct portfolio_start: for y>0 it's portfolio[:,y-1]; y=0 it's port_start
        port_start_arr = np.empty_like(r.portfolio)
        port_start_arr[:, 0] = inputs.port_start
        port_start_arr[:, 1:] = r.portfolio[:, :-1]

        # gross_wd should never exceed portfolio_start (within float tolerance)
        assert np.all(r.gross_wd <= port_start_arr + 1e-6)


# ---------------------------------------------------------------------------
# Guardrail Integration
# ---------------------------------------------------------------------------


class TestGuardrailIntegration:
    """Verify guardrails fire correctly through the engine."""

    def test_gr1_events_appear(self):
        """GR1 floor/ceiling events appear when portfolio drifts."""
        inputs = _simple_inputs(n_paths=500, plan_years=20)
        r = run_simulation(inputs)
        events_flat = set(r.events.flat)
        # With 500 paths over 20 years, some GR1 events should appear
        assert "PV-DOWN" in events_flat or "PV-UP" in events_flat

    def test_all_guardrails_disabled_only_none_events(self):
        """No guardrail events when all are disabled."""
        inputs = _simple_inputs(
            n_paths=200, plan_years=10,
            gr1=GuardrailGR1Config(enabled=False),
            gr2=GuardrailGR2Config(enabled=False),
            gr3=GuardrailGR3Config(enabled=False),
            gr4=GuardrailGR4Config(enabled=False),
        )
        r = run_simulation(inputs)
        # Only NONE events (alive paths) and NONE (ruined paths)
        assert set(r.events.flat) == {"NONE"}

    def test_floor_ceiling_clamp_applied(self):
        """Spending stays within [floor, ceiling] × cum_inf."""
        inputs = _simple_inputs(
            n_paths=500, plan_years=20,
            spend_floor=25_000.0, spend_ceiling=80_000.0,
        )
        r = run_simulation(inputs)

        # For alive paths only (ruined paths have spending = SS which may be < floor)
        port_start_arr = np.empty_like(r.portfolio)
        port_start_arr[:, 0] = inputs.port_start
        port_start_arr[:, 1:] = r.portfolio[:, :-1]
        alive = port_start_arr > 0

        nominal_floor = inputs.spend_floor * r.cum_inf
        nominal_ceiling = inputs.spend_ceiling * r.cum_inf

        assert np.all(r.spend[alive] >= nominal_floor[alive] - 1e-6)
        assert np.all(r.spend[alive] <= nominal_ceiling[alive] + 1e-6)


# ---------------------------------------------------------------------------
# Spending Tiers
# ---------------------------------------------------------------------------


class TestSpendingTiers:
    """Verify tier-based spending selection."""

    def test_multi_tier_spending(self):
        """Different tiers produce different base spending at correct ages."""
        inputs = _simple_inputs(
            retire_age=65, plan_years=10,
            spending_tiers=[
                SpendingTier(start_age=65, end_age=69, annual_spend=60_000.0),
                SpendingTier(start_age=70, end_age=74, annual_spend=40_000.0),
            ],
            n_paths=100,
            # Disable guardrails to isolate tier effect
            gr1=GuardrailGR1Config(enabled=False),
            gr2=GuardrailGR2Config(enabled=False),
            gr3=GuardrailGR3Config(enabled=False),
            gr4=GuardrailGR4Config(enabled=False),
            ss_enabled=False,
        )
        r = run_simulation(inputs)

        # Real spending should reflect tier amounts (before guardrails, for alive paths)
        # Year 0 (age 65) → tier 1 (60k real)
        # Year 5 (age 70) → tier 2 (40k real)
        assert r.real_spend[0, 0] == pytest.approx(60_000.0, rel=0.01)
        assert r.real_spend[0, 5] == pytest.approx(40_000.0, rel=0.01)


# ---------------------------------------------------------------------------
# Real vs Nominal
# ---------------------------------------------------------------------------


class TestRealNominal:
    """Verify real ↔ nominal conversions."""

    def test_real_portfolio_is_nominal_divided_by_cum_inf(self):
        r = run_simulation(_simple_inputs(n_paths=100, plan_years=5))
        np.testing.assert_array_almost_equal(
            r.real_portfolio, r.portfolio / r.cum_inf,
        )

    def test_real_spend_is_nominal_divided_by_cum_inf(self):
        r = run_simulation(_simple_inputs(n_paths=100, plan_years=5))
        np.testing.assert_array_almost_equal(
            r.real_spend, r.spend / r.cum_inf,
        )


# ---------------------------------------------------------------------------
# SimulationResults Methods
# ---------------------------------------------------------------------------


class TestResultMethods:
    """Verify computed properties on SimulationResults."""

    def test_success_rate_range(self):
        r = run_simulation(_simple_inputs(n_paths=500, plan_years=20))
        rate = r.success_rate()
        assert 0.0 <= rate <= 1.0

    def test_success_failure_counts_sum(self):
        r = run_simulation(_simple_inputs(n_paths=200, plan_years=15))
        assert r.success_count() + r.failure_count() == r.n_paths

    def test_inputs_deep_copied(self):
        """Mutating original inputs after run should not affect stored results."""
        inputs = _simple_inputs(n_paths=100, plan_years=5)
        r = run_simulation(inputs)
        original_port = r.inputs.port_start
        inputs.port_start = 999.0
        assert r.inputs.port_start == original_port

    def test_percentile_paths_keys(self):
        r = run_simulation(_simple_inputs(n_paths=200, plan_years=10))
        pcts = r.percentile_paths()
        assert set(pcts.keys()) == {10, 25, 50, 75, 90}
        for key, vals in pcts.items():
            assert len(vals) == 10  # plan_years


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Spec §7 edge cases."""

    def test_all_paths_survive_high_portfolio(self):
        """Large portfolio + low spending → all paths should survive."""
        inputs = _simple_inputs(
            port_start=10_000_000.0, taxable_value=10_000_000.0,
            spending_tiers=[SpendingTier(65, 99, 30_000.0)],
            n_paths=200, plan_years=10,
        )
        r = run_simulation(inputs)
        assert r.success_rate() == 1.0

    def test_all_paths_deplete_tiny_portfolio(self):
        """Spec §7.5: Tiny portfolio + huge spending → 0% survival."""
        inputs = _simple_inputs(
            port_start=1_000.0, taxable_value=1_000.0,
            spending_tiers=[SpendingTier(65, 99, 500_000.0)],
            spend_floor=0.0, spend_ceiling=1_000_000.0,
            n_paths=200, plan_years=10,
        )
        r = run_simulation(inputs)
        assert r.success_rate() == 0.0
        assert np.all(r.portfolio[:, -1] == 0)

    def test_minimum_plan_years(self):
        """plan_years=1 should run without error."""
        inputs = _simple_inputs(
            plan_years=1,
            spending_tiers=[SpendingTier(65, 65, 50_000.0)],
        )
        r = run_simulation(inputs)
        assert r.portfolio.shape == (inputs.n_paths, 1)

    def test_withdrawal_rate_zero_when_ss_covers_spending(self):
        """When SS ≥ spending, net withdrawal and WR should be 0."""
        inputs = _simple_inputs(
            retire_age=67, ss_start_age=67, plan_years=3,
            ss_annual=60_000.0,
            spending_tiers=[SpendingTier(67, 69, 30_000.0)],
            spend_floor=0.0,
            n_paths=100,
            gr1=GuardrailGR1Config(enabled=False),
            gr2=GuardrailGR2Config(enabled=False),
            gr3=GuardrailGR3Config(enabled=False),
            gr4=GuardrailGR4Config(enabled=False),
        )
        r = run_simulation(inputs)
        # SS (60k nominal at year 0, growing) > spending (30k real × cum_inf)
        # With inf ~3%, spending ~30k*1.03=30.9k at year 0. SS=60k.
        # net_wd should be 0 for year 0 at least
        assert np.all(r.net_wd[:, 0] == 0.0)
        assert np.all(r.gross_wd[:, 0] == 0.0)
        assert np.all(r.wr[:, 0] == 0.0)


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------


class TestPerformance:
    """Spec §3.7: 1000 paths × 35 years < 5 seconds."""

    @pytest.mark.slow
    def test_benchmark_1000x35(self):
        inputs = _simple_inputs(n_paths=1000, plan_years=35)
        start = time.perf_counter()
        run_simulation(inputs)
        elapsed = time.perf_counter() - start
        assert elapsed < 5.0, f"Simulation took {elapsed:.2f}s (limit: 5s)"
