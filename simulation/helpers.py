"""Shared helper functions for the simulation engine.

Zero Streamlit imports — this module is part of the simulation layer.
"""

from __future__ import annotations

from .models import SpendingTier


def get_base_spend(age: int, tiers: list[SpendingTier]) -> float:
    """Look up annual spending (real dollars) for the given age from spending tiers.

    Parameters
    ----------
    age : int
        The age to look up.
    tiers : list[SpendingTier]
        Spending tiers that must cover the age contiguously.
        Validated at input time; the ValueError below is a defensive guard.

    Returns
    -------
    float
        Annual spending in real (today's) dollars for the matching tier.

    Raises
    ------
    ValueError
        If no tier covers the given age (should not happen if validation passed).
    """
    for tier in tiers:
        if tier.start_age <= age <= tier.end_age:
            return tier.annual_spend
    raise ValueError(
        f"No spending tier covers age {age}. Validate tier coverage before simulation."
    )
