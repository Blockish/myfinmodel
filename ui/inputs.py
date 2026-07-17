"""Inputs tab UI for the Monte Carlo retirement planner.

Renders 7 collapsible sections per spec §2.1–2.2 and the ui-mockup.html
layout reference.  Assembles and validates a ``SimulationInputs`` on every
Streamlit rerun, storing the result in ``st.session_state["_assembled_inputs"]``.
Returns the validated inputs (or None if validation fails).

This module, along with app.py, ui/scenarios.py, and ui/outputs.py,
imports Streamlit.
"""

from __future__ import annotations

import streamlit as st

from simulation.models import (
    GuardrailGR1Config,
    GuardrailGR2Config,
    GuardrailGR3Config,
    GuardrailGR4Config,
    HealthInsuranceConfig,
    SimulationInputs,
    SpendingTier,
)
from validation.validators import validate_inputs

# ── Portfolio style presets (spec §2.2.6) ─────────────────────────────────────

_PRESETS: dict[str, dict[str, float]] = {
    "Conservative (Capital Preservation)": {"ret_mean": 0.045, "ret_std": 0.07},
    "Moderate (Balanced)": {"ret_mean": 0.055, "ret_std": 0.095},
    "Growth (Balanced Growth)": {"ret_mean": 0.065, "ret_std": 0.12},
    "Aggressive Growth": {"ret_mean": 0.08, "ret_std": 0.15},
    "Equity Only": {"ret_mean": 0.095, "ret_std": 0.18},
    "Custom": {"ret_mean": 0.065, "ret_std": 0.12},
}

_PRESET_DESCRIPTIONS: dict[str, str] = {
    "Conservative (Capital Preservation)": "Mostly bonds/fixed income; low growth, low risk.",
    "Moderate (Balanced)": "40/60 to 50/50 equity/bond blend.",
    "Growth (Balanced Growth)": "60/40 equity/bond; classic retirement allocation.",
    "Aggressive Growth": "80%+ equity; higher upside, higher sequence-of-returns risk.",
    "Equity Only": "100% equities; maximum long-run growth, maximum volatility.",
    "Custom": "Enter your own return and volatility assumptions.",
}

_LTCG_OPTIONS = [0.0, 0.15, 0.20, 0.238]
_LTCG_LABELS = ["0%", "15%", "20%", "23.8% (incl. NIIT)"]

_ORD_OPTIONS = [0.10, 0.12, 0.22, 0.24, 0.32, 0.35, 0.37]
_ORD_LABELS = ["10%", "12%", "22%", "24%", "32%", "35%", "37%"]


def _format_money(value: float) -> str:
    return f"{float(value):,.0f}"


