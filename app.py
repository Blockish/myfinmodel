"""Monte Carlo Retirement Planner — Streamlit application entry point.

Wires the inputs UI, simulation engine, and results display together.
See docs/ui-mockup.html for the visual layout reference.
"""

from __future__ import annotations

import time
import os
from typing import TYPE_CHECKING

import streamlit as st
import streamlit.components.v1 as components

from ui.inputs import render_inputs
from ui.scenarios import render_scenario_controls

if TYPE_CHECKING:
    from simulation.models import SimulationInputs, SimulationResults


# ──────────────────────────────────────────────────────────────────────────────
# Page configuration
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="MyFinModel — Retirement Monte Carlo",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _inject_ui_polish_css() -> None:
    """Apply global UI typography polish for tabs, inputs, and data tables."""
    st.markdown(
        """
        <style>
        div[data-testid="stTabs"] button[data-baseweb="tab"] p {
            font-size: 1.2rem !important;
            font-weight: 700 !important;
        }
        div[data-testid="stTextInput"] input,
        div[data-testid="stNumberInput"] input,
        div[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
        div[data-testid="stMultiSelect"] div[data-baseweb="select"] > div {
            font-size: 1rem !important;
        }
        div[data-testid="stDataFrame"] [role="columnheader"],
        div[data-testid="stDataFrame"] [role="gridcell"] {
            font-size: 0.95rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


_inject_ui_polish_css()


def _inject_shutdown_beacon() -> None:
        control_port = os.environ.get("MYFINMODEL_SHUTDOWN_CONTROL_PORT")
        token = os.environ.get("MYFINMODEL_SHUTDOWN_TOKEN")
        if not control_port or not token:
                return

        components.html(
                f"""
                <script>
                (() => {{
                    const shutdownUrl = 'http://127.0.0.1:{control_port}/shutdown/{token}';
                    const sendShutdown = () => {{
                        try {{
                            navigator.sendBeacon(shutdownUrl, new Blob(['close'], {{ type: 'text/plain' }}));
                        }} catch (error) {{
                            try {{
                                fetch(shutdownUrl, {{ method: 'POST', mode: 'no-cors', keepalive: true }});
                            }} catch (ignored) {{}}
                        }}
                    }};
                    window.addEventListener('pagehide', sendShutdown);
                    window.addEventListener('beforeunload', sendShutdown);
                }})();
                </script>
                """,
                height=0,
                width=0,
        )


_inject_shutdown_beacon()


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("💰 MyFinModel")
    st.caption("Retirement Spending Monte Carlo Simulator")
    st.divider()

    # Scenario save/load controls
    render_scenario_controls()

    st.divider()

    # Run Simulation button — always visible in sidebar
    run_clicked = st.button(
        "▶ Run Simulation",
        type="primary",
        width="stretch",
    )

    st.divider()

    st.markdown(
        """
        **How to use**
        1. Configure your retirement scenario on the **Inputs** tab.
        2. Click **▶ Run Simulation**.
        3. Review results on the **Results** tab.
        4. Save scenarios to compare different strategies.
        """
    )


# ──────────────────────────────────────────────────────────────────────────────
# Main tabs
# ──────────────────────────────────────────────────────────────────────────────

tabs = st.tabs(["📋 Inputs", "📊 Results"])

# ── Tab 0: Inputs ─────────────────────────────────────────────────────────────
with tabs[0]:
    render_inputs()

# ── Stale detection: mark results stale when inputs change ────────────────────
current_inputs = st.session_state.get("_assembled_inputs")
existing_results = st.session_state.get("results")
if existing_results is not None:
    # Derive reference hash from the inputs that produced the current results
    ref_hash = st.session_state.get(
        "_last_inputs_hash", existing_results.inputs.content_hash()
    )
    if current_inputs is None or current_inputs.content_hash() != ref_hash:
        st.session_state["results_stale"] = True
    else:
        # Inputs match again (user reverted changes) — clear stale flag
        st.session_state["results_stale"] = False

# ── Handle Run button click ───────────────────────────────────────────────────
if run_clicked:
    # Import simulation engine only when user runs a scenario to avoid heavy
    # NumPy/SciPy startup cost during initial app boot.
    from simulation.engine import run_simulation

    inputs: SimulationInputs | None = st.session_state.get("_assembled_inputs")
    if inputs is None:
        st.sidebar.error("Fix input errors before running.")
    else:
        # Generate a random seed if not locked
        if not st.session_state.get("lock_seed", False):
            import random
            inputs.random_seed = random.randint(0, 999_999)
            st.session_state["random_seed"] = inputs.random_seed

        with st.spinner("Running simulation…"):
            t0 = time.perf_counter()
            results = run_simulation(inputs)
            elapsed = time.perf_counter() - t0

        st.session_state["results"] = results
        st.session_state["results_stale"] = False
        st.session_state["_last_inputs_hash"] = inputs.content_hash()
        st.session_state["last_runtime"] = elapsed
        st.sidebar.success(
            f"✅ Done — {inputs.n_paths:,} paths × {inputs.plan_years} years "
            f"in {elapsed:.2f}s"
        )

# ── Tab 1: Results ────────────────────────────────────────────────────────────
with tabs[1]:
    results_obj: SimulationResults | None = st.session_state.get("results")

    # Stale results banner
    if st.session_state.get("results_stale") and results_obj is not None:
        st.warning(
            "⚠ Inputs changed — click **Run Simulation** to refresh results.",
            icon="⚠️",
        )

    if results_obj is None:
        st.info(
            "👈 Configure inputs and click **▶ Run Simulation** to see results here."
        )
    else:
        # Run metadata row
        elapsed = st.session_state.get("last_runtime", 0)
        meta_cols = st.columns(5)
        meta_cols[0].metric("Paths", f"{results_obj.n_paths:,}")
        meta_cols[1].metric("Years", str(results_obj.plan_years))
        meta_cols[2].metric("Seed", str(results_obj.inputs.random_seed))
        meta_cols[3].metric("Runtime", f"{elapsed:.2f}s")
        with meta_cols[4]:
            if st.button("🔄 Re-run"):
                inputs_rerun = st.session_state.get("_assembled_inputs")
                if inputs_rerun:
                    with st.spinner("Re-running…"):
                        t0 = time.perf_counter()
                        results_obj = run_simulation(inputs_rerun)
                        st.session_state["results"] = results_obj
                        st.session_state["last_runtime"] = time.perf_counter() - t0
                        st.session_state["results_stale"] = False
                        st.session_state["_last_inputs_hash"] = inputs_rerun.content_hash()
                    st.rerun()

        st.divider()

        # Import results UI lazily so Plotly/Pandas modules do not slow first boot.
        from ui.outputs import render_outputs

        # Results display (placeholder — will be fully implemented in Phase 4)
        render_outputs(results_obj)
