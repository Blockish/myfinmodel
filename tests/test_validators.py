"""Unit tests for validation.validators (Phase 1)."""

from __future__ import annotations

import pytest

from simulation.models import (
    GuardrailGR2Config,
    HealthInsuranceConfig,
    SimulationInputs,
    SpendingTier,
)
from validation.validators import ValidationResult, validate_inputs


def _default_tiers(retire_age: int = 65, plan_years: int = 35) -> list[SpendingTier]:
    """Build contiguous tiers that cover the full horizon for valid-base scenarios."""
    end_age = retire_age + plan_years - 1
    return [SpendingTier(start_age=retire_age, end_age=end_age, annual_spend=50_000.0)]


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_valid_no_warnings(self):
        """Valid result with no warnings."""
        result = ValidationResult(valid=True, errors=[], warnings=[])
        assert result.valid
        assert len(result.errors) == 0
        assert len(result.warnings) == 0

    def test_valid_with_warnings(self):
        """Valid result with warnings."""
        result = ValidationResult(
            valid=True,
            errors=[],
            warnings=["Account sum differs"],
        )
        assert result.valid
        assert len(result.warnings) == 1

    def test_invalid(self):
        """Invalid result."""
        result = ValidationResult(
            valid=False,
            errors=["Portfolio must be > 0"],
            warnings=[],
        )
        assert not result.valid
        assert len(result.errors) == 1


class TestPortfolioValidation:
    """Tests for portfolio-related validation rules."""

    def test_block_portfolio_positive(self):
        """B1: Portfolio must be > 0."""
        inputs = SimulationInputs(port_start=0)
        result = validate_inputs(inputs)
        assert not result.valid
        assert any("must be > 0" in err for err in result.errors)

    def test_block_portfolio_negative(self):
        """B1: Reject negative portfolio."""
        inputs = SimulationInputs(port_start=-1000)
        result = validate_inputs(inputs)
        assert not result.valid
        assert any("must be > 0" in err for err in result.errors)

    def test_pass_portfolio_positive(self):
        """B1: Accept positive portfolio."""
        inputs = SimulationInputs(port_start=1000)
        result = validate_inputs(inputs)
        # May have other warnings/errors, but not this one
        assert not any("portfolio start" in err.lower() and "must be > 0" in err for err in result.errors)

    def test_warn_account_breakdown_mismatch(self):
        """W1: Warn if account breakdown doesn't match portfolio."""
        inputs = SimulationInputs(
            port_start=1_000_000.0,
            spending_tiers=_default_tiers(),
            taxable_value=200_000.0,
            tax_deferred_value=300_000.0,
            roth_value=100_000.0,
        )
        result = validate_inputs(inputs)
        assert result.valid
        assert any("breakdown" in w.lower() or "sum" in w.lower() for w in result.warnings)

    def test_pass_account_breakdown_match(self):
        """W1: No warning if accounts sum to portfolio."""
        inputs = SimulationInputs(
            port_start=1_000_000.0,
            spending_tiers=_default_tiers(),
            taxable_value=300_000.0,
            tax_deferred_value=500_000.0,
            roth_value=200_000.0,
        )
        result = validate_inputs(inputs)
        # Should not have breakdown warning
        assert not any("breakdown" in w.lower() or "Account" in w for w in result.warnings)


