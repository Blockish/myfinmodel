"""Input UI page for the Monte Carlo retirement simulator."""

from __future__ import annotations

import streamlit as st

from simulation.models import GuardrailModel, SimulationParams


def render_inputs() -> SimulationParams | None:
    """Render the inputs form and return a ``SimulationParams`` on submission.

    Returns ``None`` when the form has not yet been submitted.
    """
    st.header("📋 Simulation Inputs")
    st.markdown(
        "Configure your retirement scenario below. "
        "You may also **upload an Excel spreadsheet** to pre-fill these fields."
    )

    # ── Spreadsheet upload (placeholder) ──────────────────────────────────────
    with st.expander("📂 Import from Spreadsheet (optional)", expanded=False):
        uploaded = st.file_uploader(
            "Upload an Excel file (.xlsx) with your plan inputs",
            type=["xlsx"],
            key="spreadsheet_upload",
        )
        if uploaded is not None:
            st.info(
                "✅ Spreadsheet uploaded. Automatic field population will be "
                "available in a future release — values from the spreadsheet "
                "will be used to pre-fill the form."
            )
            _prefill_from_spreadsheet(uploaded)

    st.divider()

    # ── Main input form ────────────────────────────────────────────────────────
    with st.form("simulation_inputs"):
        col_left, col_right = st.columns(2)

        with col_left:
            st.subheader("Portfolio")
            initial_portfolio = st.number_input(
                "Starting portfolio value ($)",
                min_value=0.0,
                value=st.session_state.get("input_initial_portfolio", 1_000_000.0),
                step=10_000.0,
                format="%.0f",
                help="Current total investable assets.",
            )
            st.subheader("Spending")
            annual_spending = st.number_input(
                "Annual spending / withdrawal ($)",
                min_value=0.0,
                value=st.session_state.get("input_annual_spending", 40_000.0),
                step=1_000.0,
                format="%.0f",
                help="Initial annual amount withdrawn from the portfolio.",
            )

        with col_right:
            st.subheader("Return Assumptions")
            mean_return = st.slider(
                "Expected annual return (%)",
                min_value=0.0,
                max_value=20.0,
                value=st.session_state.get("input_mean_return", 7.0),
                step=0.5,
                help="Mean nominal annual investment return.",
            )
            return_std = st.slider(
                "Return volatility / std dev (%)",
                min_value=0.0,
                max_value=30.0,
                value=st.session_state.get("input_return_std", 12.0),
                step=0.5,
                help="Standard deviation of annual nominal returns.",
            )

            st.subheader("Inflation Assumptions")
            mean_inflation = st.slider(
                "Expected annual inflation (%)",
                min_value=0.0,
                max_value=15.0,
                value=st.session_state.get("input_mean_inflation", 3.0),
                step=0.25,
                help="Mean annual inflation rate.",
            )
            inflation_std = st.slider(
                "Inflation volatility / std dev (%)",
                min_value=0.0,
                max_value=10.0,
                value=st.session_state.get("input_inflation_std", 1.0),
                step=0.25,
                help="Standard deviation of annual inflation.",
            )

        st.divider()
        col_sim1, col_sim2 = st.columns(2)

        with col_sim1:
            st.subheader("Simulation Settings")
            years = st.number_input(
                "Time horizon (years)",
                min_value=1,
                max_value=60,
                value=st.session_state.get("input_years", 30),
                step=1,
            )
            num_simulations = st.select_slider(
                "Number of simulations",
                options=[100, 250, 500, 1_000, 2_000, 5_000, 10_000],
                value=st.session_state.get("input_num_simulations", 1_000),
                help="More simulations → more accurate results but slower.",
            )
            random_seed_str = st.text_input(
                "Random seed (leave blank for random)",
                value=st.session_state.get("input_random_seed", ""),
                help="Integer seed for reproducible results.",
            )

        with col_sim2:
            st.subheader("Guardrail Model")
            guardrail_model = st.selectbox(
                "Withdrawal guardrail strategy",
                options=[m.value for m in GuardrailModel],
                index=st.session_state.get("input_guardrail_index", 0),
                help=(
                    "**Inflation-Adjusted**: spending rises with inflation each year.\n\n"
                    "**Nominal Fixed**: spending stays constant in dollar terms.\n\n"
                    "**Guardrails (Dynamic)**: spending is dynamically adjusted up or "
                    "down based on portfolio performance relative to a target ratio."
                ),
            )

            # Dynamic guardrail thresholds (shown only when relevant)
            if guardrail_model == GuardrailModel.GUARDRAILS_DYNAMIC.value:
                st.markdown("**Dynamic Guardrail Thresholds**")
                upper_pct = st.number_input(
                    "Upper guardrail threshold (multiplier of starting portfolio/spending ratio)",
                    min_value=1.0, max_value=5.0,
                    value=st.session_state.get("input_upper_guardrail_pct", 1.20),
                    step=0.05,
                    help="Spending increases when the current portfolio/spending ratio exceeds this multiplier × the starting ratio (e.g. 1.20 = 120% of initial ratio).",
                )
                lower_pct = st.number_input(
                    "Lower guardrail threshold (multiplier of starting portfolio/spending ratio)",
                    min_value=0.1, max_value=1.5,
                    value=st.session_state.get("input_lower_guardrail_pct", 0.80),
                    step=0.05,
                    help="Spending is cut when the current portfolio/spending ratio falls below this multiplier × the starting ratio (e.g. 0.80 = 80% of initial ratio).",
                )
                upper_adj = st.number_input(
                    "Spending increase when above upper guardrail (%)",
                    min_value=0.0, max_value=50.0,
                    value=st.session_state.get("input_upper_guardrail", 20.0),
                    step=1.0,
                )
                lower_adj = st.number_input(
                    "Spending cut when below lower guardrail (%)",
                    min_value=0.0, max_value=50.0,
                    value=st.session_state.get("input_lower_guardrail", 20.0),
                    step=1.0,
                )
            else:
                upper_pct = 1.20
                lower_pct = 0.80
                upper_adj = 20.0
                lower_adj = 20.0

        submitted = st.form_submit_button("▶ Run Simulation", type="primary")

    if not submitted:
        return None

    # Parse optional random seed
    random_seed: int | None = None
    if random_seed_str.strip():
        try:
            random_seed = int(random_seed_str.strip())
        except ValueError:
            st.warning("Random seed must be an integer — ignoring.")

    # Persist inputs in session state so they survive tab switches
    st.session_state.update(
        {
            "input_initial_portfolio": initial_portfolio,
            "input_annual_spending": annual_spending,
            "input_mean_return": mean_return,
            "input_return_std": return_std,
            "input_mean_inflation": mean_inflation,
            "input_inflation_std": inflation_std,
            "input_years": years,
            "input_num_simulations": num_simulations,
            "input_random_seed": random_seed_str,
            "input_guardrail_index": [m.value for m in GuardrailModel].index(
                guardrail_model
            ),
            "input_upper_guardrail_pct": upper_pct,
            "input_lower_guardrail_pct": lower_pct,
            "input_upper_guardrail": upper_adj,
            "input_lower_guardrail": lower_adj,
        }
    )

    return SimulationParams(
        initial_portfolio=initial_portfolio,
        annual_spending=annual_spending,
        mean_return=mean_return / 100.0,
        return_std=return_std / 100.0,
        mean_inflation=mean_inflation / 100.0,
        inflation_std=inflation_std / 100.0,
        years=int(years),
        num_simulations=int(num_simulations),
        random_seed=random_seed,
        guardrail_model=GuardrailModel(guardrail_model),
        upper_guardrail=upper_adj / 100.0,
        lower_guardrail=lower_adj / 100.0,
        upper_guardrail_pct=upper_pct,
        lower_guardrail_pct=lower_pct,
    )


def _prefill_from_spreadsheet(uploaded_file) -> None:
    """Placeholder: parse spreadsheet and update session_state fields.

    This function is a scaffold — full Excel parsing will be implemented
    once the spreadsheet format is finalized.
    """
    # TODO: implement when spreadsheet format is finalized
    # Example stub:
    # import pandas as pd
    # df = pd.read_excel(uploaded_file, sheet_name="Inputs")
    # st.session_state["input_initial_portfolio"] = df.loc[0, "Portfolio"]
    pass
