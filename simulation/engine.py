"""Vectorized Monte Carlo simulation engine (spec §3.1–3.7).

Implements the full 8-step per-year simulation loop with bivariate normal
return/inflation draws, guardrail execution, tax-aware withdrawals, and
ruin-state handling.

Zero Streamlit imports — this module is part of the simulation layer.
"""

from __future__ import annotations

import numpy as np

from .guardrails import (
    apply_floor_ceiling,
    apply_gr1,
    apply_gr2,
    apply_gr3,
    apply_gr4,
)
from .helpers import get_base_spend
from .models import SimulationInputs, SimulationResults


def run_simulation(inputs: SimulationInputs) -> SimulationResults:
    """Execute Monte Carlo simulation per spec §3.1–3.7.

    Parameters
    ----------
    inputs : SimulationInputs
        Validated simulation inputs.  Caller is responsible for running
        ``validate_inputs()`` before calling this function.

    Returns
    -------
    SimulationResults
        Full result structure with all arrays and metadata.

    Raises
    ------
    ValueError
        If covariance matrix is not positive semi-definite (defensive guard;
        validation should catch this first).
    """
    n = inputs.n_paths
    T = inputs.plan_years
    port_start = inputs.port_start

    # ── 1. Generate bivariate normal draws (spec §3.2) ──────────────────────
    rng = np.random.default_rng(inputs.random_seed)
    cov = [
        [inputs.ret_std ** 2, inputs.ret_inf_corr * inputs.ret_std * inputs.inf_std],
        [inputs.ret_inf_corr * inputs.ret_std * inputs.inf_std, inputs.inf_std ** 2],
    ]
    means = [inputs.ret_mean, inputs.inf_mean]
    draws = rng.multivariate_normal(means, cov, size=(n, T))

    ret_draws = draws[:, :, 0]                                    # (n, T)
    inf_draws = np.clip(draws[:, :, 1], inputs.inf_floor, None)   # (n, T)

    # ── 2. Precompute static values ─────────────────────────────────────────
    roth_frac = inputs.roth_value / port_start if port_start > 0 else 0.0
    taxable_frac = inputs.taxable_value / port_start if port_start > 0 else 0.0
    ira_frac = inputs.tax_deferred_value / port_start if port_start > 0 else 0.0
    effective_rate = taxable_frac * inputs.ltcg_rate + ira_frac * inputs.ord_income_rate
    # Spec §5.8: roth_frac × 0 contributes nothing; omitted for clarity.

    ages = list(range(inputs.retire_age, inputs.retire_age + T))

    # ── 3. Initialize result arrays (n × T) ─────────────────────────────────
    portfolio_arr = np.zeros((n, T))
    real_port_arr = np.zeros((n, T))
    spend_arr = np.zeros((n, T))
    real_spend_arr = np.zeros((n, T))
    gross_wd_arr = np.zeros((n, T))
    net_wd_arr = np.zeros((n, T))
    wr_arr = np.zeros((n, T))
    cum_inf_arr = np.zeros((n, T))
    ss_arr = np.zeros((n, T))
    health_arr = np.zeros((n, T))
    event_arr = np.full((n, T), "NONE", dtype=object)

    # ── 4. Running state vectors ────────────────────────────────────────────
    portfolio_vec = np.full(n, port_start, dtype=float)
    cum_inf_vec = np.ones(n, dtype=float)

    # ── 5. Year loop — vectorized across n_paths (spec §3.3) ────────────────
    for y in range(T):
        age = inputs.retire_age + y
        ret_vec = ret_draws[:, y]     # (n,)
        inf_vec = inf_draws[:, y]     # (n,)

        # ── Step 1 — Age and Period Setup ───────────────────────────────────
        cum_inf_vec = cum_inf_vec * (1.0 + inf_vec)
        portfolio_start_vec = portfolio_vec.copy()
        alive = portfolio_start_vec > 0

        # ── Step 2 — Social Security Income ─────────────────────────────────
        if inputs.ss_enabled and age >= inputs.ss_start_age:
            ss_scalar = inputs.ss_annual * (
                (1.0 + inputs.ss_cola) ** (age - inputs.ss_start_age)
            )
        else:
            ss_scalar = 0.0
        ss_income_vec = np.full(n, ss_scalar, dtype=float)

        # ── Step 3 — Health Insurance Cost (Medicare case) ──────────────────
        # Pre-Medicare costs determined by GR3 during Step 5.
        health_cost_vec = np.where(
            age >= inputs.health.medicare_age,
            inputs.health.medicare_premium * cum_inf_vec,
            0.0,
        )

        # ── Step 4 — Base Spending from Tiers ──────────────────────────────
        base_spend_real = get_base_spend(age, inputs.spending_tiers)
        spend_vec = np.full(n, base_spend_real, dtype=float) * cum_inf_vec

        # ── Step 5 — Apply Guardrails (GR1 → GR2 → GR3 → GR4 → clamp) ────
        event_vec = np.full(n, "NONE", dtype=object)

        spend_vec, event_vec = apply_gr1(
            spend_vec, portfolio_start_vec, port_start, inputs.gr1, event_vec,
        )
        spend_vec, event_vec = apply_gr2(
            spend_vec, portfolio_start_vec, ss_income_vec, inputs.gr2, event_vec,
        )

        # GR3 determines health cost for pre-Medicare ages
        gr3_health, event_vec = apply_gr3(
            spend_vec, ss_income_vec, roth_frac, age,
            inputs.retire_age, inputs.health, inputs.gr3, cum_inf_vec, event_vec,
        )
        # Merge: keep Medicare premium for Medicare ages, GR3 cost otherwise
        health_cost_vec = np.where(
            age >= inputs.health.medicare_age,
            health_cost_vec,
            gr3_health,
        )

        spend_vec, event_vec = apply_gr4(
            spend_vec, inf_vec, inputs.gr4, event_vec,
        )
        spend_vec = apply_floor_ceiling(
            spend_vec, inputs.spend_floor, inputs.spend_ceiling, cum_inf_vec,
        )

        # ── Ruin-state override (spec §7.1) ─────────────────────────────────
        # Depleted paths: spending = SS income only, no withdrawal, no health cost.
        spend_vec = np.where(alive, spend_vec, ss_income_vec)
        health_cost_vec = np.where(alive, health_cost_vec, 0.0)
        event_vec = np.where(alive, event_vec, "NONE")

        # ── Step 6 — Withdrawal Calculation ─────────────────────────────────
        net_wd_vec = np.maximum(0.0, spend_vec - ss_income_vec)

        # Tax gross-up (spec §5.8)
        gross_wd_vec = np.where(
            net_wd_vec > 0,
            net_wd_vec / (1.0 - effective_rate),
            0.0,
        )

        # Cap at portfolio to prevent negative balance (spec §7.2)
        gross_wd_vec = np.minimum(gross_wd_vec, portfolio_start_vec)

        # Withdrawal rate (spec §3.3 Step 8)
        safe_denom = np.where(portfolio_start_vec > 0, portfolio_start_vec, 1.0)
        wr_vec = np.where(
            portfolio_start_vec > 0,
            gross_wd_vec / safe_denom,
            0.0,
        )

        # ── Step 7 — Portfolio Update ───────────────────────────────────────
        portfolio_vec = np.maximum(
            0.0,
            np.maximum(
                0.0,
                portfolio_start_vec - gross_wd_vec - health_cost_vec,
            ) * (1.0 + ret_vec),
        )

        # ── Step 8 — Store Results ──────────────────────────────────────────
        portfolio_arr[:, y] = portfolio_vec
        real_port_arr[:, y] = portfolio_vec / cum_inf_vec
        spend_arr[:, y] = spend_vec
        real_spend_arr[:, y] = spend_vec / cum_inf_vec
        gross_wd_arr[:, y] = gross_wd_vec
        net_wd_arr[:, y] = net_wd_vec
        wr_arr[:, y] = wr_vec
        cum_inf_arr[:, y] = cum_inf_vec
        ss_arr[:, y] = ss_income_vec
        health_arr[:, y] = health_cost_vec
        event_arr[:, y] = event_vec

    # ── Assemble result ─────────────────────────────────────────────────────
    return SimulationResults(
        portfolio=portfolio_arr,
        real_portfolio=real_port_arr,
        spend=spend_arr,
        real_spend=real_spend_arr,
        gross_wd=gross_wd_arr,
        net_wd=net_wd_arr,
        wr=wr_arr,
        cum_inf=cum_inf_arr,
        ss_income=ss_arr,
        health_cost=health_arr,
        events=event_arr,
        ret_draws=ret_draws,
        inf_draws=inf_draws,
        ages=ages,
        n_paths=n,
        plan_years=T,
        inputs=inputs,
    )
