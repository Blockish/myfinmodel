"""Unit tests for simulation.guardrails and simulation.helpers (Phase 2).

Tests each guardrail in isolation and in combination, verifying:
- Spending adjustments match spec §3.5 formulas
- Event codes follow first-fires-wins convention
- Floor/ceiling clamp is always applied last
- Edge cases (depleted portfolio, zero SS, all disabled)
"""

from __future__ import annotations

import numpy as np
import pytest

from simulation.guardrails import (
    apply_floor_ceiling,
    apply_gr1,
    apply_gr2,
    apply_gr3,
    apply_gr4,
)
from simulation.helpers import get_base_spend
from simulation.models import (
    GuardrailGR1Config,
    GuardrailGR2Config,
    GuardrailGR3Config,
    GuardrailGR4Config,
    HealthInsuranceConfig,
    SpendingTier,
)


# ---------------------------------------------------------------------------
# Helpers — get_base_spend
# ---------------------------------------------------------------------------

class TestGetBaseSpend:
    """Tests for the spending-tier lookup helper."""

    def test_single_tier(self):
        tiers = [SpendingTier(start_age=65, end_age=99, annual_spend=50_000.0)]
        assert get_base_spend(65, tiers) == 50_000.0
        assert get_base_spend(80, tiers) == 50_000.0
        assert get_base_spend(99, tiers) == 50_000.0

    def test_multiple_tiers(self):
        tiers = [
            SpendingTier(start_age=65, end_age=69, annual_spend=60_000.0),
            SpendingTier(start_age=70, end_age=79, annual_spend=50_000.0),
            SpendingTier(start_age=80, end_age=99, annual_spend=35_000.0),
        ]
        assert get_base_spend(65, tiers) == 60_000.0
        assert get_base_spend(69, tiers) == 60_000.0
        assert get_base_spend(70, tiers) == 50_000.0
        assert get_base_spend(79, tiers) == 50_000.0
        assert get_base_spend(80, tiers) == 35_000.0

    def test_gap_raises_value_error(self):
        tiers = [SpendingTier(start_age=65, end_age=69, annual_spend=50_000.0)]
        with pytest.raises(ValueError, match="No spending tier covers age 70"):
            get_base_spend(70, tiers)

    def test_empty_tiers_raises(self):
        with pytest.raises(ValueError, match="No spending tier covers age"):
            get_base_spend(65, [])


# ---------------------------------------------------------------------------
# GR1 — Portfolio Value Guardrail
# ---------------------------------------------------------------------------

