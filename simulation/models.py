"""Data models for the Monte Carlo retirement simulator.

All models are mutable dataclasses. Tests should verify that mutations
during simulation do not accidentally affect cached inputs or cause state leaks.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np


class GuardrailModel(str, Enum):
    """Supported withdrawal guardrail models (legacy API compatibility)."""

    INFLATION_ADJUSTED = "Inflation-Adjusted"
    NOMINAL_FIXED = "Nominal Fixed"
    GUARDRAILS_DYNAMIC = "Guardrails (Dynamic)"


@dataclass
class SimulationParams:
    """Legacy simulation input model kept for Phase 1 compatibility."""

    initial_portfolio: float = 1_000_000.0
    annual_spending: float = 40_000.0
    mean_return: float = 0.065
    return_std: float = 0.12
    mean_inflation: float = 0.03
    inflation_std: float = 0.01
    years: int = 30
    num_simulations: int = 1_000
    random_seed: Optional[int] = 42
    guardrail_model: GuardrailModel = GuardrailModel.INFLATION_ADJUSTED
    upper_guardrail: float = 0.20
    lower_guardrail: float = 0.20
    upper_guardrail_pct: float = 1.20
    lower_guardrail_pct: float = 0.80

    def withdrawal_rate(self) -> float:
        """Return the initial withdrawal rate as a percentage."""
        if self.initial_portfolio > 0:
            return self.annual_spending / self.initial_portfolio
        return 0.0


@dataclass
class SimulationResult:
    """Legacy per-path simulation result kept for Phase 1 compatibility."""

    path_id: int
    portfolio_values: list[float]
    annual_spending: list[float]
    success: bool
    depletion_year: Optional[int] = None

    @property
    def final_value(self) -> float:
        return self.portfolio_values[-1]

    @property
    def peak_value(self) -> float:
        return max(self.portfolio_values)

    @property
    def trough_value(self) -> float:
        return min(self.portfolio_values)


@dataclass
class SimulationSummary:
    """Legacy aggregate simulation summary kept for Phase 1 compatibility."""

    params: SimulationParams
    results: list[SimulationResult]

    @property
    def num_paths(self) -> int:
        return len(self.results)

    @property
    def success_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.success for r in self.results) / len(self.results)

    @property
    def success_count(self) -> int:
        return sum(r.success for r in self.results)

    @property
    def failure_count(self) -> int:
        return self.num_paths - self.success_count

    @property
    def median_final_value(self) -> float:
        finals = [r.final_value for r in self.results]
        if not finals:
            return 0.0
        return float(np.median(finals))

    @property
    def mean_final_value(self) -> float:
        finals = [r.final_value for r in self.results]
        if not finals:
            return 0.0
        return float(np.mean(finals))

    def percentile_paths(self, percentiles: list[int] | None = None) -> dict[int, list[float]]:
        """Return portfolio values across years at requested percentiles.

        Each list has length ``params.years + 1`` because it includes year 0.
        """
        if percentiles is None:
            percentiles = [10, 25, 50, 75, 90]
        if not self.results:
            return {}
        matrix = np.array([r.portfolio_values for r in self.results])
        return {
            p: np.percentile(matrix, p, axis=0).tolist()
            for p in percentiles
        }

    def depletion_year_distribution(self) -> dict[int, int]:
        """Return count of failed paths by depletion year."""
        dist: dict[int, int] = {}
        for r in self.results:
            if not r.success and r.depletion_year is not None:
                dist[r.depletion_year] = dist.get(r.depletion_year, 0) + 1
        return dist


@dataclass
class SpendingTier:
    """A single age-range spending tier (spec §2.2.3)."""

    start_age: int
    """First age covered by this tier (inclusive)."""

    end_age: int
    """Last age covered by this tier (inclusive)."""

    annual_spend: float
    """Annual spending in real (today's) dollars for this age range."""


@dataclass
class GuardrailGR1Config:
    """Portfolio Value Guardrail configuration (spec §2.2.7 GR1)."""

    enabled: bool = True
    floor_pct: float = 0.50
    """Portfolio floor as fraction of starting portfolio (50%)."""

    ceil_pct: float = 1.50
    """Portfolio ceiling as fraction of starting portfolio (150%)."""

    cut_pct: float = 0.10
    """Spending cut when floor is breached (10%)."""

    raise_pct: float = 0.10
    """Spending raise when ceiling is breached (10%)."""


@dataclass
class GuardrailGR2Config:
    """Withdrawal Rate Guardrail configuration (spec §2.2.7 GR2)."""

    enabled: bool = True
    low_rate: float = 0.03
    """Low withdrawal rate threshold (3.0%)."""

    warn_rate: float = 0.05
    """Warning withdrawal rate threshold (5.0%)."""

    crit_rate: float = 0.065
    """Critical withdrawal rate threshold (6.5%)."""

    low_raise: float = 0.05
    """Spending raise when WR < low_rate (5%)."""

    warn_cut: float = 0.05
    """Spending cut when warn_rate <= WR < crit_rate (5%)."""

    crit_cut: float = 0.15
    """Spending cut when WR >= crit_rate (15%)."""


@dataclass
class GuardrailGR3Config:
    """ACA MAGI Guardrail configuration (spec §2.2.7 GR3).

    Actual ACA thresholds and premiums are stored in HealthInsuranceConfig.
    """

    enabled: bool = True


@dataclass
class GuardrailGR4Config:
    """Inflation Guardrail configuration (spec §2.2.7 GR4)."""

    enabled: bool = True
    inf_trigger: float = 0.045
    """Inflation trigger rate (4.5%)."""

    cut_pct: float = 0.05
    """Spending cut when inflation exceeds trigger (5%)."""


@dataclass
class HealthInsuranceConfig:
    """Health insurance and ACA parameters (spec §2.2.5)."""

    medicare_age: int = 65
    """Age at which Medicare coverage begins."""

    medicare_premium: float = 3_600.0
    """Annual Medicare premium (Part B + D) in real dollars."""

    aca_guardrail_enabled: bool = True
    """Whether to apply ACA MAGI guardrail logic."""

    aca_magi_cliff: float = 62_000.0
    """MAGI threshold above which all ACA subsidies are lost (400% FPL)."""

    aca_magi_target: float = 58_000.0
    """Target MAGI to preserve full subsidy."""

    aca_premium_over: float = 18_000.0
    """Annual premium when MAGI exceeds cliff (unsubsidized)."""

    aca_premium_under: float = 4_800.0
    """Annual premium when MAGI is under cliff (subsidized)."""


@dataclass
class SimulationInputs:
    """All input parameters required to run a Monte Carlo simulation (spec §2.2).

    Mutable by design to support scenario editing and modification.
    """

    # ── Portfolio (spec §2.2.1) ──────────────────────────────────────────────
    port_start: float
    """Starting portfolio value in real dollars. Required; must be > 0."""

    taxable_value: float = 0.0
    """Taxable (brokerage) account value in real dollars."""

    tax_deferred_value: float = 0.0
    """Tax-deferred (IRA, 401k) account value in real dollars."""

    roth_value: float = 0.0
    """Roth (tax-free) account value in real dollars."""

    unrealized_gain_pct: float = 0.30
    """Fraction of taxable account representing embedded capital gains (0–1)."""

    ltcg_rate: float = 0.15
    """Long-term capital gains tax rate applied to taxable account (0–1)."""

    ord_income_rate: float = 0.22
    """Ordinary income tax rate applied to IRA/401k withdrawals (0–1)."""

    # ── Personal Information (spec §2.2.2) ───────────────────────────────────
    current_age: int = 65
    """Client's current age in years."""

    retire_age: int = 65
    """Age at which portfolio withdrawals begin."""

    ss_start_age: int = 67
    """Age at which Social Security benefits begin (62–70)."""

    plan_years: int = 35
    """Number of years to simulate from retire_age."""

    filing_status: str = "Single"
    """Tax filing status: 'Single' or 'Married Filing Jointly'."""

    # ── Spending (spec §2.2.3) ────────────────────────────────────────────────
    spending_tiers: list[SpendingTier] = field(default_factory=list)
    """Age-range spending tiers (1–5 tiers). Must cover full horizon contiguously."""

    spend_floor: float = 0.0
    """Minimum annual spending (real dollars). Guardrails cannot reduce below."""

    spend_ceiling: float = 2_000_000.0
    """Maximum annual spending (real dollars). Guardrails cannot increase above."""

    # ── Social Security (spec §2.2.4) ─────────────────────────────────────────
    ss_enabled: bool = True
    """Whether Social Security income is included."""

    ss_annual: float = 24_000.0
    """Annual SS benefit at claiming age, in real dollars."""

    ss_cola: float = 0.025
    """Social Security COLA (cost-of-living adjustment) rate (0–1)."""

    # ── Health Insurance (spec §2.2.5) ────────────────────────────────────────
    health: HealthInsuranceConfig = field(default_factory=HealthInsuranceConfig)
    """Health insurance and ACA configuration."""

    # ── Market Assumptions (spec §2.2.6) ──────────────────────────────────────
    ret_mean: float = 0.065
    """Expected annual portfolio return (6.5%)."""

    ret_std: float = 0.12
    """Annual return standard deviation (12%)."""

    ret_inf_corr: float = 0.10
    """Return–inflation correlation (-1 to 1)."""

    inf_mean: float = 0.03
    """Expected annual inflation (3%)."""

    inf_std: float = 0.015
    """Annual inflation standard deviation (1.5%)."""

    inf_floor: float = 0.01
    """Minimum annual inflation (1%); inflation draws clipped at this floor."""

    # ── Simulation Settings ────────────────────────────────────────────────────
    n_paths: int = 1_000
    """Number of Monte Carlo simulation paths (100–10,000)."""

    random_seed: int = 42
    """Random seed for reproducibility."""

    # ── Guardrails (spec §2.2.7) ──────────────────────────────────────────────
    gr1: GuardrailGR1Config = field(default_factory=GuardrailGR1Config)
    """Portfolio Value Guardrail (GR1) configuration."""

    gr2: GuardrailGR2Config = field(default_factory=GuardrailGR2Config)
    """Withdrawal Rate Guardrail (GR2) configuration."""

    gr3: GuardrailGR3Config = field(default_factory=GuardrailGR3Config)
    """ACA MAGI Guardrail (GR3) configuration."""

    gr4: GuardrailGR4Config = field(default_factory=GuardrailGR4Config)
    """Inflation Guardrail (GR4) configuration."""


@dataclass
class SimulationResults:
    """Aggregate results from Monte Carlo simulation (spec §3.6).

    Contains vectorized arrays (n_paths × plan_years) of all simulation outputs.
    """

    # ── Core arrays (shape: n_paths × plan_years unless noted) ────────────────
    portfolio: np.ndarray
    """Nominal portfolio value at end of each year."""

    real_portfolio: np.ndarray
    """Inflation-adjusted portfolio value (real dollars)."""

    spend: np.ndarray
    """Guardrail-adjusted nominal spending each year."""

    real_spend: np.ndarray
    """Inflation-adjusted spending (real dollars)."""

    gross_wd: np.ndarray
    """Gross withdrawal (tax-grossed-up) each year."""

    net_wd: np.ndarray
    """Net withdrawal (before tax gross-up) each year."""

    wr: np.ndarray
    """Withdrawal rate (gross_wd / portfolio_start) each year."""

    cum_inf: np.ndarray
    """Cumulative inflation index each year."""

    ss_income: np.ndarray
    """Social Security income (nominal, COLA-adjusted) each year."""

    health_cost: np.ndarray
    """Health insurance cost each year."""

    events: np.ndarray
    """Guardrail event codes (dtype=object, str values) each year."""

    ret_draws: np.ndarray
    """Raw portfolio return draws (shape: n_paths × plan_years)."""

    inf_draws: np.ndarray
    """Raw inflation draws post-floor-clipping (shape: n_paths × plan_years)."""

    # ── Metadata ───────────────────────────────────────────────────────────────
    ages: list[int]
    """Age at each year: [retire_age, retire_age+1, ..., retire_age+plan_years-1]."""

    n_paths: int
    """Number of simulation paths."""

    plan_years: int
    """Number of years simulated."""

    inputs: SimulationInputs
    """Deep copy of validated inputs used to generate this result."""

    def __post_init__(self) -> None:
        """Store an internal deep copy so later input mutation does not leak into results."""
        self.inputs = deepcopy(self.inputs)

    def success_rate(self) -> float:
        """Fraction of paths where portfolio > 0 at end of horizon."""
        if self.n_paths == 0:
            return 0.0
        return float(np.mean(self.portfolio[:, -1] > 0))

    def success_count(self) -> int:
        """Number of paths that survived to end of horizon."""
        return int(np.sum(self.portfolio[:, -1] > 0))

    def failure_count(self) -> int:
        """Number of paths that depleted."""
        return self.n_paths - self.success_count()

    def median_final_value(self) -> float:
        """Median final portfolio value (nominal)."""
        if self.n_paths == 0:
            return 0.0
        return float(np.median(self.portfolio[:, -1]))

    def percentile_paths(self, percentiles: list[int] | None = None) -> dict[int, list[float]]:
        """Return portfolio-value arrays at requested percentiles across years.

        Parameters
        ----------
        percentiles : list[int], optional
            Percentile values (0–100). Default: [10, 25, 50, 75, 90].

        Returns
        -------
        dict[int, list[float]]
            Mapping of percentile → list of portfolio values (length plan_years).
            Empty dict if no results.
        """
        if percentiles is None:
            percentiles = [10, 25, 50, 75, 90]
        if self.n_paths == 0:
            return {}
        return {
            p: np.percentile(self.portfolio, p, axis=0).tolist()
            for p in percentiles
        }

    def depletion_year_distribution(self) -> dict[int, int]:
        """Return count of failures by year of depletion.

        Returns
        -------
        dict[int, int]
            Mapping of depletion year (1-indexed) → count of paths.
            Empty dict if all paths survived.
        """
        dist: dict[int, int] = {}
        for p in range(self.n_paths):
            for y in range(self.plan_years):
                if self.portfolio[p, y] <= 0 and (y == 0 or self.portfolio[p, y - 1] > 0):
                    # First year where portfolio hit zero
                    depletion_year = y + 1  # Convert to 1-indexed
                    dist[depletion_year] = dist.get(depletion_year, 0) + 1
                    break
        return dist
