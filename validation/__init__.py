"""Input validation for Monte Carlo simulation.

This module provides validation for SimulationInputs
with no Streamlit imports to ensure portability.
"""

from .validators import ValidationResult, validate_inputs

__all__ = ["ValidationResult", "validate_inputs"]
