"""Results tab UI for the Monte Carlo retirement planner.

Phase 3 placeholder: displays summary metrics using the new SimulationResults
type.  Full chart and table implementation is Phase 4.
"""

from __future__ import annotations

import numpy as np
import streamlit as st

from simulation.models import SimulationResults


def render_outputs(results: SimulationResults) -> None:
    """Render results summary for a completed simulation.

    Parameters
    ----------
    results : SimulationResults
        Output from ``run_simulation()``.
    """
    # ── Summary Dashboard (8 metric cards) ────────────────────────────────────
    st.subheader("📊 Summary Dashboard")

    survival = results.success_rate()

    r1 = st.columns(4)
    r1[0].metric("Survival Rate", f"{survival:.1%}")
    r1[1].metric("Median Final Portfolio", f"${np.median(results.portfolio[:, -1]):,.0f}")
    r1[2].metric("10th Pct Final", f"${np.percentile(results.portfolio[:, -1], 10):,.0f}")
    r1[3].metric("90th Pct Final", f"${np.percentile(results.portfolio[:, -1], 90):,.0f}")

    # Surviving path-years mask
    alive_mask = results.portfolio > 0

    r2 = st.columns(4)
    avg_spend = float(np.mean(results.spend[alive_mask])) if alive_mask.any() else 0.0
    med_wr = float(np.median(results.wr[results.wr > 0])) if (results.wr > 0).any() else 0.0
    active_grs = sum([
        results.inputs.gr1.enabled,
        results.inputs.gr2.enabled,
        results.inputs.gr3.enabled and results.inputs.health.aca_guardrail_enabled,
        results.inputs.gr4.enabled,
    ])
    r2[0].metric("Avg Annual Spending", f"${avg_spend:,.0f}")
    r2[1].metric("Median Withdrawal Rate", f"{med_wr:.1%}")
    r2[2].metric("Active Guardrails", f"{active_grs} of 4")
    r2[3].metric("Inflation Floor", f"{results.inputs.inf_floor:.1%}")

    st.divider()

    # ── Success Metrics Table (Phase 3 placeholder) ───────────────────────────
    st.subheader("📋 Success Metrics")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Portfolio Outcomes**")
        portfolio_metrics = {
            "Survival Rate": f"{survival:.1%}",
            "Paths Depleted": f"{results.failure_count():,}",
            "Median Final Portfolio (nominal)": f"${np.median(results.portfolio[:, -1]):,.0f}",
            "Median Final Portfolio (real)": f"${np.median(results.real_portfolio[:, -1]):,.0f}",
            "10th Pct Final": f"${np.percentile(results.portfolio[:, -1], 10):,.0f}",
            "25th Pct Final": f"${np.percentile(results.portfolio[:, -1], 25):,.0f}",
            "75th Pct Final": f"${np.percentile(results.portfolio[:, -1], 75):,.0f}",
            "90th Pct Final": f"${np.percentile(results.portfolio[:, -1], 90):,.0f}",
            "Median Peak Portfolio": f"${np.median(np.max(results.portfolio, axis=1)):,.0f}",
        }
        for k, v in portfolio_metrics.items():
            st.markdown(f"- **{k}:** {v}")

    with col2:
        st.markdown("**Guardrail Trigger Frequencies**")
        events = results.events
        gr_metrics = {
            "Inflation — spending cut": f"{np.mean(np.any(events == 'INF', axis=1)) * 100:.1f}%",
            "Portfolio Value — spending cut": f"{np.mean(np.any(events == 'PV-DOWN', axis=1)) * 100:.1f}%",
            "Portfolio Value — spending raise": f"{np.mean(np.any(events == 'PV-UP', axis=1)) * 100:.1f}%",
            "Withdrawal Rate — warning cut": f"{np.mean(np.any(events == 'WR-WARN', axis=1)) * 100:.1f}%",
            "Withdrawal Rate — critical cut": f"{np.mean(np.any(events == 'WR-CRIT', axis=1)) * 100:.1f}%",
            "Withdrawal Rate — low raise": f"{np.mean(np.any(events == 'WR-LOW', axis=1)) * 100:.1f}%",
            "ACA MAGI — cliff breach": f"{np.mean(np.any(events == 'ACA-BREACH', axis=1)) * 100:.1f}%",
            "No guardrail ever triggered": f"{np.mean(np.all(events == 'NONE', axis=1)) * 100:.1f}%",
        }
        for k, v in gr_metrics.items():
            st.markdown(f"- **{k}:** {v}")

    st.divider()
    st.info(
        "📈 Full charts, downloadable tables, and scenario comparison "
        "will be available after Phase 4 implementation."
    )
