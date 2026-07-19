"""Scenario management sidebar UI (spec §2.4).

Provides save/load controls rendered in the Streamlit sidebar.
Scenarios are stored in ``st.session_state["scenarios"]`` (max 5).
Each entry is a dict: ``{name: str, inputs: SimulationInputs, results: SimulationResults | None}``.

This module, along with app.py, ui/inputs.py, and ui/outputs.py, imports Streamlit.
"""

from __future__ import annotations

from copy import deepcopy

import streamlit as st

from simulation.models import SimulationInputs
from utils.scenario_storage import (
    default_scenarios_dir,
    load_scenario_snapshots,
    save_scenario_snapshot,
)


def render_scenario_controls() -> None:
    """Render scenario save/load controls in the sidebar."""
    if not st.session_state.get("_scenario_storage_loaded", False):
        report = load_scenario_snapshots()
        loaded = sorted(
            report.scenarios,
            key=lambda s: str(s.get("saved_at_utc") or ""),
            reverse=True,
        )
        warnings = list(report.warnings)
        if len(loaded) > 5:
            ignored = len(loaded) - 5
            loaded = loaded[:5]
            warnings.append(
                f"Loaded most recent 5 scenarios; ignored {ignored} older persistent scenario(s)."
            )

        st.session_state["scenarios"] = loaded
        st.session_state["_scenario_storage_warnings"] = warnings
        st.session_state["_scenario_storage_loaded"] = True
        st.session_state["_scenario_storage_recovered_count"] = report.recovered_count
        st.session_state["_scenario_storage_skipped_count"] = report.skipped_count

    if "scenarios" not in st.session_state:
        st.session_state["scenarios"] = []

    scenarios: list[dict] = st.session_state["scenarios"]

    st.markdown("##### Scenario Management")

    # ── Save ──────────────────────────────────────────────────────────────────
    c1, c2 = st.columns([3, 1])
    with c1:
        name = st.text_input(
            "Save current inputs as",
            placeholder="Scenario name…",
            key="_scenario_name",
            label_visibility="collapsed",
        )
    with c2:
        save_clicked = st.button("Save", width="stretch")

    if save_clicked and name and name.strip():
        inputs = st.session_state.get("_assembled_inputs")
        if inputs is None:
            st.warning("Fix input errors before saving.")
        else:
            # Remove existing scenario with same name first (allows replacement at capacity)
            scenarios = [s for s in scenarios if s["name"] != name.strip()]
            if len(scenarios) >= 5:
                st.warning("Maximum 5 scenarios. Delete one first.")
                st.session_state["scenarios"] = scenarios
                return
            # Only save results if they match the current inputs (not stale)
            current_results = st.session_state.get("results")
            if st.session_state.get("results_stale", False):
                current_results = None
            scenarios.append({
                "name": name.strip(),
                "inputs": deepcopy(inputs),
                "results": current_results,  # no deepcopy; results are replaced, not mutated
            })
            st.session_state["scenarios"] = scenarios
            try:
                save_scenario_snapshot(
                    name=name.strip(),
                    inputs=inputs,
                    results=current_results,
                )
                st.success(f"Saved: {name.strip()} (persistent)")
            except Exception as exc:
                st.warning(
                    "Saved for this session, but persistent write failed: "
                    f"{exc}"
                )

    # ── Load ──────────────────────────────────────────────────────────────────
    if scenarios:
        names = ["— Select saved scenario —"] + [s["name"] for s in scenarios]
        choice = st.selectbox(
            "Load Scenario",
            options=names,
            index=0,
            key="_scenario_load",
            label_visibility="collapsed",
        )
        if choice != names[0]:
            match = next((s for s in scenarios if s["name"] == choice), None)
            if match:
                if st.button("Load", width="stretch"):
                    _restore_inputs(match["inputs"])
                    if match.get("results") is not None:
                        st.session_state["results"] = match["results"]
                        st.session_state["results_stale"] = False
                        # Sync hash so stale detection doesn't immediately re-trigger
                        st.session_state["_last_inputs_hash"] = match["inputs"].content_hash()
                    else:
                        st.session_state.pop("results", None)
                        st.session_state["results_stale"] = False
                        st.session_state.pop("_last_inputs_hash", None)
                    st.rerun()

        st.caption(f"{len(scenarios)} of 5 slots used")
    else:
        st.caption("No saved scenarios.")

    warning_lines = st.session_state.get("_scenario_storage_warnings", [])
    if warning_lines:
        st.warning("Some saved scenario packages were skipped or recovered:")
        for line in warning_lines:
            st.caption(f"- {line}")

    storage_path = default_scenarios_dir()
    st.caption(f"Persistent store: {storage_path}")


