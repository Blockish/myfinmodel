"""Core validation logic for SimulationInputs (spec §2.3).

All validators are pure functions with no Streamlit dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass

from simulation.models import SimulationInputs


@dataclass
class ValidationResult:
    """Result of validating a SimulationInputs object."""

    valid: bool
    """True if all BLOCK rules pass; False if any BLOCK rule fails."""

    errors: list[str]
    """BLOCK-level errors that prevent execution."""

    warnings: list[str]
    """WARN-level advisories; execution may proceed."""

    def __str__(self) -> str:
        """Pretty-print validation result."""
        lines = []
        if self.valid and not self.warnings:
            lines.append("✓ All inputs valid.")
        elif self.valid and self.warnings:
            lines.append(f"✓ Valid with {len(self.warnings)} warning(s).")
        else:
            lines.append(f"✗ Invalid: {len(self.errors)} error(s).")

        for err in self.errors:
            lines.append(f"  ERROR: {err}")
        for warn in self.warnings:
            lines.append(f"  WARNING: {warn}")

        return "\n".join(lines)


def validate_inputs(inputs: SimulationInputs) -> ValidationResult:
    """Validate all SimulationInputs per spec §2.3.

    Performs BLOCK (error) and WARN (warning) checks.

    Parameters
    ----------
    inputs : SimulationInputs
        Inputs to validate.

    Returns
    -------
    ValidationResult
        Result containing valid flag, errors, and warnings.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # ─────────────────────────────────────────────────────────────────────────
    # BLOCK Rules (prevent execution)
    # ─────────────────────────────────────────────────────────────────────────

    # B1: Portfolio must be positive
    if inputs.port_start <= 0:
        errors.append(f"Portfolio start ({inputs.port_start}) must be > 0.")

    # B2: Plan horizon must be valid
    if inputs.plan_years < 1:
        errors.append(f"Plan horizon (plan_years={inputs.plan_years}) must be >= 1.")

    # B3: Spending tiers must cover horizon contiguously
    if inputs.plan_years >= 1:
        errors.extend(_check_tier_contiguity(inputs))

    # B4: Spending floor must be >= 0
    if inputs.spend_floor < 0:
        errors.append(f"Spending floor ({inputs.spend_floor}) cannot be negative.")

    # B5: Spending ceiling must be > floor
    if inputs.spend_ceiling <= inputs.spend_floor:
        errors.append(
            f"Spending floor ({inputs.spend_floor}) must be less than ceiling ({inputs.spend_ceiling})."
        )

    # B6: GR2 thresholds must be ordered: low_rate < warn_rate < crit_rate
    errors.extend(_check_gr2_ordering(inputs))

    # B7: Covariance validity for bivariate draw matrix
    if abs(inputs.ret_inf_corr) >= 1:
        errors.append(
            f"Return–inflation correlation ({inputs.ret_inf_corr}) must satisfy |corr| < 1."
        )
    if inputs.ret_std <= 0:
        errors.append(f"Return standard deviation ({inputs.ret_std}) must be > 0.")
    if inputs.inf_std <= 0:
        errors.append(f"Inflation standard deviation ({inputs.inf_std}) must be > 0.")

    # B8: ACA MAGI thresholds must be ordered: target < cliff (only when ACA guardrail active)
    if inputs.health.aca_guardrail_enabled and inputs.health.aca_magi_target >= inputs.health.aca_magi_cliff:
        errors.append(
            f"ACA MAGI target ({inputs.health.aca_magi_target}) must be < cliff ({inputs.health.aca_magi_cliff})."
        )

    # B9: n_paths must be in valid range
    if not 100 <= inputs.n_paths <= 10_000:
        errors.append(f"n_paths ({inputs.n_paths}) must be between 100 and 10,000.")

    # B10: ss_start_age must be in [62, 70]
    if inputs.ss_enabled and not 62 <= inputs.ss_start_age <= 70:
        errors.append(f"SS start age ({inputs.ss_start_age}) must be between 62 and 70.")

    # ─────────────────────────────────────────────────────────────────────────
    # WARN Rules (advisory; execution may proceed)
    # ─────────────────────────────────────────────────────────────────────────

    # W1: Account sum should not exceed portfolio
    account_sum = inputs.taxable_value + inputs.tax_deferred_value + inputs.roth_value
    if account_sum > 0 and abs(account_sum - inputs.port_start) > 1.0:
        warnings.append(
            f"Account breakdown sum ({account_sum:,.0f}) differs from portfolio start ({inputs.port_start:,.0f})."
        )

    # W2: Memory warning for large n_paths
    memory_cells = inputs.n_paths * inputs.plan_years
    if memory_cells > 500_000:
        warnings.append(
            f"Simulation will allocate ~{memory_cells/1e6:.1f}M cells; may slow performance."
        )

    # W3: Inflation floor should not exceed mean
    if inputs.inf_floor > inputs.inf_mean:
        warnings.append(
            f"Inflation floor ({inputs.inf_floor:.2%}) exceeds mean ({inputs.inf_mean:.2%}); draws will be clipped."
        )

    # W4: Social Security timing warning
    if inputs.ss_enabled and inputs.ss_start_age > inputs.retire_age + inputs.plan_years - 1:
        warnings.append(
            f"Social Security starts at {inputs.ss_start_age}, after plan horizon ends at {inputs.retire_age + inputs.plan_years - 1}."
        )

    # W5: Social Security starts immediately at retirement
    if inputs.ss_enabled and inputs.ss_start_age == inputs.retire_age:
        warnings.append(
            "Social Security start age equals retirement age; SS income begins immediately in Year 1."
        )

    # W6: Uncommon return std dev
    if inputs.ret_std < 0.05 or inputs.ret_std > 0.25:
        warnings.append(
            f"Return std dev ({inputs.ret_std:.1%}) is unusual; typical range is 5%–25%."
        )

    # W7: Negative expected return
    if inputs.ret_mean < 0:
        warnings.append(f"Expected return is negative ({inputs.ret_mean:.1%}).")

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)


