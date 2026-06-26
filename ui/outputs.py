"""Output UI page for the Monte Carlo retirement simulator."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from simulation.models import SimulationSummary
from utils.charts import (
    create_fan_chart,
    create_final_value_histogram,
    create_spending_fan_chart,
    create_success_gauge,
)


def render_outputs(summary: SimulationSummary, label: str = "") -> None:
    """Render all output sections for a completed simulation summary.

    Parameters
    ----------
    summary:
        The simulation results to display.
    label:
        Optional prefix for section headings (used in comparison mode).
    """
    heading_prefix = f"{label} — " if label else ""
    p = summary.params

    # ── 1. Headline metrics ────────────────────────────────────────────────────
    st.subheader(f"{heading_prefix}📊 Plan Success Summary")
    _render_headline_metrics(summary)

    st.divider()

    # ── 2. Fan charts ──────────────────────────────────────────────────────────
    st.subheader(f"{heading_prefix}📈 Portfolio Fan Chart")
    pct_paths = summary.percentile_paths([5, 10, 25, 50, 75, 90, 95])
    fan_fig = create_fan_chart(
        percentile_paths=pct_paths,
        years=p.years,
        title=f"{heading_prefix}Portfolio Value Over Time",
        initial_portfolio=p.initial_portfolio,
    )
    st.plotly_chart(fan_fig, use_container_width=True)

    # Spending fan chart
    st.subheader(f"{heading_prefix}💸 Annual Spending Fan Chart")
    spending_fig = create_spending_fan_chart(
        results=summary.results,
        years=p.years,
        title=f"{heading_prefix}Annual Spending Over Time",
    )
    st.plotly_chart(spending_fig, use_container_width=True)

    st.divider()

    # ── 3. Final-value distribution ────────────────────────────────────────────
    st.subheader(f"{heading_prefix}📉 Final Portfolio Value Distribution")
    final_values = [r.final_value for r in summary.results]
    hist_fig = create_final_value_histogram(
        final_values,
        title=f"{heading_prefix}Distribution of Final Portfolio Values",
    )
    st.plotly_chart(hist_fig, use_container_width=True)

    st.divider()

    # ── 4. Detailed statistics ────────────────────────────────────────────────
    st.subheader(f"{heading_prefix}🔢 Detailed Statistics")
    _render_detailed_stats(summary)

    st.divider()

    # ── 5. Simulation detail table (expandable) ────────────────────────────────
    with st.expander("🗂 Simulation Detail Table (all paths)", expanded=False):
        _render_detail_table(summary)


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────


def _render_headline_metrics(summary: SimulationSummary) -> None:
    """Display top-level KPIs in a metric row with a gauge chart."""
    p = summary.params
    col_gauge, col_metrics = st.columns([1, 2])

    with col_gauge:
        gauge_fig = create_success_gauge(summary.success_rate)
        st.plotly_chart(gauge_fig, use_container_width=True)

    with col_metrics:
        m1, m2, m3 = st.columns(3)
        m1.metric("Success Rate", f"{summary.success_rate:.1%}")
        m2.metric("Successful Paths", f"{summary.success_count:,}")
        m3.metric("Failed Paths", f"{summary.failure_count:,}")

        m4, m5, m6 = st.columns(3)
        m4.metric("Median Final Value", f"${summary.median_final_value:,.0f}")
        m5.metric("Mean Final Value", f"${summary.mean_final_value:,.0f}")
        m6.metric(
            "Initial Withdrawal Rate",
            f"{p.withdrawal_rate():.2%}",
        )


def _render_detailed_stats(summary: SimulationSummary) -> None:
    """Render percentile table and depletion distribution."""
    p = summary.params
    pct_paths = summary.percentile_paths([5, 10, 25, 50, 75, 90, 95])

    # Percentile summary at key years
    key_years = sorted(
        set([1, 5, 10, 15, 20, 25, p.years]) & set(range(p.years + 1))
    )
    rows = []
    for yr in key_years:
        row = {"Year": yr}
        for pct, vals in pct_paths.items():
            row[f"p{pct}"] = f"${vals[yr]:,.0f}"
        rows.append(row)

    df_pct = pd.DataFrame(rows).set_index("Year")
    st.markdown("**Portfolio Value at Key Years (by Percentile)**")
    st.dataframe(df_pct, use_container_width=True)

    # Depletion year distribution (failures only)
    dep_dist = summary.depletion_year_distribution()
    if dep_dist:
        st.markdown("**Depletion Year Distribution (failed paths)**")
        dep_df = (
            pd.DataFrame(
                [{"Year": yr, "Failed Paths": cnt} for yr, cnt in sorted(dep_dist.items())]
            )
            .set_index("Year")
        )
        st.bar_chart(dep_df, y="Failed Paths")
    else:
        st.success("🎉 No paths depleted the portfolio within the simulation horizon.")


def _render_detail_table(summary: SimulationSummary) -> None:
    """Render a summary row per simulation path."""
    rows = [
        {
            "Path": r.path_id,
            "Success": "✅" if r.success else "❌",
            "Final Value ($)": round(r.final_value, 2),
            "Peak Value ($)": round(r.peak_value, 2),
            "Trough Value ($)": round(r.trough_value, 2),
            "Depletion Year": r.depletion_year if r.depletion_year else "—",
        }
        for r in summary.results
    ]
    df = pd.DataFrame(rows).set_index("Path")
    st.dataframe(df, use_container_width=True, height=400)