def _restore_inputs(inputs: SimulationInputs) -> None:
    """Write a SimulationInputs back into session_state widget keys."""
    s = st.session_state

    # Portfolio
    s["port_start"] = inputs.port_start
    s["taxable_value"] = inputs.taxable_value
    s["tax_deferred_value"] = inputs.tax_deferred_value
    s["roth_value"] = inputs.roth_value
    s["unrealized_gain_pct"] = inputs.unrealized_gain_pct * 100.0

    # Tax rate dropdowns — map numeric rates to label strings without
    # importing private constants from ui.inputs.
    _ltcg_map = {0.0: "0%", 0.15: "15%", 0.20: "20%", 0.238: "23.8% (incl. NIIT)"}
    _ord_map = {0.10: "10%", 0.12: "12%", 0.22: "22%", 0.24: "24%",
                0.32: "32%", 0.35: "35%", 0.37: "37%"}
    if inputs.ltcg_rate in _ltcg_map:
        s["ltcg_idx_sel"] = _ltcg_map[inputs.ltcg_rate]
    if inputs.ord_income_rate in _ord_map:
        s["ord_idx_sel"] = _ord_map[inputs.ord_income_rate]

    # Personal
    s["current_age"] = inputs.current_age
    s["retire_age"] = inputs.retire_age
    s["ss_start_age"] = inputs.ss_start_age
    s["plan_years"] = inputs.plan_years
    s["filing_status"] = inputs.filing_status

    # Spending tiers — clear stale per-tier widget keys before restoring
    old_count = len(s.get("spending_tiers", []))
    for j in range(max(old_count, 5)):
        for suffix in ("start", "end", "spend"):
            s.pop(f"tier_{j}_{suffix}", None)
    s["spending_tiers"] = [
        {"start_age": t.start_age, "end_age": t.end_age, "annual_spend": t.annual_spend}
        for t in inputs.spending_tiers
    ]
    s["spend_floor"] = inputs.spend_floor
    s["spend_ceiling"] = inputs.spend_ceiling

    # Social Security
    s["ss_enabled"] = inputs.ss_enabled
    s["ss_annual"] = inputs.ss_annual
    s["ss_cola"] = inputs.ss_cola * 100.0

    # Health
    s["medicare_age"] = inputs.health.medicare_age
    s["medicare_premium"] = inputs.health.medicare_premium
    s["aca_guardrail_enabled"] = inputs.health.aca_guardrail_enabled
    s["aca_magi_cliff"] = inputs.health.aca_magi_cliff
    s["aca_magi_target"] = inputs.health.aca_magi_target
    s["aca_premium_over"] = inputs.health.aca_premium_over
    s["aca_premium_under"] = inputs.health.aca_premium_under

    # Market — set preset to "Custom" so auto-fill doesn't overwrite restored values
    s["preset_sel"] = "Custom"
    s["_prev_preset"] = "Custom"
    s["ret_mean_pct"] = inputs.ret_mean * 100.0
    s["ret_std_pct"] = inputs.ret_std * 100.0
    s["ret_inf_corr"] = inputs.ret_inf_corr
    s["inf_mean_pct"] = inputs.inf_mean * 100.0
    s["inf_std_pct"] = inputs.inf_std * 100.0
    s["inf_floor_pct"] = inputs.inf_floor * 100.0
    s["n_paths"] = inputs.n_paths
    s["random_seed"] = inputs.random_seed

    # Guardrails (gr1=Portfolio Value, gr2=Withdrawal Rate, gr3=ACA MAGI, gr4=Inflation)
    s["gr1_enabled"] = inputs.gr1.enabled
    s["gr1_floor_pct"] = inputs.gr1.floor_pct * 100.0
    s["gr1_ceil_pct"] = inputs.gr1.ceil_pct * 100.0
    s["gr1_cut_pct"] = inputs.gr1.cut_pct * 100.0
    s["gr1_raise_pct"] = inputs.gr1.raise_pct * 100.0
    s["gr2_enabled"] = inputs.gr2.enabled
    s["gr2_low_rate"] = inputs.gr2.low_rate * 100.0
    s["gr2_warn_rate"] = inputs.gr2.warn_rate * 100.0
    s["gr2_crit_rate"] = inputs.gr2.crit_rate * 100.0
    s["gr2_low_raise"] = inputs.gr2.low_raise * 100.0
    s["gr2_warn_cut"] = inputs.gr2.warn_cut * 100.0
    s["gr2_crit_cut"] = inputs.gr2.crit_cut * 100.0
    s["gr3_enabled"] = inputs.gr3.enabled
    s["gr4_enabled"] = inputs.gr4.enabled
    s["gr4_inf_trigger"] = inputs.gr4.inf_trigger * 100.0
    s["gr4_cut_pct"] = inputs.gr4.cut_pct * 100.0
