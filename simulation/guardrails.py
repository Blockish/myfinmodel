"""Guardrail logic for the Monte Carlo simulation engine (spec §3.5).

Each guardrail function operates on NumPy vectors of shape ``(n_paths,)``,
applying spending adjustments and recording event codes per the spec's
guardrail application order: GR1 → GR2 → GR3 → GR4 → floor/ceiling clamp.

Event code convention: only the **first** guardrail to fire sets the primary
event code for a given path-year cell.  Subsequent guardrails may still modify
spending but do **not** overwrite an existing non-NONE event code.

Zero Streamlit imports — this module is part of the simulation layer.
"""

from __future__ import annotations

import numpy as np

from .models import (
    GuardrailGR1Config,
    GuardrailGR2Config,
    GuardrailGR3Config,
    GuardrailGR4Config,
    HealthInsuranceConfig,
)


# ---------------------------------------------------------------------------
# GR1 — Portfolio Value Guardrail
# ---------------------------------------------------------------------------

def apply_gr1(
    spend_vec: np.ndarray,
    portfolio_start_vec: np.ndarray,
    port_start: float,
    gr1: GuardrailGR1Config,
    event_vec: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply GR1 — Portfolio Value Guardrail (spec §3.5 GR1).

    Cuts spending when portfolio falls below ``port_start × gr1.floor_pct``;
    raises spending when portfolio exceeds ``port_start × gr1.ceil_pct``.

    Parameters
    ----------
    spend_vec : ndarray, shape (n_paths,)
        Current nominal spending for each path.
    portfolio_start_vec : ndarray, shape (n_paths,)
        Portfolio value at the **start** of this year (before withdrawal).
    port_start : float
        Initial (time-zero) portfolio value used to compute floor/ceiling.
    gr1 : GuardrailGR1Config
        GR1 configuration (enabled flag, floor_pct, ceil_pct, cut_pct, raise_pct).
    event_vec : ndarray, shape (n_paths,), dtype=object
        Event codes so far for this year (``"NONE"`` if no prior event).

    Returns
    -------
    tuple[ndarray, ndarray]
        ``(modified_spend_vec, modified_event_vec)``
    """
    if not gr1.enabled:
        return spend_vec, event_vec

    gr1_floor = port_start * gr1.floor_pct
    gr1_ceil = port_start * gr1.ceil_pct

    floor_breach = portfolio_start_vec < gr1_floor
    ceil_breach = portfolio_start_vec > gr1_ceil

    spend_vec = np.where(floor_breach, spend_vec * (1 - gr1.cut_pct), spend_vec)
    spend_vec = np.where(ceil_breach, spend_vec * (1 + gr1.raise_pct), spend_vec)

    no_event = event_vec == "NONE"
    event_vec = np.where(floor_breach & no_event, "PV-DOWN", event_vec)
    event_vec = np.where(ceil_breach & no_event, "PV-UP", event_vec)

    return spend_vec, event_vec


# ---------------------------------------------------------------------------
# GR2 — Withdrawal Rate Guardrail
# ---------------------------------------------------------------------------

def apply_gr2(
    spend_vec: np.ndarray,
    portfolio_start_vec: np.ndarray,
    ss_income_vec: np.ndarray,
    gr2: GuardrailGR2Config,
    event_vec: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply GR2 — Withdrawal Rate Guardrail (spec §3.5 GR2).

    Estimates the withdrawal rate as
    ``max(0, spend - ss_income) / portfolio_start`` and adjusts spending
    based on which zone the WR falls into (low → raise, warn → cut, crit → bigger cut).

    Parameters
    ----------
    spend_vec : ndarray, shape (n_paths,)
        Current nominal spending (after any GR1 adjustments).
    portfolio_start_vec : ndarray, shape (n_paths,)
        Portfolio value at start of year (before withdrawal).
    ss_income_vec : ndarray, shape (n_paths,)
        Social Security income for this year (scalar broadcast is fine).
    gr2 : GuardrailGR2Config
        GR2 configuration.
    event_vec : ndarray, shape (n_paths,), dtype=object
        Current event codes.

    Returns
    -------
    tuple[ndarray, ndarray]
        ``(modified_spend_vec, modified_event_vec)``
    """
    if not gr2.enabled:
        return spend_vec, event_vec

    net_need = np.maximum(0.0, spend_vec - ss_income_vec)
    # Use safe denominator to avoid divide-by-zero RuntimeWarning;
    # np.where evaluates both branches so the division always executes.
    safe_denom = np.where(portfolio_start_vec > 0, portfolio_start_vec, 1.0)
    est_wr = np.where(
        portfolio_start_vec > 0,
        net_need / safe_denom,
        1.0,  # depleted portfolio → WR = 100 %
    )

    # Zones are mutually exclusive by rate ordering (low < warn < crit)
    crit = est_wr >= gr2.crit_rate
    warn = (~crit) & (est_wr >= gr2.warn_rate)
    low = est_wr < gr2.low_rate

    spend_vec = np.where(crit, spend_vec * (1 - gr2.crit_cut), spend_vec)
    spend_vec = np.where(warn, spend_vec * (1 - gr2.warn_cut), spend_vec)
    spend_vec = np.where(low, spend_vec * (1 + gr2.low_raise), spend_vec)

    no_event = event_vec == "NONE"
    event_vec = np.where(crit & no_event, "WR-CRIT", event_vec)
    event_vec = np.where(warn & no_event, "WR-WARN", event_vec)
    event_vec = np.where(low & no_event, "WR-LOW", event_vec)

    return spend_vec, event_vec


# ---------------------------------------------------------------------------
# GR3 — ACA MAGI Guardrail
# ---------------------------------------------------------------------------

def apply_gr3(
    spend_vec: np.ndarray,
    ss_income_vec: np.ndarray,
    roth_fraction: float,
    age: int,
    retire_age: int,
    health: HealthInsuranceConfig,
    gr3: GuardrailGR3Config,
    cum_inf_vec: np.ndarray,
    event_vec: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply GR3 — ACA MAGI Guardrail (spec §3.5 GR3).

    Determines health-insurance cost for pre-Medicare ages based on
    estimated MAGI relative to the ACA cliff.  When MAGI exceeds the cliff
    the full unsubsidized premium applies; otherwise the subsidized premium.

    Unlike GR1/GR2/GR4, GR3 does **not** modify ``spend_vec``; it returns
    ``health_cost_vec`` in place of spending.

    Parameters
    ----------
    spend_vec : ndarray, shape (n_paths,)
        Current nominal spending (after GR1 + GR2 adjustments).
    ss_income_vec : ndarray, shape (n_paths,)
        Social Security income for this year.
    roth_fraction : float
        Static Roth fraction ``roth_value / port_start``.
    age : int
        Current age in the simulation year.
    retire_age : int
        Retirement start age.
    health : HealthInsuranceConfig
        Health-insurance parameters (ACA thresholds, premiums, medicare_age).
    gr3 : GuardrailGR3Config
        GR3 configuration (enabled flag).
    cum_inf_vec : ndarray, shape (n_paths,)
        Cumulative inflation index for this year.
    event_vec : ndarray, shape (n_paths,), dtype=object
        Current event codes.

    Returns
    -------
    tuple[ndarray, ndarray]
        ``(health_cost_vec, modified_event_vec)`` — note first element is
        **health cost**, not spending.
    """
    n = len(spend_vec)

    # GR3 only active when enabled, ACA guardrail enabled, and in pre-Medicare range
    if (
        not gr3.enabled
        or not health.aca_guardrail_enabled
        or age < retire_age
        or age >= health.medicare_age
    ):
        return np.zeros(n, dtype=float), event_vec

    # Simplified MAGI estimate (spec §3.5 GR3 note)
    net_wd = np.maximum(0.0, spend_vec - ss_income_vec)
    estimated_magi = net_wd * (1.0 - roth_fraction)

    breach = estimated_magi > health.aca_magi_cliff

    health_cost_vec = np.where(
        breach,
        health.aca_premium_over * cum_inf_vec,
        health.aca_premium_under * cum_inf_vec,
    )

    no_event = event_vec == "NONE"
    event_vec = np.where(breach & no_event, "ACA-BREACH", event_vec)

    return health_cost_vec, event_vec


# ---------------------------------------------------------------------------
# GR4 — Inflation Guardrail
# ---------------------------------------------------------------------------

def apply_gr4(
    spend_vec: np.ndarray,
    inf_vec: np.ndarray,
    gr4: GuardrailGR4Config,
    event_vec: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply GR4 — Inflation Guardrail (spec §3.5 GR4).

    Applies a discretionary spending cut when the simulated annual inflation
    rate exceeds ``gr4.inf_trigger``.

    Parameters
    ----------
    spend_vec : ndarray, shape (n_paths,)
        Current nominal spending.
    inf_vec : ndarray, shape (n_paths,)
        Simulated annual inflation draws for this year.
    gr4 : GuardrailGR4Config
        GR4 configuration.
    event_vec : ndarray, shape (n_paths,), dtype=object
        Current event codes.

    Returns
    -------
    tuple[ndarray, ndarray]
        ``(modified_spend_vec, modified_event_vec)``
    """
    if not gr4.enabled:
        return spend_vec, event_vec

    triggered = inf_vec > gr4.inf_trigger
    spend_vec = np.where(triggered, spend_vec * (1 - gr4.cut_pct), spend_vec)

    no_event = event_vec == "NONE"
    event_vec = np.where(triggered & no_event, "INF", event_vec)

    return spend_vec, event_vec


# ---------------------------------------------------------------------------
# Floor / Ceiling Enforcement
# ---------------------------------------------------------------------------

def apply_floor_ceiling(
    spend_vec: np.ndarray,
    spend_floor: float,
    spend_ceiling: float,
    cum_inf_vec: np.ndarray,
) -> np.ndarray:
    """Clamp spending to [floor, ceiling] in nominal dollars (spec §3.5).

    Floor and ceiling are specified in real dollars and converted to nominal
    via ``cum_inf_vec`` before enforcement.

    Always applied unconditionally after all guardrails.

    Parameters
    ----------
    spend_vec : ndarray, shape (n_paths,)
        Spending after all guardrail adjustments.
    spend_floor : float
        Minimum annual spending in real dollars.
    spend_ceiling : float
        Maximum annual spending in real dollars.
    cum_inf_vec : ndarray, shape (n_paths,)
        Cumulative inflation index for this year.

    Returns
    -------
    ndarray
        Clamped spending vector.
    """
    return np.clip(
        spend_vec,
        spend_floor * cum_inf_vec,
        spend_ceiling * cum_inf_vec,
    )