def _parse_money(raw: str) -> float | None:
    cleaned = raw.strip().replace("$", "").replace(",", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _money_input(
    label: str,
    *,
    key: str,
    default: float,
    min_value: float = 0.0,
    max_value: float | None = None,
    help: str | None = None,
) -> float:
    """Render a dollar input with thousands separators normalized on rerun."""
    s = st.session_state
    raw_key = f"{key}_text"

    if key not in s:
        s[key] = float(default)

    if raw_key not in s:
        s[raw_key] = _format_money(float(s[key]))
    else:
        parsed_existing = _parse_money(str(s[raw_key]))
        if parsed_existing is not None:
            if max_value is not None:
                parsed_existing = min(parsed_existing, max_value)
            parsed_existing = max(parsed_existing, min_value)
            s[key] = float(parsed_existing)
            s[raw_key] = _format_money(parsed_existing)
        else:
            # Keep displayed text consistent with the last valid numeric state.
            s[raw_key] = _format_money(float(s[key]))

    raw = st.text_input(label, key=raw_key, help=help)
    parsed = _parse_money(raw)
    if parsed is not None:
        if max_value is not None:
            parsed = min(parsed, max_value)
        parsed = max(parsed, min_value)
        s[key] = float(parsed)
        s[raw_key] = _format_money(parsed)
    else:
        # If user enters invalid text, snap back to last valid formatted value.
        s[raw_key] = _format_money(float(s[key]))

    return float(s[key])


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════


def render_inputs() -> SimulationInputs | None:
    """Render the full Inputs tab and return validated inputs.

    Called on every Streamlit rerun.  Returns a ``SimulationInputs`` when
    the current widget state passes validation, or ``None`` when validation
    produces blocking errors.  The sidebar Run button in ``app.py`` reads
    the assembled inputs from ``st.session_state["_assembled_inputs"]``.
    """
    st.header("📋 Simulation Inputs")

    # ── Section 1: Portfolio ──────────────────────────────────────────────────
    _render_portfolio_section()

    # ── Section 2: Personal Information ───────────────────────────────────────
    _render_personal_section()

    # ── Section 3: Spending ───────────────────────────────────────────────────
    _render_spending_section()

    # ── Section 4: Social Security ────────────────────────────────────────────
    _render_social_security_section()

    # ── Section 5: Health Insurance ───────────────────────────────────────────
    _render_health_insurance_section()

    # ── Section 6: Portfolio Style / Market Assumptions ───────────────────────
    _render_market_section()

    # ── Section 7: Guardrail Thresholds ───────────────────────────────────────
    _render_guardrail_section()

    # ── Assemble and validate ─────────────────────────────────────────────────
    return _assemble_and_validate()


# ══════════════════════════════════════════════════════════════════════════════
# Section renderers
# ══════════════════════════════════════════════════════════════════════════════


def _render_portfolio_section() -> None:
    with st.expander("💼 Portfolio", expanded=True):
        _money_input(
            "Starting Portfolio Value ($)",
            key="port_start",
            default=st.session_state.get("port_start", 1_000_000.0),
            min_value=0.0,
            max_value=50_000_000.0,
            help="Total investable assets at retirement start.",
        )

        st.markdown("**Account Breakdown**")
        c1, c2, c3 = st.columns(3)
        with c1:
            _money_input(
                "Taxable Account ($)",
                key="taxable_value",
                default=st.session_state.get("taxable_value", 0.0),
                min_value=0.0,
            )
        with c2:
            _money_input(
                "Tax-Deferred — IRA/401k ($)",
                key="tax_deferred_value",
                default=st.session_state.get("tax_deferred_value", 0.0),
                min_value=0.0,
            )
        with c3:
            _money_input(
                "Roth ($)",
                key="roth_value",
                default=st.session_state.get("roth_value", 0.0),
                min_value=0.0,
            )

        # Account sum advisory check is handled by validate_inputs() (W1)
        # to avoid duplicate warnings.

        c1, c2, c3 = st.columns(3)
        with c1:
            st.slider(
                "Unrealized Gain % (Taxable)",
                min_value=0.0,
                max_value=100.0,
                value=st.session_state.get("unrealized_gain_pct", 30.0),
                step=1.0,
                format="%.0f%%",
                key="unrealized_gain_pct",
                help="Fraction of taxable account representing embedded capital gains.",
            )
        with c2:
            ltcg_idx = st.session_state.get("ltcg_idx", 1)
            st.selectbox(
                "LTCG Tax Rate",
                options=_LTCG_LABELS,
                index=ltcg_idx,
                key="ltcg_idx_sel",
                help="Federal long-term capital gains rate on taxable account.",
            )
        with c3:
            ord_idx = st.session_state.get("ord_idx", 2)
            st.selectbox(
                "Ordinary Income Tax Rate",
                options=_ORD_LABELS,
                index=ord_idx,
                key="ord_idx_sel",
                help="Marginal rate applied to IRA/401k withdrawals.",
            )


def _render_personal_section() -> None:
    with st.expander("👤 Personal Information", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.number_input(
                "Current Age",
                min_value=18,
                max_value=85,
                value=st.session_state.get("current_age", 65),
                step=1,
                key="current_age",
            )
        with c2:
            st.number_input(
                "Retirement Start Age",
                min_value=18,
                max_value=85,
                value=st.session_state.get("retire_age", 65),
                step=1,
                key="retire_age",
                help="Age at which portfolio withdrawals begin.",
            )
        with c3:
            st.selectbox(
                "Filing Status",
                options=["Single", "Married Filing Jointly"],
                index=0 if st.session_state.get("filing_status", "Single") == "Single" else 1,
                key="filing_status",
            )

        c1, c2 = st.columns(2)
        with c1:
            st.slider(
                "Social Security Start Age",
                min_value=62,
                max_value=70,
                value=st.session_state.get("ss_start_age", 67),
                step=1,
                key="ss_start_age",
                help="62 = reduced benefit, 67 = FRA, 70 = maximum delayed.",
            )
        with c2:
            plan_years = st.number_input(
                "Planning Horizon (years)",
                min_value=5,
                max_value=50,
                value=st.session_state.get("plan_years", 35),
                step=1,
                key="plan_years",
            )
            retire = st.session_state.get("retire_age", 65)
            st.caption(f"Plan through age {retire + plan_years - 1}")


def _render_spending_section() -> None:
    with st.expander("💸 Spending", expanded=True):
        st.markdown("**Spending Tiers** *(real dollars)*")

        # Initialize tiers in session state
        if "spending_tiers" not in st.session_state:
            retire = st.session_state.get("retire_age", 65)
            plan_yrs = st.session_state.get("plan_years", 35)
            st.session_state["spending_tiers"] = [
                {"start_age": retire, "end_age": retire + plan_yrs - 1, "annual_spend": 50_000.0}
            ]

        tiers = st.session_state["spending_tiers"]

        for i, tier in enumerate(tiers):
            c1, c2, c3, c4 = st.columns([1, 1, 2, 0.5])
            with c1:
                tier["start_age"] = st.number_input(
                    "Start Age",
                    min_value=18,
                    max_value=135,
                    value=tier["start_age"],
                    step=1,
                    key=f"tier_{i}_start",
                )
            with c2:
                tier["end_age"] = st.number_input(
                    "End Age",
                    min_value=18,
                    max_value=135,
                    value=tier["end_age"],
                    step=1,
                    key=f"tier_{i}_end",
                )
            with c3:
                tier["annual_spend"] = _money_input(
                    "Annual Spending ($)",
                    key=f"tier_{i}_spend",
                    default=float(tier["annual_spend"]),
                    min_value=0.0,
                    max_value=2_000_000.0,
                )
            with c4:
                st.markdown("<br>", unsafe_allow_html=True)
                if len(tiers) > 1:
                    if st.button("✕", key=f"tier_{i}_remove"):
                        # Clear stale widget keys before removing
                        for j in range(len(tiers)):
                            for suffix in ("start", "end", "spend"):
                                st.session_state.pop(f"tier_{j}_{suffix}", None)
                                st.session_state.pop(f"tier_{j}_{suffix}_text", None)
                        tiers.pop(i)
                        st.rerun()

        if len(tiers) < 5:
            if st.button("+ Add Tier"):
                last = tiers[-1]
                new_start = min(last["end_age"] + 1, 135)
                new_end = min(last["end_age"] + 10, 135)
                tiers.append({
                    "start_age": new_start,
                    "end_age": new_end,
                    "annual_spend": last["annual_spend"],
                })
                st.rerun()

        st.markdown("**Spending Floor & Ceiling** *(real dollars)*")
        c1, c2 = st.columns(2)
        with c1:
            _money_input(
                "Spending Floor — minimum after guardrails ($)",
                key="spend_floor",
                default=st.session_state.get("spend_floor", 20_000.0),
                min_value=0.0,
                max_value=2_000_000.0,
            )
        with c2:
            _money_input(
                "Spending Ceiling — maximum after guardrails ($)",
                key="spend_ceiling",
                default=st.session_state.get("spend_ceiling", 100_000.0),
                min_value=0.0,
                max_value=2_000_000.0,
            )


def _render_social_security_section() -> None:
    with st.expander("🏛 Social Security", expanded=False):
        ss_enabled = st.toggle(
            "Enable Social Security",
            value=st.session_state.get("ss_enabled", True),
            key="ss_enabled",
        )

        if ss_enabled:
            c1, c2 = st.columns(2)
            with c1:
                _money_input(
                    "Annual SS Benefit at Claiming Age ($)",
                    key="ss_annual",
                    default=st.session_state.get("ss_annual", 24_000.0),
                    min_value=0.0,
                    max_value=60_000.0,
                    help="Gross SS benefit in today's dollars.",
                )
            with c2:
                st.slider(
                    "SS COLA Rate (%)",
                    min_value=0.0,
                    max_value=5.0,
                    value=st.session_state.get("ss_cola", 2.5),
                    step=0.1,
                    format="%.1f%%",
                    key="ss_cola",
                    help="Annual cost-of-living adjustment.",
                )


def _render_health_insurance_section() -> None:
    with st.expander("🏥 Health Insurance", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            st.number_input(
                "Medicare Start Age",
                min_value=60,
                max_value=70,
                value=st.session_state.get("medicare_age", 65),
                step=1,
                key="medicare_age",
            )
        with c2:
            _money_input(
                "Annual Medicare Premium ($)",
                key="medicare_premium",
                default=st.session_state.get("medicare_premium", 3_600.0),
                min_value=0.0,
                max_value=20_000.0,
                help="Combined Part B + Part D annual premium (today's dollars).",
            )

        aca_enabled = st.toggle(
            "Enable ACA MAGI Guardrail",
            value=st.session_state.get("aca_guardrail_enabled", True),
            key="aca_guardrail_enabled",
        )

        if aca_enabled:
            c1, c2 = st.columns(2)
            with c1:
                _money_input(
                    "ACA MAGI Cliff ($)",
                    key="aca_magi_cliff",
                    default=st.session_state.get("aca_magi_cliff", 62_000.0),
                    min_value=20_000.0,
                    max_value=200_000.0,
                    help="Income threshold above which ACA subsidies are lost (400% FPL).",
                )
                _money_input(
                    "Annual Premium if Over Cliff ($)",
                    key="aca_premium_over",
                    default=st.session_state.get("aca_premium_over", 18_000.0),
                    min_value=0.0,
                    max_value=60_000.0,
                )
            with c2:
                _money_input(
                    "ACA Safe Target MAGI ($)",
                    key="aca_magi_target",
                    default=st.session_state.get("aca_magi_target", 58_000.0),
                    min_value=0.0,
                    max_value=200_000.0,
                    help="Target MAGI for full subsidy preservation.",
                )
                _money_input(
                    "Annual Premium if Under Cliff ($)",
                    key="aca_premium_under",
                    default=st.session_state.get("aca_premium_under", 4_800.0),
                    min_value=0.0,
                    max_value=60_000.0,
                )


def _render_market_section() -> None:
    with st.expander("📊 Portfolio Style / Market Assumptions", expanded=False):
        preset_names = list(_PRESETS.keys())
        preset = st.selectbox(
            "Portfolio Style Preset",
            options=preset_names,
            index=st.session_state.get("preset_idx", 2),
            key="preset_sel",
            help="Selecting a preset auto-fills return and volatility sliders.",
        )
        st.session_state["preset_idx"] = preset_names.index(preset)
        desc = _PRESET_DESCRIPTIONS[preset]
        st.info(
            f"**{preset}** — {desc}\n\n"
            "*These are long-run historical approximations. "
            "Actual future returns may differ materially.*"
        )

        # Auto-fill from preset: only apply when the preset selection changes,
        # so manual slider adjustments are preserved across reruns.
        p = _PRESETS[preset]
        prev_preset = st.session_state.get("_prev_preset")
        if preset != "Custom" and preset != prev_preset:
            st.session_state["ret_mean_pct"] = p["ret_mean"] * 100
            st.session_state["ret_std_pct"] = p["ret_std"] * 100
        st.session_state["_prev_preset"] = preset
        default_ret = st.session_state.get("ret_mean_pct", 6.5)
        default_std = st.session_state.get("ret_std_pct", 12.0)

        c1, c2 = st.columns(2)
        with c1:
            st.slider(
                "Expected Annual Return (%)",
                min_value=1.0,
                max_value=15.0,
                value=default_ret,
                step=0.1,
                format="%.1f%%",
                key="ret_mean_pct",
            )
        with c2:
            st.slider(
                "Return Standard Deviation (%)",
                min_value=1.0,
                max_value=30.0,
                value=default_std,
                step=0.1,
                format="%.1f%%",
                key="ret_std_pct",
            )

        st.slider(
            "Return–Inflation Correlation",
            min_value=-0.50,
            max_value=0.80,
            value=st.session_state.get("ret_inf_corr", 0.10),
            step=0.01,
            format="%.2f",
            key="ret_inf_corr",
        )

        c1, c2, c3 = st.columns(3)
        with c1:
            st.slider(
                "Inflation Mean (%)",
                min_value=0.0,
                max_value=10.0,
                value=st.session_state.get("inf_mean_pct", 3.0),
                step=0.1,
                format="%.1f%%",
                key="inf_mean_pct",
            )
        with c2:
            st.slider(
                "Inflation Std Dev (%)",
                min_value=0.0,
                max_value=5.0,
                value=st.session_state.get("inf_std_pct", 1.5),
                step=0.1,
                format="%.1f%%",
                key="inf_std_pct",
            )
        with c3:
            st.slider(
                "Inflation Floor (%)",
                min_value=0.0,
                max_value=10.0,
                value=st.session_state.get("inf_floor_pct", 1.0),
                step=0.1,
                format="%.1f%%",
                key="inf_floor_pct",
            )

        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            st.slider(
                "Simulation Paths",
                min_value=100,
                max_value=10_000,
                value=st.session_state.get("n_paths", 1_000),
                step=100,
                key="n_paths",
            )
        with c2:
            lock_seed = st.toggle(
                "Lock random seed",
                value=st.session_state.get("lock_seed", False),
                key="lock_seed",
                help="When off, a new random seed is chosen each run. Turn on to fix the seed for reproducible results.",
            )
            if lock_seed:
                st.number_input(
                    "Random Seed",
                    min_value=0,
                    max_value=999_999,
                    value=st.session_state.get("random_seed", 42),
                    step=1,
                    key="random_seed",
                )


def _render_guardrail_section() -> None:
    with st.expander("🛡 Guardrail Thresholds", expanded=False):

        # ── Inflation Guardrail ───────────────────────────────────────────
        st.markdown("---")
        inf_enabled = st.toggle(
            "**Inflation Guardrail**",
            value=st.session_state.get("gr4_enabled", True),
            key="gr4_enabled",
        )
        if inf_enabled:
            st.slider(
                "Inflation Trigger Rate (%)",
                min_value=2.0,
                max_value=10.0,
                value=st.session_state.get("gr4_inf_trigger", 4.5),
                step=0.1,
                format="%.1f%%",
                key="gr4_inf_trigger",
            )
            st.slider(
                "Spending Cut %",
                min_value=2.0,
                max_value=20.0,
                value=st.session_state.get("gr4_cut_pct", 5.0),
                step=0.5,
                format="%.1f%%",
                key="gr4_cut_pct",
            )

        # ── Portfolio Value Guardrail ─────────────────────────────────────
        st.markdown("---")
        pv_enabled = st.toggle(
            "**Portfolio Value Guardrail**",
            value=st.session_state.get("gr1_enabled", True),
            key="gr1_enabled",
        )
        if pv_enabled:
            c1, c2 = st.columns(2)
            with c1:
                st.slider(
                    "Portfolio Floor (% of starting portfolio)",
                    min_value=10.0,
                    max_value=90.0,
                    value=st.session_state.get("gr1_floor_pct", 50.0),
                    step=1.0,
                    format="%.0f%%",
                    key="gr1_floor_pct",
                )
            with c2:
                st.slider(
                    "Portfolio Ceiling (% of starting portfolio)",
                    min_value=110.0,
                    max_value=300.0,
                    value=st.session_state.get("gr1_ceil_pct", 150.0),
                    step=5.0,
                    format="%.0f%%",
                    key="gr1_ceil_pct",
                )
            c1, c2 = st.columns(2)
            with c1:
                st.slider(
                    "Spending Cut %",
                    min_value=5.0,
                    max_value=30.0,
                    value=st.session_state.get("gr1_cut_pct", 10.0),
                    step=1.0,
                    format="%.0f%%",
                    key="gr1_cut_pct",
                )
            with c2:
                st.slider(
                    "Spending Raise %",
                    min_value=5.0,
                    max_value=30.0,
                    value=st.session_state.get("gr1_raise_pct", 10.0),
                    step=1.0,
                    format="%.0f%%",
                    key="gr1_raise_pct",
                )

        # ── Withdrawal Rate Guardrail ─────────────────────────────────────
        st.markdown("---")
        wr_enabled = st.toggle(
            "**Withdrawal Rate Guardrail**",
            value=st.session_state.get("gr2_enabled", True),
            key="gr2_enabled",
        )
        if wr_enabled:
            c1, c2, c3 = st.columns(3)
            with c1:
                st.slider(
                    "Low Rate (%)",
                    min_value=1.0,
                    max_value=8.0,
                    value=st.session_state.get("gr2_low_rate", 3.0),
                    step=0.1,
                    format="%.1f%%",
                    key="gr2_low_rate",
                )
            with c2:
                st.slider(
                    "Warning Rate (%)",
                    min_value=3.0,
                    max_value=8.0,
                    value=st.session_state.get("gr2_warn_rate", 5.0),
                    step=0.1,
                    format="%.1f%%",
                    key="gr2_warn_rate",
                )
            with c3:
                st.slider(
                    "Critical Rate (%)",
                    min_value=3.0,
                    max_value=12.0,
                    value=st.session_state.get("gr2_crit_rate", 6.5),
                    step=0.1,
                    format="%.1f%%",
                    key="gr2_crit_rate",
                )
            c1, c2, c3 = st.columns(3)
            with c1:
                st.slider(
                    "Low — raise spending (%)",
                    min_value=2.0,
                    max_value=20.0,
                    value=st.session_state.get("gr2_low_raise", 5.0),
                    step=0.5,
                    format="%.1f%%",
                    key="gr2_low_raise",
                )
            with c2:
                st.slider(
                    "Warn — cut spending (%)",
                    min_value=2.0,
                    max_value=20.0,
                    value=st.session_state.get("gr2_warn_cut", 5.0),
                    step=0.5,
                    format="%.1f%%",
                    key="gr2_warn_cut",
                )
            with c3:
                st.slider(
                    "Critical — cut spending (%)",
                    min_value=5.0,
                    max_value=40.0,
                    value=st.session_state.get("gr2_crit_cut", 15.0),
                    step=0.5,
                    format="%.1f%%",
                    key="gr2_crit_cut",
                )

        # ── ACA MAGI Guardrail ────────────────────────────────────────────
        aca_on = st.session_state.get("aca_guardrail_enabled", True)
        if aca_on:
            st.markdown("---")
            st.toggle(
                "**ACA MAGI Guardrail**",
                value=st.session_state.get("gr3_enabled", True),
                key="gr3_enabled",
                help="Conditional on ACA guardrail being enabled in Health Insurance section.",
            )
            st.caption(
                "ℹ MAGI estimation is a simplified heuristic. "
                "See documentation for assumptions and limitations."
            )


# ══════════════════════════════════════════════════════════════════════════════
# Assembly & validation
# ══════════════════════════════════════════════════════════════════════════════


def _assemble_and_validate() -> SimulationInputs | None:
    """Collect all widget values into SimulationInputs, validate, and return.

    Called every Streamlit rerun.  Returns the inputs object if valid,
    displays errors/warnings inline, and stores validation state.
    This does NOT trigger the simulation — the sidebar Run button does that.
    """
    s = st.session_state

    # Build spending tiers
    tier_dicts = s.get("spending_tiers", [])
    tiers = [
        SpendingTier(
            start_age=int(t["start_age"]),
            end_age=int(t["end_age"]),
            annual_spend=float(t["annual_spend"]),
        )
        for t in tier_dicts
    ]

    # Resolve dropdown indices to values (safe fallback for stale session_state)
    ltcg_sel = s.get("ltcg_idx_sel", _LTCG_LABELS[1])
    try:
        ltcg_rate = _LTCG_OPTIONS[_LTCG_LABELS.index(ltcg_sel)]
    except ValueError:
        ltcg_rate = 0.15  # default 15%

    ord_sel = s.get("ord_idx_sel", _ORD_LABELS[2])
    try:
        ord_rate = _ORD_OPTIONS[_ORD_LABELS.index(ord_sel)]
    except ValueError:
        ord_rate = 0.22  # default 22%

    health = HealthInsuranceConfig(
        medicare_age=int(s.get("medicare_age", 65)),
        medicare_premium=float(s.get("medicare_premium", 3_600.0)),
        aca_guardrail_enabled=bool(s.get("aca_guardrail_enabled", True)),
        aca_magi_cliff=float(s.get("aca_magi_cliff", 62_000.0)),
        aca_magi_target=float(s.get("aca_magi_target", 58_000.0)),
        aca_premium_over=float(s.get("aca_premium_over", 18_000.0)),
        aca_premium_under=float(s.get("aca_premium_under", 4_800.0)),
    )

    inputs = SimulationInputs(
        port_start=float(s.get("port_start", 1_000_000.0)),
        taxable_value=float(s.get("taxable_value", 0.0)),
        tax_deferred_value=float(s.get("tax_deferred_value", 0.0)),
        roth_value=float(s.get("roth_value", 0.0)),
        unrealized_gain_pct=float(s.get("unrealized_gain_pct", 30.0)) / 100.0,
        ltcg_rate=ltcg_rate,
        ord_income_rate=ord_rate,
        current_age=int(s.get("current_age", 65)),
        retire_age=int(s.get("retire_age", 65)),
        ss_start_age=int(s.get("ss_start_age", 67)),
        plan_years=int(s.get("plan_years", 35)),
        filing_status=str(s.get("filing_status", "Single")),
        spending_tiers=tiers,
        spend_floor=float(s.get("spend_floor", 20_000.0)),
        spend_ceiling=float(s.get("spend_ceiling", 100_000.0)),
        ss_enabled=bool(s.get("ss_enabled", True)),
        ss_annual=float(s.get("ss_annual", 24_000.0)),
        ss_cola=float(s.get("ss_cola", 2.5)) / 100.0,
        health=health,
        ret_mean=float(s.get("ret_mean_pct", 6.5)) / 100.0,
        ret_std=float(s.get("ret_std_pct", 12.0)) / 100.0,
        ret_inf_corr=float(s.get("ret_inf_corr", 0.10)),
        inf_mean=float(s.get("inf_mean_pct", 3.0)) / 100.0,
        inf_std=float(s.get("inf_std_pct", 1.5)) / 100.0,
        inf_floor=float(s.get("inf_floor_pct", 1.0)) / 100.0,
        n_paths=int(s.get("n_paths", 1_000)),
        random_seed=int(s.get("random_seed", 42)),
        gr1=GuardrailGR1Config(
            enabled=bool(s.get("gr1_enabled", True)),
            floor_pct=float(s.get("gr1_floor_pct", 50.0)) / 100.0,
            ceil_pct=float(s.get("gr1_ceil_pct", 150.0)) / 100.0,
            cut_pct=float(s.get("gr1_cut_pct", 10.0)) / 100.0,
            raise_pct=float(s.get("gr1_raise_pct", 10.0)) / 100.0,
        ),
        gr2=GuardrailGR2Config(
            enabled=bool(s.get("gr2_enabled", True)),
            low_rate=float(s.get("gr2_low_rate", 3.0)) / 100.0,
            warn_rate=float(s.get("gr2_warn_rate", 5.0)) / 100.0,
            crit_rate=float(s.get("gr2_crit_rate", 6.5)) / 100.0,
            low_raise=float(s.get("gr2_low_raise", 5.0)) / 100.0,
            warn_cut=float(s.get("gr2_warn_cut", 5.0)) / 100.0,
            crit_cut=float(s.get("gr2_crit_cut", 15.0)) / 100.0,
        ),
        gr3=GuardrailGR3Config(
            enabled=bool(s.get("gr3_enabled", True)),
        ),
        gr4=GuardrailGR4Config(
            enabled=bool(s.get("gr4_enabled", True)),
            inf_trigger=float(s.get("gr4_inf_trigger", 4.5)) / 100.0,
            cut_pct=float(s.get("gr4_cut_pct", 5.0)) / 100.0,
        ),
    )

    # Run validation and display results
    result = validate_inputs(inputs)

    if result.errors:
        for err in result.errors:
            st.error(err)
    if result.warnings:
        for warn in result.warnings:
            st.warning(warn)
    if result.valid and not result.warnings:
        st.success("✓ All inputs valid. Ready to run simulation.")

    # Store assembled inputs for the Run button to use
    s["_assembled_inputs"] = inputs if result.valid else None
    s["_validation_result"] = result

    return inputs if result.valid else None
