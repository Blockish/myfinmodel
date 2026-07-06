"""Monte Carlo simulation engine for retirement spending analysis."""

from .engine import run_simulation
from .guardrails import (
    apply_floor_ceiling,
    apply_gr1,
    apply_gr2,
    apply_gr3,
    apply_gr4,
)
from .helpers import get_base_spend
from .models import (
    GuardrailGR1Config,
    GuardrailGR2Config,
    GuardrailGR3Config,
    GuardrailGR4Config,
    HealthInsuranceConfig,
    SimulationInputs,
    SimulationResults,
    SpendingTier,
)

# Legacy re-exports kept until app.py is rewritten (Phase 3–5).
from .models import (  # noqa: F811
    GuardrailModel,
    SimulationParams,
    SimulationResult,
    SimulationSummary,
)

__all__ = [
    # Phase 2 API
    "run_simulation",
    "get_base_spend",
    "apply_gr1",
    "apply_gr2",
    "apply_gr3",
    "apply_gr4",
    "apply_floor_ceiling",
    "SimulationInputs",
    "SimulationResults",
    "SpendingTier",
    "GuardrailGR1Config",
    "GuardrailGR2Config",
    "GuardrailGR3Config",
    "GuardrailGR4Config",
    "HealthInsuranceConfig",
    # Legacy (remove after Phase 3–5 UI rewrite)
    "GuardrailModel",
    "SimulationParams",
    "SimulationResult",
    "SimulationSummary",
]