class TestApplyGR1:
    """Tests for GR1 Portfolio Value Guardrail."""

    def _events(self, n: int = 4) -> np.ndarray:
        return np.full(n, "NONE", dtype=object)

    def test_disabled(self):
        gr1 = GuardrailGR1Config(enabled=False)
        spend = np.array([50_000.0, 50_000.0])
        port_start_vec = np.array([400_000.0, 2_000_000.0])
        events = self._events(2)
        new_spend, new_events = apply_gr1(spend, port_start_vec, 1_000_000.0, gr1, events)
        np.testing.assert_array_equal(new_spend, spend)
        np.testing.assert_array_equal(new_events, events)

    def test_floor_breach_cuts_spending(self):
        gr1 = GuardrailGR1Config(floor_pct=0.50, cut_pct=0.10)
        port_start = 1_000_000.0
        spend = np.array([50_000.0, 50_000.0, 50_000.0])
        portfolio = np.array([400_000.0, 600_000.0, 1_600_000.0])  # below/at/above floor
        events = self._events(3)

        new_spend, new_events = apply_gr1(spend, portfolio, port_start, gr1, events)

        # Floor = 500k: path 0 below → cut 10%
        assert new_spend[0] == pytest.approx(45_000.0)
        assert new_events[0] == "PV-DOWN"
        # Path 1 at 600k (above floor, below ceiling) → no change
        assert new_spend[1] == pytest.approx(50_000.0)
        assert new_events[1] == "NONE"

    def test_ceiling_breach_raises_spending(self):
        gr1 = GuardrailGR1Config(ceil_pct=1.50, raise_pct=0.10)
        port_start = 1_000_000.0
        spend = np.array([50_000.0, 50_000.0])
        portfolio = np.array([1_600_000.0, 800_000.0])  # above ceiling / in-band
        events = self._events(2)

        new_spend, new_events = apply_gr1(spend, portfolio, port_start, gr1, events)

        assert new_spend[0] == pytest.approx(55_000.0)
        assert new_events[0] == "PV-UP"
        assert new_spend[1] == pytest.approx(50_000.0)
        assert new_events[1] == "NONE"

    def test_does_not_overwrite_existing_event(self):
        gr1 = GuardrailGR1Config(floor_pct=0.50, cut_pct=0.10)
        port_start = 1_000_000.0
        spend = np.array([50_000.0])
        portfolio = np.array([400_000.0])  # floor breach
        events = np.array(["WR-WARN"], dtype=object)  # prior event

        new_spend, new_events = apply_gr1(spend, portfolio, port_start, gr1, events)

        # Spending is still cut (guardrails always modify spending)
        assert new_spend[0] == pytest.approx(45_000.0)
        # But event is NOT overwritten
        assert new_events[0] == "WR-WARN"


# ---------------------------------------------------------------------------
# GR2 — Withdrawal Rate Guardrail
# ---------------------------------------------------------------------------

class TestApplyGR2:
    """Tests for GR2 Withdrawal Rate Guardrail."""

    def _events(self, n: int = 4) -> np.ndarray:
        return np.full(n, "NONE", dtype=object)

    def test_disabled(self):
        gr2 = GuardrailGR2Config(enabled=False)
        spend = np.array([50_000.0])
        events = self._events(1)
        new_spend, new_events = apply_gr2(
            spend, np.array([1_000_000.0]), np.array([0.0]), gr2, events
        )
        np.testing.assert_array_equal(new_spend, spend)

    def test_critical_zone_cuts(self):
        """WR >= crit_rate → crit_cut applied."""
        gr2 = GuardrailGR2Config(crit_rate=0.065, crit_cut=0.15)
        # spend=70k, portfolio=1M, ss=0 → WR=7% > 6.5%
        spend = np.array([70_000.0])
        portfolio = np.array([1_000_000.0])
        ss = np.array([0.0])
        events = self._events(1)

        new_spend, new_events = apply_gr2(spend, portfolio, ss, gr2, events)

        assert new_spend[0] == pytest.approx(70_000.0 * 0.85)
        assert new_events[0] == "WR-CRIT"

    def test_warning_zone_cuts(self):
        """warn_rate <= WR < crit_rate → warn_cut applied."""
        gr2 = GuardrailGR2Config(warn_rate=0.05, crit_rate=0.065, warn_cut=0.05)
        # spend=55k, portfolio=1M, ss=0 → WR=5.5%
        spend = np.array([55_000.0])
        portfolio = np.array([1_000_000.0])
        ss = np.array([0.0])
        events = self._events(1)

        new_spend, new_events = apply_gr2(spend, portfolio, ss, gr2, events)

        assert new_spend[0] == pytest.approx(55_000.0 * 0.95)
        assert new_events[0] == "WR-WARN"

    def test_low_zone_raises(self):
        """WR < low_rate → low_raise applied."""
        gr2 = GuardrailGR2Config(low_rate=0.03, low_raise=0.05)
        # spend=20k, portfolio=1M, ss=0 → WR=2%
        spend = np.array([20_000.0])
        portfolio = np.array([1_000_000.0])
        ss = np.array([0.0])
        events = self._events(1)

        new_spend, new_events = apply_gr2(spend, portfolio, ss, gr2, events)

        assert new_spend[0] == pytest.approx(20_000.0 * 1.05)
        assert new_events[0] == "WR-LOW"

    def test_normal_zone_no_change(self):
        """low_rate <= WR < warn_rate → no adjustment."""
        gr2 = GuardrailGR2Config(low_rate=0.03, warn_rate=0.05)
        # spend=40k, portfolio=1M, ss=0 → WR=4%
        spend = np.array([40_000.0])
        portfolio = np.array([1_000_000.0])
        ss = np.array([0.0])
        events = self._events(1)

        new_spend, new_events = apply_gr2(spend, portfolio, ss, gr2, events)

        assert new_spend[0] == pytest.approx(40_000.0)
        assert new_events[0] == "NONE"

    def test_ss_offsets_withdrawal_rate(self):
        """SS income reduces the net withdrawal rate calculation."""
        gr2 = GuardrailGR2Config(low_rate=0.03, low_raise=0.05)
        # spend=40k, portfolio=1M, ss=20k → net=20k → WR=2%
        spend = np.array([40_000.0])
        portfolio = np.array([1_000_000.0])
        ss = np.array([20_000.0])
        events = self._events(1)

        new_spend, new_events = apply_gr2(spend, portfolio, ss, gr2, events)

        assert new_events[0] == "WR-LOW"  # 2% < 3% low_rate

    def test_depleted_portfolio_wr_is_one(self):
        """Depleted portfolio → WR = 1.0 → critical zone."""
        gr2 = GuardrailGR2Config(crit_rate=0.065, crit_cut=0.15)
        spend = np.array([50_000.0])
        portfolio = np.array([0.0])
        ss = np.array([0.0])
        events = self._events(1)

        new_spend, new_events = apply_gr2(spend, portfolio, ss, gr2, events)

        assert new_events[0] == "WR-CRIT"


