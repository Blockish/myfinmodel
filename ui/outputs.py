"""Results tab UI for the Monte Carlo retirement planner (Phase 4)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re

import numpy as np
import pandas as pd
import streamlit as st

from simulation.models import SimulationResults
from utils.charts import (
    create_comparison_overlay,
    create_guardrail_event_chart,
    create_inflation_fan_chart,
    create_portfolio_fan_chart,
    create_spending_fan_chart,
    create_survival_donut,
    create_withdrawal_rate_chart,
)

_EVENT_CODES = ["PV-DOWN", "PV-UP", "WR-WARN", "WR-CRIT", "WR-LOW", "ACA-BREACH", "INF", "NONE"]


@dataclass
class _DisplayMetrics:
    survival_rate: float
    median_final_nominal: float
    p10_final_nominal: float
    p90_final_nominal: float
    avg_spending_alive_nominal: float
    median_wr_alive: float
    active_guardrails: int
    inflation_floor: float


def _survival_band(survival_rate: float) -> tuple[str, str]:
    """Return status label and Streamlit color token for survival thresholds."""
    if survival_rate >= 0.85:
        return "Green (>= 85%)", "green"
    if survival_rate >= 0.70:
        return "Yellow (70%-85%)", "orange"
    return "Red (< 70%)", "red"


def _safe_mean(values: np.ndarray) -> float:
    return float(np.mean(values)) if values.size else 0.0


def _safe_median(values: np.ndarray) -> float:
    return float(np.median(values)) if values.size else 0.0


def _metric_summary(results: SimulationResults) -> _DisplayMetrics:
    alive_mask = results.portfolio > 0
    wr_alive = results.wr[alive_mask]

    active_grs = sum([
        results.inputs.gr1.enabled,
        results.inputs.gr2.enabled,
        results.inputs.gr3.enabled and results.inputs.health.aca_guardrail_enabled,
        results.inputs.gr4.enabled,
    ])

    final = results.portfolio[:, -1]

    return _DisplayMetrics(
        survival_rate=results.success_rate(),
        median_final_nominal=_safe_median(final),
        p10_final_nominal=float(np.percentile(final, 10)),
        p90_final_nominal=float(np.percentile(final, 90)),
        avg_spending_alive_nominal=_safe_mean(results.spend[alive_mask]),
        median_wr_alive=_safe_median(wr_alive),
        active_guardrails=active_grs,
        inflation_floor=results.inputs.inf_floor,
    )


def _median_depletion_age(results: SimulationResults) -> str:
    depleted_mask = results.portfolio <= 0
    any_depleted = np.any(depleted_mask, axis=1)
    if not np.any(any_depleted):
        return "N/A - All paths survived"
    first_depletion_idx = np.argmax(depleted_mask[any_depleted], axis=1)
    med_year = int(np.median(first_depletion_idx))
    return f"Age {results.ages[med_year]}"


def _success_metrics_table(results: SimulationResults, *, show_extended: bool = False) -> pd.DataFrame:
    alive_mask = results.portfolio > 0
    final_nominal = results.portfolio[:, -1]
    final_real = results.real_portfolio[:, -1]
    events = results.events
    wr_alive = results.wr[alive_mask]

    rows: list[dict[str, str]] = [
        {"Category": "Portfolio Outcomes", "Metric": "Survival Rate", "Value": f"{results.success_rate() * 100:.1f}%"},
        {"Category": "Portfolio Outcomes", "Metric": "Paths Depleted", "Value": f"{results.failure_count():,}"},
        {"Category": "Portfolio Outcomes", "Metric": "Median Final Portfolio (nominal)", "Value": f"${_safe_median(final_nominal):,.0f}"},
        {"Category": "Portfolio Outcomes", "Metric": "Median Final Portfolio (real)", "Value": f"${_safe_median(final_real):,.0f}"},
        {"Category": "Portfolio Outcomes", "Metric": "10th Percentile Final (nominal)", "Value": f"${np.percentile(final_nominal, 10):,.0f}"},
        {"Category": "Portfolio Outcomes", "Metric": "25th Percentile Final (nominal)", "Value": f"${np.percentile(final_nominal, 25):,.0f}"},
        {"Category": "Portfolio Outcomes", "Metric": "75th Percentile Final (nominal)", "Value": f"${np.percentile(final_nominal, 75):,.0f}"},
        {"Category": "Portfolio Outcomes", "Metric": "90th Percentile Final (nominal)", "Value": f"${np.percentile(final_nominal, 90):,.0f}"},
        {"Category": "Portfolio Outcomes", "Metric": "Median Depletion Age", "Value": _median_depletion_age(results)},
        {"Category": "Portfolio Outcomes", "Metric": "Median Peak Portfolio", "Value": f"${_safe_median(np.max(results.portfolio, axis=1)):,.0f}"},
        {"Category": "Portfolio Outcomes", "Metric": "Median Age of Peak Portfolio", "Value": f"Age {results.ages[int(np.median(np.argmax(results.portfolio, axis=1)))]}"},
        {"Category": "Portfolio Outcomes", "Metric": "Maximum Portfolio Observed", "Value": f"${float(np.max(results.portfolio)):,.0f}"},
        {"Category": "Spending Outcomes", "Metric": "Average Annual Spending - All Path-Years (nominal)", "Value": f"${_safe_mean(results.spend):,.0f}"},
        {"Category": "Spending Outcomes", "Metric": "Average Annual Spending - Surviving Path-Years (nominal)", "Value": f"${_safe_mean(results.spend[alive_mask]):,.0f}"},
        {"Category": "Spending Outcomes", "Metric": "Average Annual Spending - Surviving Path-Years (real)", "Value": f"${_safe_mean(results.real_spend[alive_mask]):,.0f}"},
        {"Category": "Spending Outcomes", "Metric": "Median Year-1 Spending (nominal)", "Value": f"${_safe_median(results.spend[:, 0]):,.0f}"},
        {"Category": "Spending Outcomes", "Metric": f"Median Year-{min(10, results.plan_years)} Spending", "Value": f"${_safe_median(results.spend[:, min(9, results.plan_years - 1)]):,.0f} nominal / ${_safe_median(results.real_spend[:, min(9, results.plan_years - 1)]):,.0f} real"},
        {"Category": "Spending Outcomes", "Metric": f"Median Year-{min(20, results.plan_years)} Spending", "Value": f"${_safe_median(results.spend[:, min(19, results.plan_years - 1)]):,.0f} nominal / ${_safe_median(results.real_spend[:, min(19, results.plan_years - 1)]):,.0f} real"},
        {"Category": "Guardrail Trigger Frequencies", "Metric": "% paths with PV-DOWN at least once", "Value": f"{np.mean(np.any(events == 'PV-DOWN', axis=1)) * 100:.1f}%"},
        {"Category": "Guardrail Trigger Frequencies", "Metric": "% paths with PV-UP at least once", "Value": f"{np.mean(np.any(events == 'PV-UP', axis=1)) * 100:.1f}%"},
        {"Category": "Guardrail Trigger Frequencies", "Metric": "% paths with WR-WARN at least once", "Value": f"{np.mean(np.any(events == 'WR-WARN', axis=1)) * 100:.1f}%"},
        {"Category": "Guardrail Trigger Frequencies", "Metric": "% paths with WR-CRIT at least once", "Value": f"{np.mean(np.any(events == 'WR-CRIT', axis=1)) * 100:.1f}%"},
        {"Category": "Guardrail Trigger Frequencies", "Metric": "% paths with WR-LOW at least once", "Value": f"{np.mean(np.any(events == 'WR-LOW', axis=1)) * 100:.1f}%"},
        {"Category": "Guardrail Trigger Frequencies", "Metric": "% paths with ACA-BREACH at least once", "Value": f"{np.mean(np.any(events == 'ACA-BREACH', axis=1)) * 100:.1f}%" if (results.inputs.gr3.enabled and results.inputs.health.aca_guardrail_enabled) else "N/A (GR3 disabled)"},
        {"Category": "Guardrail Trigger Frequencies", "Metric": "% paths with INF at least once", "Value": f"{np.mean(np.any(events == 'INF', axis=1)) * 100:.1f}%"},
        {"Category": "Guardrail Trigger Frequencies", "Metric": "% paths never triggering any guardrail", "Value": f"{np.mean(np.all(events == 'NONE', axis=1)) * 100:.1f}%"},
        {"Category": "Withdrawal Rate Statistics", "Metric": "Median WR across surviving path-years", "Value": f"{_safe_median(wr_alive) * 100:.2f}%"},
        {"Category": "Withdrawal Rate Statistics", "Metric": "Average WR across surviving path-years", "Value": f"{_safe_mean(wr_alive) * 100:.2f}%"},
        {"Category": "Withdrawal Rate Statistics", "Metric": "Median annual 90th percentile WR", "Value": f"{_safe_median(np.percentile(results.wr, 90, axis=0)) * 100:.2f}%"},
        {"Category": "Withdrawal Rate Statistics", "Metric": "% path-years with WR > 5%", "Value": f"{np.mean(results.wr > 0.05) * 100:.1f}%"},
        {"Category": "Withdrawal Rate Statistics", "Metric": "% path-years with WR > 6.5%", "Value": f"{np.mean(results.wr > 0.065) * 100:.1f}%"},
    ]

    if show_extended:
        rows.extend(
            [
                {
                    "Category": "Spending Outcomes (Extended)",
                    "Metric": f"Median Year-{min(10, results.plan_years)} Spending (nominal)",
                    "Value": f"${_safe_median(results.spend[:, min(9, results.plan_years - 1)]):,.0f}",
                },
                {
                    "Category": "Spending Outcomes (Extended)",
                    "Metric": f"Median Year-{min(10, results.plan_years)} Spending (real)",
                    "Value": f"${_safe_median(results.real_spend[:, min(9, results.plan_years - 1)]):,.0f}",
                },
                {
                    "Category": "Spending Outcomes (Extended)",
                    "Metric": f"Median Year-{min(20, results.plan_years)} Spending (nominal)",
                    "Value": f"${_safe_median(results.spend[:, min(19, results.plan_years - 1)]):,.0f}",
                },
                {
                    "Category": "Spending Outcomes (Extended)",
                    "Metric": f"Median Year-{min(20, results.plan_years)} Spending (real)",
                    "Value": f"${_safe_median(results.real_spend[:, min(19, results.plan_years - 1)]):,.0f}",
                },
            ]
        )

    return pd.DataFrame(rows)


def _portfolio_percentiles_df(results: SimulationResults) -> pd.DataFrame:
    p = np.percentile(results.portfolio, [10, 25, 50, 75, 90], axis=0).T
    return pd.DataFrame(
        {
            "Age": results.ages,
            "Year": np.arange(1, results.plan_years + 1),
            "10th Pct": p[:, 0],
            "25th Pct": p[:, 1],
            "Median": p[:, 2],
            "75th Pct": p[:, 3],
            "90th Pct": p[:, 4],
        }
    )


def _spending_percentiles_df(results: SimulationResults) -> pd.DataFrame:
    p = np.percentile(results.spend, [10, 25, 50, 75, 90], axis=0).T
    return pd.DataFrame(
        {
            "Age": results.ages,
            "Year": np.arange(1, results.plan_years + 1),
            "10th Pct": p[:, 0],
            "25th Pct": p[:, 1],
            "Median": p[:, 2],
            "75th Pct": p[:, 3],
            "90th Pct": p[:, 4],
            "Median Real": np.median(results.real_spend, axis=0),
        }
    )


def _event_frequency_df(results: SimulationResults) -> pd.DataFrame:
    data: dict[str, np.ndarray] = {
        "Age": np.array(results.ages),
    }
    for code in _EVENT_CODES:
        data[code] = np.sum(results.events == code, axis=0)
    return pd.DataFrame(data)


def _inflation_stats_df(results: SimulationResults) -> pd.DataFrame:
    inf = results.inf_draws
    return pd.DataFrame(
        {
            "Age": results.ages,
            "Year": np.arange(1, results.plan_years + 1),
            "Min Inf": np.min(inf, axis=0),
            "10th Pct Inf": np.percentile(inf, 10, axis=0),
            "Median Inf": np.percentile(inf, 50, axis=0),
            "90th Pct Inf": np.percentile(inf, 90, axis=0),
            "Max Inf": np.max(inf, axis=0),
            "Median Cum Inflation Index": np.median(results.cum_inf, axis=0),
        }
    )


def _pad_to_range(
    ages: list[int],
    values: np.ndarray,
    global_start: int,
    global_end: int,
) -> list[float]:
    """Pad a values array with NaN so it spans [global_start, global_end]."""
    result = [float("nan")] * (global_end - global_start + 1)
    for i, age in enumerate(ages):
        result[age - global_start] = float(values[i])
    return result


def _full_path_export_df(results: SimulationResults) -> pd.DataFrame:
    n, t = results.n_paths, results.plan_years
    path_idx = np.repeat(np.arange(n), t)
    age_arr = np.tile(np.array(results.ages), n)

    return pd.DataFrame(
        {
            "Path": path_idx,
            "Age": age_arr,
            "Portfolio": results.portfolio.reshape(-1),
            "Spending": results.spend.reshape(-1),
            "WR": results.wr.reshape(-1),
            "SS Income": results.ss_income.reshape(-1),
            "Health Cost": results.health_cost.reshape(-1),
            "Event Code": results.events.reshape(-1),
            "Cum Inflation": results.cum_inf.reshape(-1),
            "Real Portfolio": results.real_portfolio.reshape(-1),
        }
    )


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", text.strip().lower())
    return cleaned.strip("-") or "run"


def _csv_file_name(base: str, *, scenario_name: str = "current-run") -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{_slugify(base)}-{_slugify(scenario_name)}-{ts}.csv"


def _download_df(df: pd.DataFrame, *, label: str, file_name: str) -> None:
    st.download_button(
        label=label,
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=file_name,
        mime="text/csv",
        use_container_width=False,
    )


def _compare_candidates() -> dict[str, SimulationResults]:
    """Return saved scenarios with attached results only.

    Compare view is enabled only when at least two saved scenarios have results.
    """
    candidates: dict[str, SimulationResults] = {}
    scenarios = st.session_state.get("scenarios", [])
    for entry in scenarios:
        name = entry.get("name")
        saved = entry.get("results")
        if isinstance(name, str) and isinstance(saved, SimulationResults):
            # Keep first match for duplicated names.
            if name not in candidates:
                candidates[name] = saved
    return candidates


def render_outputs(results: SimulationResults) -> None:
    """Render full Phase 4 results UI for a completed simulation."""
    st.subheader("Summary Dashboard Metric Cards")
    m = _metric_summary(results)

    compare_sources = _compare_candidates()
    include_compare = len(compare_sources) >= 2
    scenario_a_name = st.session_state.get("outputs_compare_a")
    if include_compare:
        if not isinstance(scenario_a_name, str) or scenario_a_name not in compare_sources:
            scenario_a_name = list(compare_sources.keys())[0]

    baseline_metrics: _DisplayMetrics | None = None
    if include_compare and isinstance(scenario_a_name, str):
        baseline_metrics = _metric_summary(compare_sources[scenario_a_name])

    band_label, band_color = _survival_band(m.survival_rate)

    def _pct_point_delta(current: float, base: float | None) -> str | None:
        if base is None:
            return None
        return f"{(current - base) * 100:+.1f} pp"

    def _usd_delta(current: float, base: float | None) -> str | None:
        if base is None:
            return None
        return f"${(current - base):+,.0f}"

    def _raw_delta(current: float, base: float | None, fmt: str) -> str | None:
        if base is None:
            return None
        return format(current - base, fmt)

    r1 = st.columns(4)
    r1[0].metric(
        "Full Horizon Survival Rate",
        f"{m.survival_rate:.1%}",
        delta=_pct_point_delta(m.survival_rate, baseline_metrics.survival_rate if baseline_metrics else None),
        help="Delta is relative to selected Scenario A when compare is active.",
    )
    r1[0].markdown(f":{band_color}[Threshold Band: {band_label}]")
    r1[1].metric(
        "Median Final Portfolio",
        f"${m.median_final_nominal:,.0f}",
        delta=_usd_delta(m.median_final_nominal, baseline_metrics.median_final_nominal if baseline_metrics else None),
        help="Delta is relative to selected Scenario A when compare is active.",
    )
    r1[2].metric(
        "10th Pct Final Portfolio",
        f"${m.p10_final_nominal:,.0f}",
        delta=_usd_delta(m.p10_final_nominal, baseline_metrics.p10_final_nominal if baseline_metrics else None),
        help="Delta is relative to selected Scenario A when compare is active.",
    )
    r1[3].metric(
        "90th Pct Final Portfolio",
        f"${m.p90_final_nominal:,.0f}",
        delta=_usd_delta(m.p90_final_nominal, baseline_metrics.p90_final_nominal if baseline_metrics else None),
        help="Delta is relative to selected Scenario A when compare is active.",
    )

    r2 = st.columns(4)
    r2[0].metric(
        "Avg Spending (Surviving)",
        f"${m.avg_spending_alive_nominal:,.0f}",
        delta=_usd_delta(
            m.avg_spending_alive_nominal,
            baseline_metrics.avg_spending_alive_nominal if baseline_metrics else None,
        ),
        help="Mean across surviving path-years only. Delta is relative to selected Scenario A when compare is active.",
    )
    r2[1].metric(
        "Median Withdrawal Rate",
        f"{m.median_wr_alive:.1%}",
        delta=_pct_point_delta(m.median_wr_alive, baseline_metrics.median_wr_alive if baseline_metrics else None),
        help="Delta is relative to selected Scenario A when compare is active.",
    )
    r2[2].metric(
        "Active Guardrails",
        f"{m.active_guardrails} of 4 enabled",
        delta=_raw_delta(
            float(m.active_guardrails),
            float(baseline_metrics.active_guardrails) if baseline_metrics else None,
            "+.0f",
        ),
        help="Delta is relative to selected Scenario A when compare is active.",
    )
    r2[3].metric(
        "Inflation Floor",
        f"{m.inflation_floor:.1%}",
        delta=_pct_point_delta(m.inflation_floor, baseline_metrics.inflation_floor if baseline_metrics else None),
        help="Delta is relative to selected Scenario A when compare is active.",
    )

    if include_compare and isinstance(scenario_a_name, str):
        st.caption(f"Summary card deltas are shown vs Scenario A ({scenario_a_name}).")

    st.divider()

    tabs = ["Success Metrics", "Portfolio", "Spending", "Analysis", "Tax Efficiency", "Raw Data"]
    if include_compare:
        tabs.append("Compare")

    tab_objects = st.tabs(tabs)

    # Tab 1: Success Metrics
    with tab_objects[0]:
        show_extended = st.toggle(
            "Show extended metrics",
            value=False,
            key="outputs_show_extended_metrics",
            help="Off = strict spec row counts. On = include additional spending detail rows.",
        )
        success_df = _success_metrics_table(results, show_extended=show_extended)
        st.dataframe(success_df, use_container_width=True, hide_index=True)

    # Tab 2: Portfolio
    with tab_objects[1]:
        mode = st.radio(
            "Portfolio Fan View",
            options=["Nominal", "Real (Inflation-Adjusted)"],
            horizontal=True,
            key="outputs_portfolio_mode",
        )
        matrix = results.portfolio if mode == "Nominal" else results.real_portfolio
        prefix = "Portfolio Value by Age" if mode == "Nominal" else "Real Portfolio Value by Age"
        fig = create_portfolio_fan_chart(
            portfolio_matrix=matrix,
            ages=results.ages,
            n_paths=results.n_paths,
            ss_start_age=results.inputs.ss_start_age if results.inputs.ss_enabled else None,
            medicare_age=results.inputs.health.medicare_age,
            title_prefix=prefix,
        )
        st.plotly_chart(fig, use_container_width=True)

    # Tab 3: Spending
    with tab_objects[2]:
        mode = st.radio(
            "Spending Fan View",
            options=["Nominal", "Real"],
            horizontal=True,
            key="outputs_spending_mode",
        )

        if mode == "Nominal":
            matrix = results.spend
            med_cum = np.median(results.cum_inf, axis=0)
            floor_line = results.inputs.spend_floor * med_cum
            ceiling_line = results.inputs.spend_ceiling * med_cum
        else:
            matrix = results.real_spend
            floor_line = np.full(results.plan_years, results.inputs.spend_floor)
            ceiling_line = np.full(results.plan_years, results.inputs.spend_ceiling)

        fig = create_spending_fan_chart(
            spend_matrix=matrix,
            ages=results.ages,
            n_paths=results.n_paths,
            floor_line=floor_line,
            ceiling_line=ceiling_line,
            ss_start_age=results.inputs.ss_start_age if results.inputs.ss_enabled else None,
            medicare_age=results.inputs.health.medicare_age,
        )
        st.plotly_chart(fig, use_container_width=True)

    # Tab 4: Analysis (Guardrails + Inflation)
    with tab_objects[3]:
        aca_active = results.inputs.gr3.enabled and results.inputs.health.aca_guardrail_enabled
        ev_fig = create_guardrail_event_chart(
            events_matrix=results.events,
            ages=results.ages,
            n_paths=results.n_paths,
            include_none=False,
            include_aca=aca_active,
        )
        st.plotly_chart(ev_fig, use_container_width=True)

        c1, c2 = st.columns([1, 2])
        with c1:
            survived = results.success_count()
            donut = create_survival_donut(
                survived_paths=survived,
                total_paths=results.n_paths,
                plan_years=results.plan_years,
                final_age=results.ages[-1],
            )
            st.plotly_chart(donut, use_container_width=True)

        with c2:
            infl = create_inflation_fan_chart(
                inf_matrix=results.inf_draws,
                ages=results.ages,
                inf_floor=results.inputs.inf_floor,
                inf_mean=results.inputs.inf_mean,
                gr4_inf_trigger=results.inputs.gr4.inf_trigger,
            )
            st.plotly_chart(infl, use_container_width=True)
            if results.inputs.inf_floor > 0:
                st.caption(
                    f"Inflation draws are clipped at {results.inputs.inf_floor:.1%}; "
                    "deflation scenarios are excluded."
                )

    # Tab 5: Tax Efficiency
    with tab_objects[4]:
        wr_mode = st.radio(
            "Withdrawal Rate chart mode",
            options=["Fan", "Box"],
            horizontal=True,
            key="outputs_wr_mode",
        )
        wr_fig = create_withdrawal_rate_chart(
            wr_matrix=results.wr,
            ages=results.ages,
            mode="fan" if wr_mode == "Fan" else "box",
            ref_lines=(0.04, 0.05, 0.065),
        )
        st.plotly_chart(wr_fig, use_container_width=True)

    # Tab 6: Raw Data
    with tab_objects[5]:
        df1 = _portfolio_percentiles_df(results)
        st.markdown("**Table 1 - Percentile Portfolio Paths**")
        st.dataframe(df1, use_container_width=True)
        _download_df(
            df1,
            label="Download CSV - Table 1 Portfolio Paths",
            file_name=_csv_file_name("portfolio-percentiles"),
        )

        st.markdown("**Table 2 - Percentile Spending Paths**")
        df2 = _spending_percentiles_df(results)
        st.dataframe(df2, use_container_width=True)
        _download_df(
            df2,
            label="Download CSV - Table 2 Spending Paths",
            file_name=_csv_file_name("spending-percentiles"),
        )

        st.markdown("**Table 3 - Guardrail Event Frequency**")
        df3 = _event_frequency_df(results)
        st.dataframe(df3, use_container_width=True)
        _download_df(
            df3,
            label="Download CSV - Table 3 Guardrail Events",
            file_name=_csv_file_name("guardrail-event-frequency"),
        )

        st.markdown("**Table 4 - Inflation Statistics**")
        df4 = _inflation_stats_df(results)
        st.dataframe(df4, use_container_width=True)
        _download_df(
            df4,
            label="Download CSV - Table 4 Inflation Statistics",
            file_name=_csv_file_name("inflation-statistics"),
        )

        st.markdown("**Table 5 - Full Path Data Export (On-Demand)**")
        n_rows = results.n_paths * results.plan_years
        est_mb = n_rows * 10 * 12 / 1024 / 1024
        st.warning(
            f"This export will contain {n_rows:,} rows. Estimated CSV size is roughly {est_mb:.1f} MB.",
            icon="⚠️",
        )

        if st.button("Generate Full Path Export", key="outputs_gen_full_export"):
            full_df = _full_path_export_df(results)
            st.dataframe(full_df.head(500), use_container_width=True)
            st.caption("Showing first 500 rows in-app. The CSV download includes all rows.")
            _download_df(
                full_df,
                label="Download CSV - Table 5 Full Path Export",
                file_name=_csv_file_name("full-path-export"),
            )

    # Tab 7 (optional): Compare
    if include_compare:
        with tab_objects[6]:
            scenario_names = list(compare_sources.keys())
            base_default = 0
            comp_default = 1 if len(scenario_names) > 1 else 0

            c1, c2 = st.columns(2)
            with c1:
                base_name = st.selectbox(
                    "Scenario A",
                    options=scenario_names,
                    index=base_default,
                    key="outputs_compare_a",
                )
            with c2:
                compare_name = st.selectbox(
                    "Scenario B",
                    options=scenario_names,
                    index=comp_default,
                    key="outputs_compare_b",
                )

            if base_name == compare_name:
                st.info("Choose two different scenarios to compare.")
            else:
                a = compare_sources[base_name]
                b = compare_sources[compare_name]

                a_alive = a.portfolio > 0
                b_alive = b.portfolio > 0
                rows = [
                    ("Survival Rate", a.success_rate() * 100, b.success_rate() * 100, "%"),
                    ("Median Final Portfolio", _safe_median(a.portfolio[:, -1]), _safe_median(b.portfolio[:, -1]), "$"),
                    ("Avg Spending (Surviving)", _safe_mean(a.spend[a_alive]), _safe_mean(b.spend[b_alive]), "$"),
                    ("Median Withdrawal Rate", _safe_median(a.wr[a_alive]) * 100, _safe_median(b.wr[b_alive]) * 100, "%"),
                ]

                display_rows: list[dict[str, str]] = []
                for metric, va, vb, kind in rows:
                    delta = vb - va
                    if kind == "$":
                        display_rows.append(
                            {
                                "Metric": metric,
                                base_name: f"${va:,.0f}",
                                compare_name: f"${vb:,.0f}",
                                "Delta (B \u2212 A)": f"${delta:+,.0f}",
                            }
                        )
                    else:
                        display_rows.append(
                            {
                                "Metric": metric,
                                base_name: f"{va:.1f}%",
                                compare_name: f"{vb:.1f}%",
                                "Delta (B \u2212 A)": f"{delta:+.1f} pp",
                            }
                        )

                st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)

                # Guard for mismatched horizons between scenarios
                if a.plan_years != b.plan_years or a.ages[0] != b.ages[0]:
                    st.warning(
                        f"Scenario horizons differ ({base_name}: ages {a.ages[0]}\u2013{a.ages[-1]}, "
                        f"{compare_name}: ages {b.ages[0]}\u2013{b.ages[-1]}). "
                        "Both series are padded onto a combined age axis; gaps appear where a scenario has no data.",
                        icon="⚠️",
                    )

                overlay = create_comparison_overlay(
                    ages=a.ages,
                    scenario_to_median={
                        base_name: np.percentile(a.portfolio, 50, axis=0),
                        compare_name: np.percentile(b.portfolio, 50, axis=0),
                    },
                ) if a.plan_years == b.plan_years and a.ages[0] == b.ages[0] else create_comparison_overlay(
                    ages=list(range(
                        min(a.ages[0], b.ages[0]),
                        max(a.ages[-1], b.ages[-1]) + 1,
                    )),
                    scenario_to_median={
                        base_name: _pad_to_range(a.ages, np.percentile(a.portfolio, 50, axis=0),
                                                 min(a.ages[0], b.ages[0]), max(a.ages[-1], b.ages[-1])),
                        compare_name: _pad_to_range(b.ages, np.percentile(b.portfolio, 50, axis=0),
                                                    min(a.ages[0], b.ages[0]), max(a.ages[-1], b.ages[-1])),
                    },
                )
                st.plotly_chart(overlay, use_container_width=True)

    if not include_compare:
        st.caption("Compare tab appears when at least two saved scenarios include results.")