class TestSpendingValidation:
    """Tests for spending-related validation rules."""

    def test_block_spending_floor_negative(self):
        """B3: Spending floor cannot be negative."""
        inputs = SimulationInputs(port_start=1_000_000.0, spend_floor=-1000)
        result = validate_inputs(inputs)
        assert not result.valid
        assert any("floor" in err.lower() and "negative" in err.lower() for err in result.errors)

    def test_block_spending_ceiling_below_floor(self):
        """B4: Spending floor must be strictly less than ceiling."""
        inputs = SimulationInputs(
            port_start=1_000_000.0,
            spend_floor=50_000.0,
            spend_ceiling=30_000.0,
        )
        result = validate_inputs(inputs)
        assert not result.valid
        assert any("less than" in err.lower() for err in result.errors)

    def test_block_spending_ceiling_equal_floor(self):
        """B4: Equality is invalid; floor must be < ceiling."""
        inputs = SimulationInputs(
            port_start=1_000_000.0,
            spend_floor=50_000.0,
            spend_ceiling=50_000.0,
        )
        result = validate_inputs(inputs)
        assert not result.valid
        assert any("less than" in err.lower() for err in result.errors)

    def test_block_tiers_missing(self):
        """B2: Missing tiers should block run."""
        inputs = SimulationInputs(port_start=1_000_000.0, spending_tiers=[])
        result = validate_inputs(inputs)
        assert not result.valid
        assert any("no spending tier covers ages" in err.lower() for err in result.errors)

    def test_block_tier_gap(self):
        """B2: Spending tiers must be contiguous."""
        tiers = [
            SpendingTier(start_age=65, end_age=74, annual_spend=60_000.0),
            # Gap: 75 missing
            SpendingTier(start_age=76, end_age=99, annual_spend=40_000.0),
        ]
        inputs = SimulationInputs(port_start=1_000_000.0, spending_tiers=tiers)
        result = validate_inputs(inputs)
        assert not result.valid
        assert any("no spending tier covers ages" in err.lower() for err in result.errors)

    def test_block_tier_overlap(self):
        """B2: Spending tiers cannot overlap."""
        tiers = [
            SpendingTier(start_age=65, end_age=75, annual_spend=60_000.0),
            SpendingTier(start_age=75, end_age=85, annual_spend=40_000.0),
        ]
        inputs = SimulationInputs(port_start=1_000_000.0, spending_tiers=tiers)
        result = validate_inputs(inputs)
        assert not result.valid
        assert any("tier" in err.lower() for err in result.errors)

    def test_pass_valid_tiers(self):
        """B2: Pass with valid contiguous tiers."""
        tiers = [
            SpendingTier(start_age=65, end_age=74, annual_spend=60_000.0),
            SpendingTier(start_age=75, end_age=99, annual_spend=40_000.0),
        ]
        inputs = SimulationInputs(
            port_start=1_000_000.0,
            plan_years=35,
            retire_age=65,
            spending_tiers=tiers,
        )
        result = validate_inputs(inputs)
        # Should pass tier validation
        assert not any("tier" in err.lower() and ("gap" in err.lower() or "contiguou" in err.lower())
                      for err in result.errors)


class TestGuardrailValidation:
    """Tests for guardrail configuration validation."""

    def test_block_gr2_ordering(self):
        """B5: GR2 rates must be ordered: low < warn < crit."""
        inputs = SimulationInputs(
            port_start=1_000_000.0,
            gr2=GuardrailGR2Config(low_rate=0.05, warn_rate=0.03, crit_rate=0.065),
        )
        result = validate_inputs(inputs)
        assert not result.valid
        assert any("GR2" in err and "low_rate" in err for err in result.errors)

    def test_block_gr2_warn_crit_ordering(self):
        """B5: GR2 warn_rate must be < crit_rate."""
        inputs = SimulationInputs(
            port_start=1_000_000.0,
            gr2=GuardrailGR2Config(low_rate=0.03, warn_rate=0.065, crit_rate=0.05),
        )
        result = validate_inputs(inputs)
        assert not result.valid
        assert any("GR2" in err and "warn_rate" in err for err in result.errors)

    def test_pass_gr2_ordering(self):
        """B5: Pass with correct GR2 ordering."""
        inputs = SimulationInputs(
            port_start=1_000_000.0,
            spending_tiers=_default_tiers(),
            gr2=GuardrailGR2Config(low_rate=0.03, warn_rate=0.05, crit_rate=0.065),
        )
        result = validate_inputs(inputs)
        # Should not have GR2 ordering errors
        assert not any("GR2" in err and ("low_rate" in err or "warn_rate" in err) for err in result.errors)


class TestCorrelationValidation:
    """Tests for correlation validation."""

    def test_block_correlation_below_minus_one(self):
        """B6: Return–inflation correlation must satisfy |corr| < 1."""
        inputs = SimulationInputs(port_start=1_000_000.0, ret_inf_corr=-1.5)
        result = validate_inputs(inputs)
        assert not result.valid
        assert any("|corr| < 1" in err for err in result.errors)

    def test_block_correlation_above_one(self):
        """B6: Return–inflation correlation must satisfy |corr| < 1."""
        inputs = SimulationInputs(port_start=1_000_000.0, ret_inf_corr=1.5)
        result = validate_inputs(inputs)
        assert not result.valid
        assert any("|corr| < 1" in err for err in result.errors)

    def test_block_correlation_at_boundaries(self):
        """B6: Reject correlation at boundaries -1 and 1."""
        for corr in [-1.0, 1.0]:
            inputs = SimulationInputs(port_start=1_000_000.0, ret_inf_corr=corr)
            result = validate_inputs(inputs)
            assert not result.valid
            assert any("|corr| < 1" in err for err in result.errors)

    def test_pass_correlation_interior(self):
        """B6: Accept correlations strictly inside (-1, 1)."""
        for corr in [-0.99, 0.0, 0.99]:
            inputs = SimulationInputs(port_start=1_000_000.0, spending_tiers=_default_tiers(), ret_inf_corr=corr)
            result = validate_inputs(inputs)
            assert not any("correlation" in err.lower() for err in result.errors)

    def test_block_nonpositive_std_devs(self):
        """B6: ret_std and inf_std must be > 0."""
        inputs = SimulationInputs(port_start=1_000_000.0, ret_std=0.0, inf_std=0.0)
        result = validate_inputs(inputs)
        assert not result.valid
        assert any("return standard deviation" in err.lower() for err in result.errors)
        assert any("inflation standard deviation" in err.lower() for err in result.errors)


