from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from simulation.models import SimulationInputs, SimulationResults, SpendingTier
from utils.scenario_storage import (
    ScenarioStorageError,
    load_scenario_snapshots,
    save_scenario_snapshot,
)


def _build_inputs(*, seed: int = 123) -> SimulationInputs:
    return SimulationInputs(
        port_start=1_000_000.0,
        spending_tiers=[SpendingTier(start_age=65, end_age=67, annual_spend=50_000.0)],
        current_age=65,
        retire_age=65,
        plan_years=3,
        n_paths=2,
        random_seed=seed,
    )


def _build_results(inputs: SimulationInputs, *, offset: float = 0.0) -> SimulationResults:
    base = np.array(
        [
            [1_000_000.0 + offset, 950_000.0 + offset, 900_000.0 + offset],
            [1_000_000.0 + offset, 925_000.0 + offset, 875_000.0 + offset],
        ],
        dtype=float,
    )
    zeros = np.zeros_like(base)
    wr = np.array(
        [
            [0.05, 0.052, 0.055],
            [0.05, 0.054, 0.057],
        ],
        dtype=float,
    )
    events = np.array(
        [
            ["NONE", "WR-WARN", "NONE"],
            ["NONE", "NONE", "PV-DOWN"],
        ],
        dtype="<U16",
    )
    inf = np.array(
        [
            [0.02, 0.03, 0.025],
            [0.02, 0.028, 0.03],
        ],
        dtype=float,
    )

    return SimulationResults(
        portfolio=base,
        real_portfolio=base,
        spend=np.full_like(base, 50_000.0),
        real_spend=np.full_like(base, 49_000.0),
        gross_wd=np.full_like(base, 55_000.0),
        net_wd=np.full_like(base, 50_000.0),
        wr=wr,
        cum_inf=np.array(
            [[1.02, 1.0506, 1.0769], [1.02, 1.0486, 1.0801]],
            dtype=float,
        ),
        ss_income=zeros,
        health_cost=np.full_like(base, 4_000.0),
        events=events,
        ret_draws=np.array(
            [[0.06, -0.02, 0.04], [0.05, -0.03, 0.03]],
            dtype=float,
        ),
        inf_draws=inf,
        ages=[65, 66, 67],
        n_paths=2,
        plan_years=3,
        inputs=inputs,
    )


def test_scenario_snapshot_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "scenarios"
    inputs = _build_inputs(seed=42)
    results = _build_results(inputs)

    save_scenario_snapshot(name="Baseline", inputs=inputs, results=results, base_dir=root)
    report = load_scenario_snapshots(base_dir=root)

    assert report.recovered_count == 0
    assert report.skipped_count == 0
    assert len(report.scenarios) == 1

    loaded = report.scenarios[0]
    assert loaded["name"] == "Baseline"
    loaded_results = loaded["results"]
    assert isinstance(loaded_results, SimulationResults)
    assert loaded_results.inputs.random_seed == 42
    assert np.array_equal(loaded_results.portfolio, results.portfolio)
    assert np.array_equal(loaded_results.events, results.events)


def test_recover_from_backup_when_current_package_corrupt(tmp_path: Path) -> None:
    root = tmp_path / "scenarios"

    inputs_a = _build_inputs(seed=100)
    results_a = _build_results(inputs_a, offset=0.0)
    save_scenario_snapshot(name="Retire Plan", inputs=inputs_a, results=results_a, base_dir=root)

    inputs_b = _build_inputs(seed=200)
    results_b = _build_results(inputs_b, offset=100_000.0)
    save_scenario_snapshot(name="Retire Plan", inputs=inputs_b, results=results_b, base_dir=root)

    pkg = root / "retire-plan"
    assert (root / "retire-plan.bak").exists()

    (pkg / "results.npz").write_bytes(b"not-a-valid-npz")

    report = load_scenario_snapshots(base_dir=root)

    assert report.recovered_count == 1
    assert report.skipped_count == 0
    assert len(report.scenarios) == 1

    loaded_results = report.scenarios[0]["results"]
    assert isinstance(loaded_results, SimulationResults)
    assert loaded_results.inputs.random_seed == 100
    assert np.array_equal(loaded_results.portfolio, results_a.portfolio)


def test_quarantine_corrupt_package_when_no_valid_backup(tmp_path: Path) -> None:
    root = tmp_path / "scenarios"

    inputs = _build_inputs(seed=77)
    results = _build_results(inputs)
    save_scenario_snapshot(name="Single", inputs=inputs, results=results, base_dir=root)

    pkg = root / "single"
    (pkg / "manifest.json").write_text("{}", encoding="utf-8")

    report = load_scenario_snapshots(base_dir=root)

    assert report.recovered_count == 0
    assert report.skipped_count == 1
    assert len(report.scenarios) == 0

    quarantined = [p for p in root.iterdir() if p.is_dir() and ".corrupt-" in p.name]
    assert quarantined


def test_slug_collision_raises_clear_error(tmp_path: Path) -> None:
    root = tmp_path / "scenarios"

    inputs_a = _build_inputs(seed=1)
    results_a = _build_results(inputs_a)
    save_scenario_snapshot(name="Retire Plan", inputs=inputs_a, results=results_a, base_dir=root)

    inputs_b = _build_inputs(seed=2)
    results_b = _build_results(inputs_b, offset=5_000.0)

    with pytest.raises(ScenarioStorageError, match="collides with existing saved scenario"):
        save_scenario_snapshot(
            name="Retire-Plan",
            inputs=inputs_b,
            results=results_b,
            base_dir=root,
        )
