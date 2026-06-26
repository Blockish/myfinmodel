"""Chart utilities for the Monte Carlo retirement simulator."""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

PERCENTILE_BANDS = [
    (5, 95, "rgba(99,110,250,0.10)", "5th–95th percentile"),
    (10, 90, "rgba(99,110,250,0.15)", "10th–90th percentile"),
    (25, 75, "rgba(99,110,250,0.25)", "25th–75th percentile"),
]
MEDIAN_COLOR = "rgba(99,110,250,1.0)"
SUCCESS_COLOR = "#2ca02c"
FAILURE_COLOR = "#d62728"


def create_fan_chart(
    percentile_paths: dict[int, list[float]],
    years: int,
    title: str = "Portfolio Value — Fan Chart",
    initial_portfolio: float | None = None,
) -> go.Figure:
    """Create a Plotly fan chart from pre-computed percentile paths.

    Parameters
    ----------
    percentile_paths:
        Mapping of percentile integer → list of portfolio values (length years+1).
    years:
        Number of simulation years (used for the x-axis).
    title:
        Chart title.
    initial_portfolio:
        If provided, add a horizontal reference line at this value.
    """
    year_labels = list(range(years + 1))
    fig = go.Figure()

    for low_pct, high_pct, fill_color, name in PERCENTILE_BANDS:
        low = percentile_paths.get(low_pct)
        high = percentile_paths.get(high_pct)
        if low is None or high is None:
            continue
        # Upper boundary
        fig.add_trace(
            go.Scatter(
                x=year_labels,
                y=high,
                mode="lines",
                line=dict(width=0),
                showlegend=False,
                hoverinfo="skip",
                name=f"p{high_pct}",
            )
        )
        # Lower boundary – fill to previous trace
        fig.add_trace(
            go.Scatter(
                x=year_labels,
                y=low,
                mode="lines",
                line=dict(width=0),
                fill="tonexty",
                fillcolor=fill_color,
                name=name,
                hoverinfo="skip",
            )
        )

    # Median line
    median = percentile_paths.get(50)
    if median is not None:
        fig.add_trace(
            go.Scatter(
                x=year_labels,
                y=median,
                mode="lines",
                line=dict(color=MEDIAN_COLOR, width=2),
                name="Median (50th percentile)",
            )
        )

    # Optional initial portfolio reference line
    if initial_portfolio is not None:
        fig.add_hline(
            y=initial_portfolio,
            line_dash="dash",
            line_color="grey",
            annotation_text="Starting portfolio",
            annotation_position="bottom right",
        )

    # Zero line
    fig.add_hline(y=0, line_dash="dot", line_color="red", annotation_text="$0")

    fig.update_layout(
        title=title,
        xaxis_title="Year",
        yaxis_title="Portfolio Value ($)",
        yaxis_tickformat="$,.0f",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
        template="plotly_white",
    )
    return fig


def create_final_value_histogram(
    final_values: list[float],
    title: str = "Distribution of Final Portfolio Values",
) -> go.Figure:
    """Return a histogram of final portfolio values."""
    fig = go.Figure(
        go.Histogram(
            x=final_values,
            nbinsx=50,
            marker_color=MEDIAN_COLOR,
            opacity=0.75,
            name="Final value",
        )
    )
    fig.add_vline(
        x=0,
        line_dash="dash",
        line_color=FAILURE_COLOR,
        annotation_text="Depletion",
        annotation_position="top right",
    )
    fig.update_layout(
        title=title,
        xaxis_title="Final Portfolio Value ($)",
        yaxis_title="Number of Simulations",
        xaxis_tickformat="$,.0f",
        template="plotly_white",
    )
    return fig


def create_success_gauge(success_rate: float) -> go.Figure:
    """Create a gauge chart showing the plan success rate."""
    pct = success_rate * 100
    if pct >= 90:
        bar_color = SUCCESS_COLOR
    elif pct >= 75:
        bar_color = "#ff7f0e"
    else:
        bar_color = FAILURE_COLOR

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=pct,
            number={"suffix": "%", "font": {"size": 36}},
            title={"text": "Plan Success Rate"},
            gauge={
                "axis": {"range": [0, 100], "ticksuffix": "%"},
                "bar": {"color": bar_color},
                "steps": [
                    {"range": [0, 75], "color": "rgba(214,39,40,0.15)"},
                    {"range": [75, 90], "color": "rgba(255,127,14,0.15)"},
                    {"range": [90, 100], "color": "rgba(44,160,44,0.15)"},
                ],
                "threshold": {
                    "line": {"color": "black", "width": 3},
                    "thickness": 0.75,
                    "value": pct,
                },
            },
        )
    )
    fig.update_layout(height=300, template="plotly_white")
    return fig


def create_spending_fan_chart(
    results: list,
    years: int,
    title: str = "Annual Spending — Fan Chart",
) -> go.Figure:
    """Fan chart for annual spending across simulation paths."""
    if not results:
        return go.Figure()

    matrix = np.array([r.annual_spending for r in results])
    year_labels = list(range(1, years + 1))
    percentiles = [5, 10, 25, 50, 75, 90, 95]
    pct_paths = {p: np.percentile(matrix, p, axis=0).tolist() for p in percentiles}

    fig = go.Figure()
    for low_pct, high_pct, fill_color, name in PERCENTILE_BANDS:
        low = pct_paths.get(low_pct)
        high = pct_paths.get(high_pct)
        if low is None or high is None:
            continue
        fig.add_trace(
            go.Scatter(
                x=year_labels, y=high, mode="lines",
                line=dict(width=0), showlegend=False, hoverinfo="skip",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=year_labels, y=low, mode="lines",
                line=dict(width=0), fill="tonexty",
                fillcolor=fill_color, name=name, hoverinfo="skip",
            )
        )
    median = pct_paths.get(50)
    if median is not None:
        fig.add_trace(
            go.Scatter(
                x=year_labels, y=median, mode="lines",
                line=dict(color=MEDIAN_COLOR, width=2), name="Median spending",
            )
        )
    fig.update_layout(
        title=title,
        xaxis_title="Year",
        yaxis_title="Annual Spending ($)",
        yaxis_tickformat="$,.0f",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
        template="plotly_white",
    )
    return fig
