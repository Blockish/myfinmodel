"""Smoke tests for Phase 4 chart builders in utils.charts."""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from utils.charts import (
    create_comparison_overlay,
    create_guardrail_event_chart,
    create_inflation_fan_chart,
    create_portfolio_fan_chart,
    create_spending_fan_chart,
    create_survival_donut,
    create_withdrawal_rate_chart,
)


def _sample_matrix(n_paths: int = 200, years: int = 8, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = rng.normal(loc=1.0, scale=0.12, size=(n_paths, years))
    growth = np.cumprod(base, axis=1)
    return np.maximum(growth * 1_000_000, 0.0)


def test_create_portfolio_fan_chart_returns_figure():
    matrix = _sample_matrix()
    ages = list(range(60, 68))

    fig = create_portfolio_fan_chart(
        portfolio_matrix=matrix,
        ages=ages,
        n_paths=matrix.shape[0],
        ss_start_age=67,
        medicare_age=65,
    )

    assert isinstance(fig, go.Figure)
    # 2 band traces + 5 percentile traces
    assert len(fig.data) == 7
    assert fig.layout.xaxis.title.text == "Age"
    assert fig.layout.xaxis.tickfont.size >= 14
    assert fig.layout.yaxis.tickfont.size >= 14


def test_create_spending_fan_chart_returns_figure():
    matrix = np.full((150, 6), 50_000.0)
    ages = list(range(65, 71))
    floor = np.full(6, 35_000.0)
    ceiling = np.full(6, 75_000.0)

    fig = create_spending_fan_chart(
        spend_matrix=matrix,
        ages=ages,
        n_paths=matrix.shape[0],
        floor_line=floor,
        ceiling_line=ceiling,
        ss_start_age=67,
        medicare_age=65,
    )

    assert isinstance(fig, go.Figure)
    # 2 band + 5 percentile + floor + ceiling
    assert len(fig.data) == 9


def test_create_guardrail_event_chart_returns_figure():
    ages = [60, 61, 62, 63]
    events = np.array(
        [
            ["NONE", "PV-DOWN", "WR-WARN", "INF"],
            ["PV-UP", "PV-UP", "WR-CRIT", "NONE"],
            ["NONE", "WR-LOW", "WR-WARN", "ACA-BREACH"],
        ],
        dtype=object,
    )

    fig = create_guardrail_event_chart(events_matrix=events, ages=ages, n_paths=events.shape[0])

    assert isinstance(fig, go.Figure)
    # Default excludes NONE => 7 event traces
    assert len(fig.data) == 7
    assert fig.layout.barmode == "stack"


def test_create_survival_donut_returns_figure():
    fig = create_survival_donut(survived_paths=87, total_paths=100, plan_years=35, final_age=94)

    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    assert fig.data[0].type == "pie"


def test_create_withdrawal_rate_chart_fan_and_box_modes():
    rng = np.random.default_rng(7)
    wr = np.clip(rng.normal(loc=0.045, scale=0.012, size=(120, 7)), 0.0, 0.2)
    ages = list(range(65, 72))

    fan = create_withdrawal_rate_chart(wr_matrix=wr, ages=ages, mode="fan")
    box = create_withdrawal_rate_chart(wr_matrix=wr, ages=ages, mode="box")

    assert isinstance(fan, go.Figure)
    assert isinstance(box, go.Figure)
    assert len(fan.data) >= 5
    assert len(box.data) == len(ages)
    assert fan.layout.xaxis.tickfont.size >= 14
    assert fan.layout.yaxis.tickfont.size >= 14


def test_create_inflation_fan_chart_returns_figure():
    rng = np.random.default_rng(11)
    inf = rng.normal(loc=0.03, scale=0.015, size=(300, 10))
    inf = np.clip(inf, 0.01, None)
    ages = list(range(60, 70))

    fig = create_inflation_fan_chart(
        inf_matrix=inf,
        ages=ages,
        inf_floor=0.01,
        inf_mean=0.03,
        gr4_inf_trigger=0.045,
    )

    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 5


def test_create_comparison_overlay_returns_figure():
    ages = list(range(60, 68))
    line_a = np.linspace(1_000_000, 1_400_000, len(ages))
    line_b = np.linspace(1_000_000, 1_050_000, len(ages))

    fig = create_comparison_overlay(
        ages=ages,
        scenario_to_median={
            "Base": line_a,
            "Conservative": line_b,
        },
    )

    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 2
