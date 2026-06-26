"""Data models for the Monte Carlo retirement simulator."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np


class GuardrailModel(str, Enum):
    """Supported withdrawal guardrail models."""

    INFLATION_ADJUSTED = "Inflation-Adjusted"
    NOMINAL_FIXED = "Nominal Fixed"
    GUARDRAILS_DYNAMIC = "Guardrails (Dynamic)"


@dataclass
class SimulationParams:
    """All input parameters required to run a Monte Carlo simulation."""

    # Portfolio
    initial_portfolio: float = 1_000_000.0
    """Starting portfolio value in dollars."""

    # Spending
    annual_spending: float = 40_000.0
    """Initial annual withdrawal amount in dollars."""

    # Return assumptions
    mean_return: float = 0.07
    """Expected annualized nominal investment return (e.g. 0.07 = 7 %)."""

    return_std: float = 0.12
    """Standard deviation of annual nominal returns (e.g. 0.12 = 12 %)."""

    # Inflation assumptions
    mean_inflation: float = 0.03
    """Expected annual inflation rate (e.g. 0.03 = 3 %)."""

    inflation_std: float = 0.01
    """Standard deviation of annual inflation (e.g. 0.01 = 1 %)."""

    # Time horizon
    years: int = 30
    """Number of years to simulate."""

    # Simulation settings
    num_simulations: int = 1_000
    """Number of Monte Carlo paths to generate."""

    random_seed: Optional[int] = None
    """Optional random seed for reproducibility."""

    # Guardrail model
    guardrail_model: GuardrailModel = GuardrailModel.INFLATION_ADJUSTED
    """Withdrawal guardrail strategy to apply."""

    # Dynamic guardrail thresholds (used only when model is GUARDRAILS_DYNAMIC)
    upper_guardrail: float = 0.20
    """Increase spending by this fraction when portfolio exceeds upper threshold."""

    lower_guardrail: float = 0.20
    """Decrease spending by this fraction when portfolio falls below lower threshold."""

    upper_guardrail_pct: float = 1.20
    """Portfolio-to-spending ratio above which the upper guardrail triggers."""

    lower_guardrail_pct: float = 0.80
    """Portfolio-to-spending ratio below which the lower guardrail triggers."""

    def withdrawal_rate(self) -> float:
        """Return the initial withdrawal rate as a percentage."""
        if self.initial_portfolio > 0:
            return self.annual_spending / self.initial_portfolio
        return 0.0


@dataclass
class SimulationResult:
    """Result for a single Monte Carlo path."""

    path_id: int
    """Zero-based index of this simulation path."""

    portfolio_values: list[float]
    """Portfolio value at the end of each year (length == params.years + 1,
    index 0 is the starting value)."""

    annual_spending: list[float]
    """Actual spending applied each year (length == params.years)."""

    success: bool
    """True if the portfolio survived (value > 0) for the entire horizon."""

    depletion_year: Optional[int] = None
    """Year in which the portfolio was depleted, or None if it survived."""

    @property
    def final_value(self) -> float:
        """Portfolio value at the end of the simulation horizon."""
        return self.portfolio_values[-1]

    @property
    def peak_value(self) -> float:
        """Maximum portfolio value across all years."""
        return max(self.portfolio_values)

    @property
    def trough_value(self) -> float:
        """Minimum portfolio value across all years."""
        return min(self.portfolio_values)


@dataclass
class SimulationSummary:
    """Aggregate statistics across all Monte Carlo paths."""

    params: SimulationParams
    """The parameters used to generate this summary."""

    results: list[SimulationResult]
    """All individual simulation paths."""

    # Aggregate metrics (computed lazily via property)
    _percentile_values: Optional[np.ndarray] = field(default=None, repr=False)

    @property
    def num_paths(self) -> int:
        return len(self.results)

    @property
    def success_rate(self) -> float:
        """Fraction of paths that succeeded (0–1)."""
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
        return float(np.median(finals))

    @property
    def mean_final_value(self) -> float:
        finals = [r.final_value for r in self.results]
        return float(np.mean(finals))

    def percentile_paths(self, percentiles: list[int] = None) -> dict[int, list[float]]:
        """Return portfolio-value arrays at the requested percentiles across years.

        Keys are percentile integers (e.g. 10, 25, 50, 75, 90).
        Each value is a list of length ``params.years + 1``.
        """
        if percentiles is None:
            percentiles = [10, 25, 50, 75, 90]
        # Shape: (num_paths, years+1)
        matrix = np.array([r.portfolio_values for r in self.results])
        return {
            p: np.percentile(matrix, p, axis=0).tolist()
            for p in percentiles
        }

    def depletion_year_distribution(self) -> dict[int, int]:
        """Return a count of failures by the year of depletion."""
        dist: dict[int, int] = {}
        for r in self.results:
            if not r.success and r.depletion_year is not None:
                dist[r.depletion_year] = dist.get(r.depletion_year, 0) + 1
        return dist