class TestACAValidation:
    """Tests for ACA-related validation."""

    def test_block_aca_magi_ordering(self):
        """B7: ACA MAGI target must be < cliff."""
        inputs = SimulationInputs(
            port_start=1_000_000.0,
            health=HealthInsuranceConfig(
                aca_magi_target=70_000.0,
                aca_magi_cliff=60_000.0,
            ),
        )
        result = validate_inputs(inputs)
        assert not result.valid
        assert any("MAGI" in err and "target" in err for err in result.errors)

    def test_block_aca_magi_equality(self):
        """B7: Equality is invalid; target must be strictly less than cliff."""
        inputs = SimulationInputs(
            port_start=1_000_000.0,
            health=HealthInsuranceConfig(
                aca_magi_target=62_000.0,
                aca_magi_cliff=62_000.0,
            ),
        )
        result = validate_inputs(inputs)
        assert not result.valid
        assert any("must be < cliff" in err for err in result.errors)

    def test_pass_aca_magi_ordering(self):
        """B7: Pass with correct ACA MAGI ordering."""
        inputs = SimulationInputs(
            port_start=1_000_000.0,
            health=HealthInsuranceConfig(
                aca_magi_target=58_000.0,
                aca_magi_cliff=62_000.0,
            ),
        )
        result = validate_inputs(inputs)
        assert not any("MAGI" in err and "target" in err for err in result.errors)


class TestSimulationSettingsValidation:
    """Tests for simulation settings validation."""

    def test_block_plan_years_too_low(self):
        """B2: plan_years must be >= 1."""
        inputs = SimulationInputs(port_start=1_000_000.0, plan_years=0)
        result = validate_inputs(inputs)
        assert not result.valid
        assert any("plan_years" in err.lower() and ">= 1" in err for err in result.errors)

    def test_plan_years_guard_skips_tier_horizon_math_when_invalid(self):
        """Invalid horizon should produce plan_years BLOCK without tier-range artifact."""
        inputs = SimulationInputs(port_start=1_000_000.0, plan_years=0, spending_tiers=[])
        result = validate_inputs(inputs)
        assert not result.valid
        assert any("plan_years" in err.lower() for err in result.errors)
        assert not any("no spending tier covers ages [65] to [64]" in err.lower() for err in result.errors)

    def test_block_n_paths_too_low(self):
        """B8: n_paths must be >= 100."""
        inputs = SimulationInputs(port_start=1_000_000.0, n_paths=50)
        result = validate_inputs(inputs)
        assert not result.valid
        assert any("n_paths" in err.lower() and "100" in err for err in result.errors)

    def test_block_n_paths_too_high(self):
        """B8: n_paths must be <= 10,000."""
        inputs = SimulationInputs(port_start=1_000_000.0, n_paths=15_000)
        result = validate_inputs(inputs)
        assert not result.valid
        assert any("n_paths" in err.lower() and "10,000" in err for err in result.errors)

    def test_pass_n_paths_boundaries(self):
        """B8: Accept n_paths at boundaries [100, 10000]."""
        for n in [100, 1000, 10_000]:
            inputs = SimulationInputs(port_start=1_000_000.0, spending_tiers=_default_tiers(), n_paths=n)
            result = validate_inputs(inputs)
            assert not any("n_paths" in err.lower() for err in result.errors)

    def test_warn_memory_large_simulation(self):
        """W2: Warn for large n_paths * plan_years."""
        inputs = SimulationInputs(
            port_start=1_000_000.0,
            spending_tiers=_default_tiers(plan_years=100),
            n_paths=10_000,
            plan_years=100,
        )
        result = validate_inputs(inputs)
        assert result.valid
        assert any("memory" in w.lower() or "allocate" in w.lower() for w in result.warnings)