# ---------------------------------------------------------------------------
# GR3 — ACA MAGI Guardrail
# ---------------------------------------------------------------------------

class TestApplyGR3:
    """Tests for GR3 ACA MAGI Guardrail."""

    def _events(self, n: int = 2) -> np.ndarray:
        return np.full(n, "NONE", dtype=object)

    def _health(self, **overrides) -> HealthInsuranceConfig:
        return HealthInsuranceConfig(**overrides)

    def test_disabled(self):
        gr3 = GuardrailGR3Config(enabled=False)
        health = self._health()
        spend = np.array([50_000.0])
        events = self._events(1)
        h_cost, new_events = apply_gr3(
            spend, np.array([0.0]), 0.0, 63, 60, health, gr3, np.array([1.0]), events
        )
        assert h_cost[0] == 0.0
        np.testing.assert_array_equal(new_events, events)

    def test_aca_guardrail_disabled(self):
        gr3 = GuardrailGR3Config(enabled=True)
        health = self._health(aca_guardrail_enabled=False)
        spend = np.array([50_000.0])
        events = self._events(1)
        h_cost, _ = apply_gr3(
            spend, np.array([0.0]), 0.0, 63, 60, health, gr3, np.array([1.0]), events
        )
        assert h_cost[0] == 0.0

    def test_age_at_or_above_medicare_returns_zero(self):
        """GR3 inactive at or above medicare_age."""
        gr3 = GuardrailGR3Config(enabled=True)
        health = self._health(medicare_age=65)
        spend = np.array([50_000.0])
        events = self._events(1)
        h_cost, _ = apply_gr3(
            spend, np.array([0.0]), 0.0, 65, 60, health, gr3, np.array([1.0]), events
        )
        assert h_cost[0] == 0.0

    def test_cliff_breach_premium_over(self):
        """MAGI > cliff → unsubsidized premium + ACA-BREACH event."""
        gr3 = GuardrailGR3Config(enabled=True)
        health = self._health(
            aca_guardrail_enabled=True,
            aca_magi_cliff=62_000.0,
            aca_premium_over=18_000.0,
            aca_premium_under=4_800.0,
            medicare_age=65,
        )
        # spend=80k, ss=0, roth_fraction=0.0 → MAGI=80k > 62k cliff
        spend = np.array([80_000.0])
        ss = np.array([0.0])
        cum_inf = np.array([1.05])
        events = self._events(1)

        h_cost, new_events = apply_gr3(
            spend, ss, 0.0, 63, 60, health, gr3, cum_inf, events
        )

        assert h_cost[0] == pytest.approx(18_000.0 * 1.05)
        assert new_events[0] == "ACA-BREACH"

    def test_under_cliff_subsidized_premium(self):
        """MAGI <= cliff → subsidized premium, no ACA-BREACH event."""
        gr3 = GuardrailGR3Config(enabled=True)
        health = self._health(
            aca_guardrail_enabled=True,
            aca_magi_cliff=62_000.0,
            aca_premium_over=18_000.0,
            aca_premium_under=4_800.0,
            medicare_age=65,
        )
        # spend=30k, ss=0, roth_fraction=0.0 → MAGI=30k < 62k
        spend = np.array([30_000.0])
        ss = np.array([0.0])
        cum_inf = np.array([1.0])
        events = self._events(1)

        h_cost, new_events = apply_gr3(
            spend, ss, 0.0, 63, 60, health, gr3, cum_inf, events
        )

        assert h_cost[0] == pytest.approx(4_800.0)
        assert new_events[0] == "NONE"

    def test_roth_fraction_reduces_magi(self):
        """Higher Roth fraction reduces estimated MAGI, avoiding cliff breach."""
        gr3 = GuardrailGR3Config(enabled=True)
        health = self._health(
            aca_guardrail_enabled=True,
            aca_magi_cliff=62_000.0,
            aca_premium_over=18_000.0,
            aca_premium_under=4_800.0,
            medicare_age=65,
        )
        # spend=80k, ss=0 → net_wd=80k, roth_fraction=0.5 → MAGI=40k < 62k
        spend = np.array([80_000.0])
        ss = np.array([0.0])
        cum_inf = np.array([1.0])
        events = self._events(1)

        h_cost, new_events = apply_gr3(
            spend, ss, 0.5, 63, 60, health, gr3, cum_inf, events
        )

        assert h_cost[0] == pytest.approx(4_800.0)  # subsidized
        assert new_events[0] == "NONE"  # no breach

    def test_does_not_overwrite_prior_event(self):
        """GR3 ACA-BREACH sets event only if NONE."""
        gr3 = GuardrailGR3Config(enabled=True)
        health = self._health(
            aca_guardrail_enabled=True,
            aca_magi_cliff=62_000.0,
            aca_premium_over=18_000.0,
            medicare_age=65,
        )
        spend = np.array([80_000.0])
        ss = np.array([0.0])
        events = np.array(["PV-DOWN"], dtype=object)  # prior event

        h_cost, new_events = apply_gr3(
            spend, ss, 0.0, 63, 60, health, gr3, np.array([1.0]), events
        )

        # Premium is still over (MAGI > cliff), but event not overwritten
        assert h_cost[0] == pytest.approx(18_000.0)
        assert new_events[0] == "PV-DOWN"


