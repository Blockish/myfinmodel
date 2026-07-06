from __future__ import annotations

import numpy as np

from simulation.models import SimulationInputs, SimulationResults
from ui.outputs import _event_frequency_df, _success_metrics_table


def _sample_results(*, gr3_enabled: bool = True, aca_guardrail_enabled: bool = True) -> SimulationResults:
    inputs = SimulationInputs(port_start=1_000_000.0, n_paths=2, plan_years=3)
    inputs.gr3.enabled = gr3_enabled
    inputs.health.aca_guardrail_enabled = aca_guardrail_enabled

    return SimulationResults(
        portfolio=np.array([[100.0, 90.0, 80.0], [100.0, 95.0, 0.0]]),
        real_portfolio=np.array([[100.0, 90.0, 80.0], [100.0, 95.0, 0.0]]),
        spend=np.full((2, 3), 50_000.0),
        real_spend=np.full((2, 3), 48_000.0),
        gross_wd=np.full((2, 3), 50_000.0),
        net_wd=np.full((2, 3), 48_000.0),
        wr=np.full((2, 3), 0.04),
        cum_inf=np.ones((2, 3)),
        ss_income=np.zeros((2, 3)),
        health_cost=np.zeros((2, 3)),
        events=np.array(
            [
                ["NONE", "ACA-BREACH", "INF"],
                ["PV-DOWN", "NONE", "NONE"],
            ],
            dtype=object,
        ),
        ret_draws=np.zeros((2, 3)),
        inf_draws=np.full((2, 3), 0.02),
        ages=[65, 66, 67],
        n_paths=2,
        plan_years=3,
        inputs=inputs,
    )


def test_success_metrics_table_labels_aca_disabled_reason():
    results = _sample_results(gr3_enabled=True, aca_guardrail_enabled=False)

    success_df = _success_metrics_table(results)
    aca_row = success_df.loc[success_df["Metric"] == "% paths with ACA-BREACH at least once", "Value"].iloc[0]

    assert aca_row == "N/A (ACA guardrail disabled)"


def test_event_frequency_df_omits_aca_breach_when_inactive():
    results = _sample_results(gr3_enabled=False, aca_guardrail_enabled=True)

    event_df = _event_frequency_df(results)

    assert "ACA-BREACH" not in event_df.columns