class TestSocialSecurityValidation:
    """Tests for Social Security validation."""

    def test_block_ss_start_age_too_low(self):
        """B9: SS start age must be >= 62."""
        inputs = SimulationInputs(port_start=1_000_000.0, ss_enabled=True, ss_start_age=61)
        result = validate_inputs(inputs)
        assert not result.valid
        assert any("SS start age" in err and "62" in err for err in result.errors)

    def test_block_ss_start_age_too_high(self):
        """B9: SS start age must be <= 70."""
        inputs = SimulationInputs(port_start=1_000_000.0, ss_enabled=True, ss_start_age=71)
        result = validate_inputs(inputs)
        assert not result.valid
        assert any("SS start age" in err and "70" in err for err in result.errors)

    def test_pass_ss_start_age_boundaries(self):
        """B9: Accept SS start age in [62, 70]."""
        for age in [62, 67, 70]:
            inputs = SimulationInputs(port_start=1_000_000.0, ss_enabled=True, ss_start_age=age)
            result = validate_inputs(inputs)
            assert not any("SS start age" in err for err in result.errors)

    def test_warn_ss_after_horizon(self):
        """W4: Warn if SS starts after plan horizon ends."""
        inputs = SimulationInputs(
            port_start=1_000_000.0,
            retire_age=65,
            plan_years=5,
            ss_enabled=True,
            ss_start_age=70,  # Plan ends at 69 (65+5-1); 70 is after
            spending_tiers=_default_tiers(plan_years=5),
        )
        result = validate_inputs(inputs)
        assert result.valid
        assert any("Social Security" in w and "horizon" in w for w in result.warnings)

    def test_warn_ss_starts_at_retirement(self):
        """W5: Warn when SS starts immediately at retirement."""
        inputs = SimulationInputs(
            port_start=1_000_000.0,
            retire_age=67,
            ss_enabled=True,
            ss_start_age=67,
            spending_tiers=_default_tiers(retire_age=67),
        )
        result = validate_inputs(inputs)
        assert result.valid
        assert any("begins immediately" in w for w in result.warnings)


class TestInflationValidation:
    """Tests for inflation-related validation."""

    def test_warn_inflation_floor_exceeds_mean(self):
        """W3: Warn if inflation floor > mean."""
        inputs = SimulationInputs(
            port_start=1_000_000.0,
            spending_tiers=_default_tiers(),
            inf_mean=0.02,
            inf_floor=0.03,
        )
        result = validate_inputs(inputs)
        assert result.valid
        assert any("floor" in w.lower() and "exceed" in w.lower() for w in result.warnings)

    def test_warn_negative_return(self):
        """W7: Warn for negative expected return."""
        inputs = SimulationInputs(port_start=1_000_000.0, spending_tiers=_default_tiers(), ret_mean=-0.05)
        result = validate_inputs(inputs)
        assert result.valid
        assert any("negative" in w.lower() for w in result.warnings)

    def test_warn_unusual_return_std(self):
        """W6: Warn for unusual return std dev."""
        for std in [0.02, 0.30]:
            inputs = SimulationInputs(port_start=1_000_000.0, spending_tiers=_default_tiers(), ret_std=std)
            result = validate_inputs(inputs)
            assert result.valid
            # Both extremes should warn
            assert any("unusual" in w.lower() for w in result.warnings)


class TestIntegration:
    """Integration tests combining multiple validation rules."""

    def test_block_minimal_inputs_missing_tiers(self):
        """Missing spending tiers should fail validation per spec coverage rule."""
        inputs = SimulationInputs(port_start=1_000_000.0, spending_tiers=[])
        result = validate_inputs(inputs)
        assert not result.valid
        assert any("no spending tier covers ages" in err.lower() for err in result.errors)

    def test_valid_minimal_inputs_with_tier(self):
        """Minimal valid inputs with a single covering tier pass."""
        inputs = SimulationInputs(port_start=1_000_000.0, spending_tiers=_default_tiers())
        result = validate_inputs(inputs)
        assert result.valid

    def test_comprehensive_valid_inputs(self):
        """Complex but valid inputs pass all checks."""
        inputs = SimulationInputs(
            port_start=1_500_000.0,
            taxable_value=450_000.0,
            tax_deferred_value=750_000.0,
            roth_value=300_000.0,
            current_age=60,
            retire_age=65,
            ss_start_age=67,
            plan_years=35,
            spending_tiers=[
                SpendingTier(start_age=65, end_age=79, annual_spend=80_000.0),
                SpendingTier(start_age=80, end_age=99, annual_spend=60_000.0),
            ],
            ss_enabled=True,
            ss_annual=36_000.0,
            n_paths=2000,
            ret_mean=0.07,
            ret_std=0.11,
            ret_inf_corr=0.2,
            inf_mean=0.025,
            inf_std=0.012,
            inf_floor=0.01,
        )
        result = validate_inputs(inputs)
        assert result.valid

    def test_multiple_errors_reported(self):
        """Multiple validation errors are all reported."""
        inputs = SimulationInputs(
            port_start=-1000,  # Error
            n_paths=50,  # Error
            ss_enabled=True,
            ss_start_age=75,  # Error
        )
        result = validate_inputs(inputs)
        assert not result.valid
        assert len(result.errors) >= 3