# ---------------------------------------------------------------------------
# GR4 — Inflation Guardrail
# ---------------------------------------------------------------------------

class TestApplyGR4:
    """Tests for GR4 Inflation Guardrail."""

    def _events(self, n: int = 2) -> np.ndarray:
        return np.full(n, "NONE", dtype=object)

    def test_disabled(self):
        gr4 = GuardrailGR4Config(enabled=False)
        spend = np.array([50_000.0])
        events = self._events(1)
        new_spend, new_events = apply_gr4(spend, np.array([0.06]), gr4, events)
        np.testing.assert_array_equal(new_spend, spend)

    def test_triggered(self):
        """Inflation > trigger → spending cut."""
        gr4 = GuardrailGR4Config(inf_trigger=0.045, cut_pct=0.05)
        spend = np.array([50_000.0, 50_000.0])
        inf = np.array([0.05, 0.03])  # above / below trigger
        events = self._events(2)

        new_spend, new_events = apply_gr4(spend, inf, gr4, events)

        assert new_spend[0] == pytest.approx(50_000.0 * 0.95)
        assert new_events[0] == "INF"
        assert new_spend[1] == pytest.approx(50_000.0)
        assert new_events[1] == "NONE"

    def test_at_trigger_no_cut(self):
        """Inflation exactly at trigger → no cut (strict >)."""
        gr4 = GuardrailGR4Config(inf_trigger=0.045, cut_pct=0.05)
        spend = np.array([50_000.0])
        inf = np.array([0.045])
        events = self._events(1)

        new_spend, _ = apply_gr4(spend, inf, gr4, events)

        assert new_spend[0] == pytest.approx(50_000.0)

    def test_does_not_overwrite_prior_event(self):
        gr4 = GuardrailGR4Config(inf_trigger=0.045, cut_pct=0.05)
        spend = np.array([50_000.0])
        inf = np.array([0.06])
        events = np.array(["WR-CRIT"], dtype=object)

        new_spend, new_events = apply_gr4(spend, inf, gr4, events)

        # Spending cut still applied
        assert new_spend[0] == pytest.approx(50_000.0 * 0.95)
        # Event NOT overwritten
        assert new_events[0] == "WR-CRIT"


