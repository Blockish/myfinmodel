"""Monte Carlo Retirement Simulator — Streamlit application entry point."""

from __future__ import annotations

import streamlit as st

from simulation.models import GuardrailModel, SimulationParams, SimulationSummary

# NOTE: MonteCarloSimulator removed in Phase 2. App will be rewritten in Phase 3–5.
# from simulation.monte_carlo import MonteCarloSimulator
from ui.inputs import render_inputs
from ui.outputs import render_outputs


# ──────────────────────────────────────────────────────────────────────────────
# Page configuration
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="MyFinModel — Retirement Monte Carlo",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ──────────────────────────────────────────────────────────────────────────────
# Helper: Scenario B input form (used in Comparison tab)
# ──────────────────────────────────────────────────────────────────────────────

def _render_comparison_inputs() -> SimulationParams | None:
    """Minimal input form for the Scenario B comparison run."""
    with st.form("comparison_inputs"):
        st.markdown("**Scenario B Parameters**")
        c1, c2 = st.columns(2)
        with c1:
            portfolio = st.number_input(
                "Starting portfolio ($)",
                value=1_000_000.0,
                step=10_000.0,
                format="%.0f",
                key="cmp_portfolio",
            )
            spending = st.number_input(
                "Annual spending ($)",
                value=40_000.0,
                step=1_000.0,
                format="%.0f",
                key="cmp_spending",
            )
            mean_ret = st.slider(
                "Expected return (%)", 0.0, 20.0, 7.0, 0.5, key="cmp_ret"
            )
            ret_std = st.slider(
                "Return volatility (%)", 0.0, 30.0, 12.0, 0.5, key="cmp_std"
            )
        with c2:
            mean_inf = st.slider(
                "Expected inflation (%)", 0.0, 15.0, 3.0, 0.25, key="cmp_inf"
            )
            inf_std = st.slider(
                "Inflation volatility (%)", 0.0, 10.0, 1.0, 0.25, key="cmp_inf_std"
            )
            years = st.number_input("Years", 1, 60, 30, key="cmp_years")
            n_sims = st.select_slider(
                "Simulations",
                options=[100, 250, 500, 1_000, 2_000, 5_000, 10_000],
                value=1_000,
                key="cmp_nsims",
            )
            guardrail = st.selectbox(
                "Guardrail model",
                options=[m.value for m in GuardrailModel],
                key="cmp_guardrail",
            )
        submitted = st.form_submit_button("▶ Run Scenario B", type="primary")

    if not submitted:
        return None

    return SimulationParams(
        initial_portfolio=portfolio,
        annual_spending=spending,
        mean_return=mean_ret / 100.0,
        return_std=ret_std / 100.0,
        mean_inflation=mean_inf / 100.0,
        inflation_std=inf_std / 100.0,
        years=int(years),
        num_simulations=int(n_sims),
        guardrail_model=GuardrailModel(guardrail),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("💰 MyFinModel")
    st.caption("Retirement Spending Monte Carlo Simulator")
    st.divider()

    comparison_mode = st.toggle(
        "Enable Side-by-Side Comparison",
        value=st.session_state.get("comparison_mode", False),
        help=(
            "Run two independent simulations and display their results "
            "side-by-side to compare the effect of different parameter choices."
        ),
    )
    st.session_state["comparison_mode"] = comparison_mode

    st.divider()
    st.markdown(
        """
        **How to use**
        1. Fill in your retirement scenario on the **Inputs** tab.
        2. Click **▶ Run Simulation**.
        3. Review results on the **Results** tab.
        4. Optionally enable *Side-by-Side Comparison* to run a second scenario.

        **Guardrail Models**
        - *Inflation-Adjusted* — spending grows with inflation each year.
        - *Nominal Fixed* — spending stays constant in dollar terms.
        - *Guardrails (Dynamic)* — spending is adjusted up or down based on
          portfolio performance.

        ---
        *More guardrail strategies and simulation models coming soon.*
        """
    )


# ──────────────────────────────────────────────────────────────────────────────
# Main tabs
# ──────────────────────────────────────────────────────────────────────────────

tab_labels = ["📋 Inputs", "📊 Results"]
if comparison_mode:
    tab_labels.append("⚖️ Comparison")

tabs = st.tabs(tab_labels)

# ── Tab 0: Inputs ──────────────────────────────────────────────────────────────
with tabs[0]:
    params = render_inputs()
    if params is not None:
        with st.spinner("Running simulation…"):
            new_summary: SimulationSummary = MonteCarloSimulator(params).run()
        st.session_state["last_summary"] = new_summary
        st.success(
            f"✅ Simulation complete — "
            f"{params.num_simulations:,} paths × {params.years} years. "
            f"Switch to the **Results** tab to see the output."
        )

# ── Tab 1: Results ─────────────────────────────────────────────────────────────
with tabs[1]:
    last_summary: SimulationSummary | None = st.session_state.get("last_summary")

    if last_summary is None:
        st.info("👈 Run a simulation on the **Inputs** tab to see results here.")
    else:
        render_outputs(last_summary)

# ── Tab 2: Comparison (optional) ───────────────────────────────────────────────
if comparison_mode and len(tabs) > 2:
    with tabs[2]:
        st.header("⚖️ Side-by-Side Comparison")
        st.markdown(
            "Run a **second simulation** with adjusted parameters and compare it "
            "against your primary scenario."
        )

        col_a, col_b = st.columns(2)

        with col_a:
            st.subheader("Scenario A (Primary)")
            summary_a: SimulationSummary | None = st.session_state.get("last_summary")
            if summary_a is None:
                st.info("Run a simulation on the **Inputs** tab first.")
            else:
                render_outputs(summary_a, label="Scenario A")

        with col_b:
            st.subheader("Scenario B (Alternate)")
            summary_b: SimulationSummary | None = st.session_state.get(
                "comparison_summary"
            )

            with st.expander(
                "Configure Scenario B", expanded=(summary_b is None)
            ):
                params_b = _render_comparison_inputs()
                if params_b is not None:
                    with st.spinner("Running Scenario B…"):
                        summary_b = MonteCarloSimulator(params_b).run()
                    st.session_state["comparison_summary"] = summary_b

            if summary_b is None:
                st.info("Use the form above to configure and run Scenario B.")
            else:
                render_outputs(summary_b, label="Scenario B")
