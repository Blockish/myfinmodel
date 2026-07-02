"""Monte Carlo simulation engine for retirement spending analysis."""

from __future__ import annotations

import numpy as np

from .models import (
    GuardrailModel,
    SimulationParams,
    SimulationResult,
    SimulationSummary,
)


class MonteCarloSimulator:
    """Run Monte Carlo retirement-spending simulations.

    Usage
    -----
    >>> params = SimulationParams(initial_portfolio=1_000_000, annual_spending=40_000)
    >>> sim = MonteCarloSimulator(params)
    >>> summary = sim.run()
    >>> print(f"Success rate: {summary.success_rate:.1%}")
    """

    def __init__(self, params: SimulationParams) -> None:
        self.params = params

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> SimulationSummary:
        """Execute all simulation paths and return an aggregated summary."""
        p = self.params
        if p.years <= 0:
            raise ValueError(f"years must be > 0, got {p.years}")
        if p.num_simulations <= 0:
            raise ValueError(f"num_simulations must be > 0, got {p.num_simulations}")

        rng = np.random.default_rng(p.random_seed)

        # Pre-generate return and inflation matrices:
        # shape (num_simulations, years)
        returns = rng.normal(p.mean_return, p.return_std, (p.num_simulations, p.years))
        inflations = rng.normal(
            p.mean_inflation, p.inflation_std, (p.num_simulations, p.years)
        )
        # Clip extreme negative returns to avoid artifacts
        returns = np.clip(returns, -0.60, None)
        inflations = np.clip(inflations, 0.0, None)

        results: list[SimulationResult] = []
        for i in range(p.num_simulations):
            result = self._simulate_path(i, returns[i], inflations[i])
            results.append(result)

        return SimulationSummary(params=p, results=results)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _simulate_path(
        self,
        path_id: int,
        annual_returns: np.ndarray,
        annual_inflations: np.ndarray,
    ) -> SimulationResult:
        """Simulate a single retirement spending path."""
        p = self.params
        portfolio = p.initial_portfolio
        spending = p.annual_spending

        portfolio_values: list[float] = [portfolio]
        spending_history: list[float] = []
        depletion_year: int | None = None
        success = True

        for year_idx in range(p.years):
            ret = annual_returns[year_idx]
            inf = annual_inflations[year_idx]

            # Determine this year's spending based on guardrail model
            spending = self._apply_guardrail(
                model=p.guardrail_model,
                spending=spending,
                portfolio=portfolio,
                inflation=inf,
                year_idx=year_idx,
            )

            # Grow portfolio (returns applied after withdrawal at start of year)
            withdrawal = min(spending, portfolio)
            portfolio_after_withdrawal = portfolio - withdrawal
            portfolio = portfolio_after_withdrawal * (1.0 + ret)

            spending_history.append(withdrawal)
            portfolio_values.append(max(portfolio, 0.0))

            if portfolio <= 0.0:
                success = False
                depletion_year = year_idx + 1
                # Fill remaining years with zeros
                for remaining in range(p.years - year_idx - 1):
                    spending_history.append(0.0)
                    portfolio_values.append(0.0)
                break

        return SimulationResult(
            path_id=path_id,
            portfolio_values=portfolio_values,
            annual_spending=spending_history,
            success=success,
            depletion_year=depletion_year,
        )

    def _apply_guardrail(
        self,
        model: GuardrailModel,
        spending: float,
        portfolio: float,
        inflation: float,
        year_idx: int,
    ) -> float:
        """Return the adjusted spending for the current year."""
        p = self.params

        if model == GuardrailModel.NOMINAL_FIXED:
            # Spending never changes
            return spending

        if model == GuardrailModel.INFLATION_ADJUSTED:
            # Increase spending with inflation each year (except year 0)
            if year_idx == 0:
                return spending
            return spending * (1.0 + inflation)

        if model == GuardrailModel.GUARDRAILS_DYNAMIC:
            if year_idx == 0:
                return spending
            # Adjust for inflation first
            inflation_adjusted = spending * (1.0 + inflation)
            if inflation_adjusted <= 0 or portfolio <= 0:
                return 0.0
            # Compute starting portfolio-to-spending ratio as the reference baseline
            initial_ratio = (
                p.initial_portfolio / p.annual_spending
                if p.annual_spending > 0
                else 0.0
            )
            ratio = portfolio / inflation_adjusted
            upper_threshold = initial_ratio * p.upper_guardrail_pct
            lower_threshold = initial_ratio * p.lower_guardrail_pct
            if ratio > upper_threshold:
                # Portfolio doing well – allow a modest spending increase
                new_spending = inflation_adjusted * (1.0 + p.upper_guardrail)
            elif ratio < lower_threshold:
                # Portfolio under stress – reduce spending
                new_spending = inflation_adjusted * (1.0 - p.lower_guardrail)
            else:
                new_spending = inflation_adjusted
            return max(new_spending, 0.0)

        # Fallback – return unchanged spending
        return spending