# ---------------------------------------------------------------------------
# Floor / Ceiling Enforcement
# ---------------------------------------------------------------------------

class TestFloorCeiling:
    """Tests for floor/ceiling spending clamp."""

    def test_clamps_to_floor(self):
        spend = np.array([5_000.0, 50_000.0, 200_000.0])
        cum_inf = np.array([1.0, 1.0, 1.0])
        result = apply_floor_ceiling(spend, 10_000.0, 150_000.0, cum_inf)
        assert result[0] == pytest.approx(10_000.0)  # clamped up
        assert result[1] == pytest.approx(50_000.0)   # unchanged
        assert result[2] == pytest.approx(150_000.0)   # clamped down

    def test_adjusts_for_inflation(self):
        """Floor and ceiling scale with cumulative inflation."""
        spend = np.array([5_000.0, 200_000.0])
        cum_inf = np.array([2.0, 2.0])
        result = apply_floor_ceiling(spend, 10_000.0, 80_000.0, cum_inf)
        # Floor = 10k * 2 = 20k; ceiling = 80k * 2 = 160k
        assert result[0] == pytest.approx(20_000.0)
        assert result[1] == pytest.approx(160_000.0)

    def test_zero_floor(self):
        """Floor of 0 allows any spending above zero."""
        spend = np.array([1.0])
        cum_inf = np.array([1.0])
        result = apply_floor_ceiling(spend, 0.0, 2_000_000.0, cum_inf)
        assert result[0] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Sequential Application — Event Code Priority
# ---------------------------------------------------------------------------