def _check_tier_contiguity(inputs: SimulationInputs) -> list[str]:
    """Check that spending tiers cover horizon [retire_age, retire_age+plan_years) contiguously.

    Returns
    -------
    list[str]
        List of error messages (empty if valid).
    """
    errors: list[str] = []

    if not inputs.spending_tiers:
        start_age = inputs.retire_age
        end_age = inputs.retire_age + inputs.plan_years - 1
        errors.append(
            f"No spending tier covers ages [{start_age}] to [{end_age}]. Add a tier or extend an existing tier."
        )
        return errors

    tiers = sorted(inputs.spending_tiers, key=lambda t: t.start_age)

    # Check for overlaps and gaps
    expected_start = inputs.retire_age
    expected_end = inputs.retire_age + inputs.plan_years - 1

    for tier in tiers:
        if tier.start_age < expected_start:
            errors.append(
                f"Spending tier overlap: tier starts at {tier.start_age} but expected {expected_start}."
            )
            break
        if tier.start_age > expected_start:
            errors.append(
                f"No spending tier covers ages [{expected_start}] to [{tier.start_age - 1}]."
            )
            break
        if tier.start_age > tier.end_age:
            errors.append(f"Spending tier has start_age > end_age: [{tier.start_age}, {tier.end_age}].")
            break
        expected_start = tier.end_age + 1

    if not errors and expected_start != expected_end + 1:
        errors.append(
            f"Spending tiers do not cover full horizon [{inputs.retire_age}, {expected_end}]; got up to {expected_start - 1}."
        )

    return errors


def _check_gr2_ordering(inputs: SimulationInputs) -> list[str]:
    """Check GR2 thresholds are correctly ordered: low_rate < warn_rate < crit_rate.

    Returns
    -------
    list[str]
        List of error messages (empty if valid).
    """
    errors: list[str] = []
    gr2 = inputs.gr2

    if gr2.low_rate >= gr2.warn_rate:
        errors.append(
            f"GR2 low_rate ({gr2.low_rate:.1%}) must be < warn_rate ({gr2.warn_rate:.1%})."
        )
    if gr2.warn_rate >= gr2.crit_rate:
        errors.append(
            f"GR2 warn_rate ({gr2.warn_rate:.1%}) must be < crit_rate ({gr2.crit_rate:.1%})."
        )

    return errors
