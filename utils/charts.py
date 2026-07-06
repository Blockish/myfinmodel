"""Plotly chart builders for Phase 4 Results UI.

This module has zero Streamlit imports by design. Functions accept plain arrays
and metadata, and return Plotly ``go.Figure`` objects.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import plotly.graph_objects as go

# Core percentile colors used across fan charts.
P10_COLOR = "#d62728"
P25_COLOR = "#ff7f0e"
P50_COLOR = "#2ca02c"
P75_COLOR = "#1f77b4"
P90_COLOR = "#9467bd"
BAND_COLOR = "rgba(31, 119, 180, 0.18)"

# Event colors for guardrail stacked bars.
EVENT_COLORS: dict[str, str] = {
    "PV-DOWN": "#d62728",
    "PV-UP": "#2ca02c",
    "WR-WARN": "#ff7f0e",
    "WR-CRIT": "#b91c1c",
    "WR-LOW": "#0f766e",
    "ACA-BREACH": "#7c3aed",
    "INF": "#d97706",
    "NONE": "#9ca3af",
}


def _percentiles_by_year(matrix: np.ndarray, percentiles: Sequence[int]) -> dict[int, np.ndarray]:
    """Return percentile paths over years from a (n_paths, years) matrix."""
    p = np.percentile(matrix, percentiles, axis=0)
    return {pct: p[idx, :] for idx, pct in enumerate(percentiles)}


def _add_age_markers(
    fig: go.Figure,
    *,
    ss_start_age: int | None,
    medicare_age: int | None,
) -> None:
    """Add consistent vertical age markers for SS and Medicare to a chart."""
    if ss_start_age is not None:
        fig.add_vline(
            x=ss_start_age,
            line_dash="dash",
            line_color="#6b7280",
            annotation_text="SS Begins",
            annotation_position="top right",
        )
    if medicare_age is not None:
        fig.add_vline(
            x=medicare_age,
            line_dash="dot",
            line_color="#6b7280",
            annotation_text="Medicare",
            annotation_position="top right",
        )


def _base_layout(fig: go.Figure, *, title: str, yaxis_title: str) -> go.Figure:
    fig.update_layout(
        title=title,
        xaxis_title="Age",
        yaxis_title=yaxis_title,
        hovermode="x unified",
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=36, r=24, t=62, b=40),
    )
    return fig


def create_portfolio_fan_chart(
    *,
    portfolio_matrix: np.ndarray,
    ages: Sequence[int],
    n_paths: int,
    ss_start_age: int | None = None,
    medicare_age: int | None = None,
    title_prefix: str = "Portfolio Value by Age",
) -> go.Figure:
    """Build portfolio percentile fan chart with 10/25/50/75/90 lines and 10-90 band."""
    p = _percentiles_by_year(portfolio_matrix, [10, 25, 50, 75, 90])
    fig = go.Figure()

    # Build 10-90 shaded band (upper then lower with fill).
    fig.add_trace(
        go.Scatter(
            x=list(ages),
            y=p[90],
            mode="lines",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
            name="90th",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=list(ages),
            y=p[10],
            mode="lines",
            line=dict(width=0),
            fill="tonexty",
            fillcolor=BAND_COLOR,
            showlegend=True,
            name="10th-90th band",
            hoverinfo="skip",
        )
    )

    fig.add_trace(go.Scatter(x=list(ages), y=p[10], mode="lines", name="10th", line=dict(color=P10_COLOR, width=1.8)))
    fig.add_trace(go.Scatter(x=list(ages), y=p[25], mode="lines", name="25th", line=dict(color=P25_COLOR, width=1.8)))
    fig.add_trace(go.Scatter(x=list(ages), y=p[50], mode="lines", name="50th (Median)", line=dict(color=P50_COLOR, width=3.0)))
    fig.add_trace(go.Scatter(x=list(ages), y=p[75], mode="lines", name="75th", line=dict(color=P75_COLOR, width=1.8)))
    fig.add_trace(go.Scatter(x=list(ages), y=p[90], mode="lines", name="90th", line=dict(color=P90_COLOR, width=1.8)))

    _add_age_markers(fig, ss_start_age=ss_start_age, medicare_age=medicare_age)
    return _base_layout(
        fig,
        title=f"{title_prefix} - Percentile Fan ({n_paths:,} paths)",
        yaxis_title="Portfolio Value ($)",
    ).update_yaxes(tickformat="$,.0f")


def create_spending_fan_chart(
    *,
    spend_matrix: np.ndarray,
    ages: Sequence[int],
    n_paths: int,
    floor_line: np.ndarray | Sequence[float] | None = None,
    ceiling_line: np.ndarray | Sequence[float] | None = None,
    ss_start_age: int | None = None,
    medicare_age: int | None = None,
    title_prefix: str = "Annual Spending by Age",
) -> go.Figure:
    """Build spending percentile fan with optional floor/ceiling overlays."""
    p = _percentiles_by_year(spend_matrix, [10, 25, 50, 75, 90])
    fig = go.Figure()

    fig.add_trace(go.Scatter(x=list(ages), y=p[90], mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(
        go.Scatter(
            x=list(ages),
            y=p[10],
            mode="lines",
            line=dict(width=0),
            fill="tonexty",
            fillcolor=BAND_COLOR,
            showlegend=True,
            name="10th-90th band",
            hoverinfo="skip",
        )
    )

    fig.add_trace(go.Scatter(x=list(ages), y=p[10], mode="lines", name="10th", line=dict(color=P10_COLOR, width=1.8)))
    fig.add_trace(go.Scatter(x=list(ages), y=p[25], mode="lines", name="25th", line=dict(color=P25_COLOR, width=1.8)))
    fig.add_trace(go.Scatter(x=list(ages), y=p[50], mode="lines", name="50th (Median)", line=dict(color=P50_COLOR, width=3.0)))
    fig.add_trace(go.Scatter(x=list(ages), y=p[75], mode="lines", name="75th", line=dict(color=P75_COLOR, width=1.8)))
    fig.add_trace(go.Scatter(x=list(ages), y=p[90], mode="lines", name="90th", line=dict(color=P90_COLOR, width=1.8)))

    if floor_line is not None:
        fig.add_trace(
            go.Scatter(
                x=list(ages),
                y=np.asarray(floor_line),
                mode="lines",
                name="Floor",
                line=dict(color="#8b5cf6", width=1.6, dash="dash"),
            )
        )
    if ceiling_line is not None:
        fig.add_trace(
            go.Scatter(
                x=list(ages),
                y=np.asarray(ceiling_line),
                mode="lines",
                name="Ceiling",
                line=dict(color="#6d28d9", width=1.6, dash="dash"),
            )
        )

    _add_age_markers(fig, ss_start_age=ss_start_age, medicare_age=medicare_age)
    return _base_layout(
        fig,
        title=f"{title_prefix} - Guardrail Adjusted ({n_paths:,} paths)",
        yaxis_title="Annual Spending ($)",
    ).update_yaxes(tickformat="$,.0f")


def create_guardrail_event_chart(
    *,
    events_matrix: np.ndarray,
    ages: Sequence[int],
    n_paths: int,
    include_none: bool = False,
) -> go.Figure:
    """Create stacked event frequency bars by age from event code matrix."""
    codes = ["PV-DOWN", "PV-UP", "WR-WARN", "WR-CRIT", "WR-LOW", "ACA-BREACH", "INF"]
    if include_none:
        codes.append("NONE")

    fig = go.Figure()
    for code in codes:
        counts = np.sum(events_matrix == code, axis=0)
        fig.add_trace(
            go.Bar(
                x=list(ages),
                y=counts,
                name=code,
                marker_color=EVENT_COLORS[code],
                customdata=np.round((counts / max(n_paths, 1)) * 100.0, 1),
                hovertemplate="Age %{x}<br>Count %{y}<br>% of paths %{customdata:.1f}%<extra></extra>",
            )
        )

    fig.update_layout(
        barmode="stack",
        title=f"Guardrail Events by Age (count out of {n_paths:,} paths)",
        xaxis_title="Age",
        yaxis_title="Count of paths",
        yaxis=dict(range=[0, n_paths]),
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=36, r=24, t=62, b=40),
    )
    return fig


def create_survival_donut(
    *,
    survived_paths: int,
    total_paths: int,
    plan_years: int,
    final_age: int,
) -> go.Figure:
    """Create survival vs depleted donut chart with center annotation."""
    depleted_paths = max(total_paths - survived_paths, 0)
    survival_pct = 0.0 if total_paths == 0 else (survived_paths / total_paths) * 100.0

    fig = go.Figure(
        go.Pie(
            labels=["Survived", "Depleted"],
            values=[survived_paths, depleted_paths],
            marker_colors=["#2ca02c", "#d62728"],
            hole=0.55,
            sort=False,
            textinfo="label+percent",
        )
    )
    fig.update_layout(
        title=f"Portfolio Survival at Year {plan_years} (Age {final_age})",
        annotations=[
            dict(text=f"{survival_pct:.1f}%", x=0.5, y=0.5, showarrow=False, font=dict(size=24, color="#111827")),
            dict(text=f"n={total_paths:,}", x=0.5, y=0.41, showarrow=False, font=dict(size=11, color="#6b7280")),
        ],
        template="plotly_white",
        margin=dict(l=24, r=24, t=58, b=20),
    )
    return fig


def create_withdrawal_rate_chart(
    *,
    wr_matrix: np.ndarray,
    ages: Sequence[int],
    mode: str = "fan",
    ref_lines: Sequence[float] = (0.04, 0.05, 0.065),
) -> go.Figure:
    """Create withdrawal-rate distribution chart in fan or box mode."""
    fig = go.Figure()

    if mode == "box":
        for idx, age in enumerate(ages):
            fig.add_trace(
                go.Box(
                    y=wr_matrix[:, idx],
                    name=str(age),
                    boxpoints=False,
                    line=dict(color="#1f77b4"),
                    marker_color="#93c5fd",
                    showlegend=False,
                )
            )
    else:
        p = _percentiles_by_year(wr_matrix, [10, 50, 90])
        fig.add_trace(go.Scatter(x=list(ages), y=p[90], mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(
            go.Scatter(
                x=list(ages),
                y=p[10],
                mode="lines",
                line=dict(width=0),
                fill="tonexty",
                fillcolor="rgba(59,130,246,0.18)",
                name="10th-90th band",
                hoverinfo="skip",
            )
        )
        fig.add_trace(go.Scatter(x=list(ages), y=p[10], mode="lines", name="10th", line=dict(color=P10_COLOR, width=1.6)))
        fig.add_trace(go.Scatter(x=list(ages), y=p[50], mode="lines", name="50th (Median)", line=dict(color=P50_COLOR, width=3.0)))
        fig.add_trace(go.Scatter(x=list(ages), y=p[90], mode="lines", name="90th", line=dict(color=P90_COLOR, width=1.6)))

    ref_colors = ["#6b7280", "#f59e0b", "#dc2626"]
    ref_labels = ["4.0%", "5.0%", "6.5%"]
    for idx, rate in enumerate(ref_lines):
        label = ref_labels[idx] if idx < len(ref_labels) else f"{rate*100:.1f}%"
        color = ref_colors[idx] if idx < len(ref_colors) else "#6b7280"
        fig.add_hline(
            y=rate,
            line_dash="dash",
            line_color=color,
            annotation_text=label,
            annotation_position="top right",
        )

    fig.update_layout(
        title="Withdrawal Rate by Age - Distribution Across Paths",
        xaxis_title="Age",
        yaxis_title="Withdrawal Rate",
        yaxis_tickformat=".1%",
        template="plotly_white",
        hovermode="x unified" if mode != "box" else "closest",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=36, r=24, t=62, b=40),
    )
    return fig


def create_inflation_fan_chart(
    *,
    inf_matrix: np.ndarray,
    ages: Sequence[int],
    inf_floor: float,
    inf_mean: float,
    gr4_inf_trigger: float,
) -> go.Figure:
    """Create inflation percentile fan with reference assumption lines."""
    p = _percentiles_by_year(inf_matrix, [10, 50, 90])
    fig = go.Figure()

    fig.add_trace(go.Scatter(x=list(ages), y=p[90], mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(
        go.Scatter(
            x=list(ages),
            y=p[10],
            mode="lines",
            line=dict(width=0),
            fill="tonexty",
            fillcolor="rgba(251,146,60,0.20)",
            name="10th-90th band",
            hoverinfo="skip",
        )
    )
    fig.add_trace(go.Scatter(x=list(ages), y=p[10], mode="lines", name="10th", line=dict(color=P10_COLOR, width=1.6)))
    fig.add_trace(go.Scatter(x=list(ages), y=p[50], mode="lines", name="50th (Median)", line=dict(color=P50_COLOR, width=3.0)))
    fig.add_trace(go.Scatter(x=list(ages), y=p[90], mode="lines", name="90th", line=dict(color=P90_COLOR, width=1.6)))

    fig.add_hline(y=inf_floor, line_dash="dash", line_color="#475569", annotation_text="Inflation Floor", annotation_position="top right")
    fig.add_hline(y=inf_mean, line_dash="dot", line_color="#0f766e", annotation_text="Mean Assumption", annotation_position="top right")
    fig.add_hline(y=gr4_inf_trigger, line_dash="dash", line_color="#b45309", annotation_text="GR4 Trigger", annotation_position="top right")

    fig.update_layout(
        title="Simulated Annual Inflation Rates - Distribution by Age",
        xaxis_title="Age",
        yaxis_title="Inflation Rate",
        yaxis_tickformat=".1%",
        template="plotly_white",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=36, r=24, t=62, b=40),
    )
    return fig


def create_comparison_overlay(
    *,
    ages: Sequence[int],
    scenario_to_median: Mapping[str, Sequence[float]],
    title: str = "Median Portfolio Comparison",
) -> go.Figure:
    """Create overlaid median lines for scenario comparison view."""
    palette = ["#2563eb", "#f97316", "#16a34a", "#9333ea", "#dc2626"]
    fig = go.Figure()

    for idx, (name, values) in enumerate(scenario_to_median.items()):
        fig.add_trace(
            go.Scatter(
                x=list(ages),
                y=list(values),
                mode="lines",
                name=name,
                line=dict(color=palette[idx % len(palette)], width=2.6),
            )
        )

    fig.update_layout(
        title=title,
        xaxis_title="Age",
        yaxis_title="Portfolio Value ($)",
        yaxis_tickformat="$,.0f",
        template="plotly_white",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=36, r=24, t=62, b=40),
    )
    return fig