class TestSequentialGuardrails:
    """Test the full GR1 → GR2 → GR3 → GR4 → floor/ceiling sequence."""

    def test_first_event_wins(self):
        """When multiple guardrails fire, only the first sets the event code."""
        n = 1
        spend = np.array([50_000.0])
        events = np.full(n, "NONE", dtype=object)

        gr1 = GuardrailGR1Config(floor_pct=0.50, cut_pct=0.10)
        portfolio = np.array([300_000.0])  # below 500k floor
        port_start = 1_000_000.0

        # GR1 fires → PV-DOWN
        spend, events = apply_gr1(spend, portfolio, port_start, gr1, events)
        assert events[0] == "PV-DOWN"

        # GR4 also fires, but event should NOT change
        gr4 = GuardrailGR4Config(inf_trigger=0.045, cut_pct=0.05)
        inf = np.array([0.06])
        spend, events = apply_gr4(spend, inf, gr4, events)

        # Spending is adjusted by both GR1 and GR4
        expected = 50_000.0 * 0.90 * 0.95  # GR1 cut then GR4 cut
        assert spend[0] == pytest.approx(expected)
        # But event still reflects only GR1
        assert events[0] == "PV-DOWN"

    def test_all_guardrails_disabled(self):
        """No guardrails fire → NONE event, spending unchanged before clamp."""
        n = 2
        spend = np.array([50_000.0, 50_000.0])
        events = np.full(n, "NONE", dtype=object)

        gr1 = GuardrailGR1Config(enabled=False)
        gr2 = GuardrailGR2Config(enabled=False)
        gr4 = GuardrailGR4Config(enabled=False)

        spend, events = apply_gr1(spend, np.array([800_000.0, 800_000.0]),
                                  1_000_000.0, gr1, events)
        spend, events = apply_gr2(spend, np.array([800_000.0, 800_000.0]),
                                  np.array([0.0, 0.0]), gr2, events)
        spend, events = apply_gr4(spend, np.array([0.05, 0.05]), gr4, events)
        spend = apply_floor_ceiling(spend, 0.0, 2_000_000.0, np.ones(n))

        np.testing.assert_array_almost_equal(spend, [50_000.0, 50_000.0])
        assert all(e == "NONE" for e in events)

    def test_floor_ceiling_after_guardrails(self):
        """Guardrail cut below floor → floor clamp rescues it."""
        n = 1
        spend = np.array([15_000.0])
        events = np.full(n, "NONE", dtype=object)

        # GR1 cuts by 10% → 13,500
        gr1 = GuardrailGR1Config(floor_pct=0.50, cut_pct=0.10)
        portfolio = np.array([400_000.0])
        spend, events = apply_gr1(spend, portfolio, 1_000_000.0, gr1, events)
        assert spend[0] == pytest.approx(13_500.0)

        # Floor of 14,000 (real) rescues the cut
        cum_inf = np.array([1.0])
        spend = apply_floor_ceiling(spend, 14_000.0, 2_000_000.0, cum_inf)
        assert spend[0] == pytest.approx(14_000.0)

    def test_multi_path_mixed_events(self):
        """Different paths can trigger different guardrails."""
        n = 4
        spend = np.array([50_000.0, 50_000.0, 50_000.0, 30_000.0])
        events = np.full(n, "NONE", dtype=object)
        port_start = 1_000_000.0

        # Path 0: below GR1 floor (300k < 500k)
        # Path 1: above GR1 ceiling (1.6M > 1.5M)
        # Path 2: in-band but high WR (50k/600k ≈ 8.3% > crit 6.5%)
        # Path 3: in-band, normal WR (30k/900k ≈ 3.3%), high inflation
        portfolio = np.array([300_000.0, 1_600_000.0, 600_000.0, 900_000.0])

        gr1 = GuardrailGR1Config(floor_pct=0.50, ceil_pct=1.50, cut_pct=0.10, raise_pct=0.10)
        gr2 = GuardrailGR2Config(
            low_rate=0.03, warn_rate=0.05, crit_rate=0.065,
            low_raise=0.05, warn_cut=0.05, crit_cut=0.15,
        )
        gr4 = GuardrailGR4Config(inf_trigger=0.045, cut_pct=0.05)

        spend, events = apply_gr1(spend, portfolio, port_start, gr1, events)
        spend, events = apply_gr2(spend, portfolio, np.zeros(n), gr2, events)
        inf = np.array([0.02, 0.02, 0.02, 0.06])
        spend, events = apply_gr4(spend, inf, gr4, events)

        assert events[0] == "PV-DOWN"
        assert events[1] == "PV-UP"
        assert events[2] == "WR-CRIT"
        assert events[3] == "INF"
