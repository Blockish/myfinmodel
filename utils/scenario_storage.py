"""Persistent storage for saved scenarios (Issue #13).

Stores scenario inputs and optional results snapshots on disk so compare-ready
scenarios survive Streamlit session restarts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import uuid

import numpy as np

from simulation.models import (
    GuardrailGR1Config,
    GuardrailGR2Config,
    GuardrailGR3Config,
    GuardrailGR4Config,
    HealthInsuranceConfig,
    SimulationInputs,
    SimulationResults,
    SpendingTier,
)

SCENARIO_SCHEMA_VERSION = 1


@dataclass
class ScenarioLoadReport:
    """Result summary for loading persistent scenarios."""

    scenarios: list[dict]
    warnings: list[str]
    recovered_count: int
    skipped_count: int


class ScenarioStorageError(RuntimeError):
    """Raised for invalid or corrupt scenario packages."""


def default_scenarios_dir() -> Path:
    """Return the default local directory for persistent scenarios."""
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "MyFinModel" / "scenarios"
    return Path.home() / ".myfinmodel" / "scenarios"


def save_scenario_snapshot(
    *,
    name: str,
    inputs: SimulationInputs,
    results: SimulationResults | None,
    base_dir: Path | None = None,
) -> Path:
    """Persist a scenario package and return the final package directory."""
    if not name.strip():
        raise ValueError("Scenario name must be non-empty.")

    root = (base_dir or default_scenarios_dir()).expanduser()
    root.mkdir(parents=True, exist_ok=True)

    slug = _slugify(name)
    target_dir = root / slug
    backup_dir = root / f"{slug}.bak"
    temp_dir = root / f"{slug}.tmp-{uuid.uuid4().hex}"

    try:
        temp_dir.mkdir(parents=True, exist_ok=False)

        inputs_payload = asdict(inputs)
        inputs_path = temp_dir / "inputs.json"
        _write_json(inputs_path, inputs_payload)
        inputs_sha = _sha256_file(inputs_path)

        results_sha: str | None = None
        if results is not None:
            results_path = temp_dir / "results.npz"
            _write_results_npz(results_path, results)
            results_sha = _sha256_file(results_path)

        manifest = {
            "schema_version": SCENARIO_SCHEMA_VERSION,
            "name": name.strip(),
            "saved_at_utc": datetime.now(UTC).isoformat(),
            "inputs_hash": inputs_sha,
            "results_hash": results_sha,
            "has_results": results is not None,
            "inputs_content_hash": inputs.content_hash(),
            "seed": int(inputs.random_seed),
        }
        _write_json(temp_dir / "manifest.json", manifest)

        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        if target_dir.exists():
            target_dir.replace(backup_dir)
        temp_dir.replace(target_dir)
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    return target_dir


def load_scenario_snapshots(base_dir: Path | None = None) -> ScenarioLoadReport:
    """Load scenario packages from disk and return session-compatible entries."""
    root = (base_dir or default_scenarios_dir()).expanduser()
    if not root.exists():
        return ScenarioLoadReport(scenarios=[], warnings=[], recovered_count=0, skipped_count=0)

    scenarios: list[dict] = []
    warnings: list[str] = []
    recovered_count = 0
    skipped_count = 0

    for pkg in sorted(root.iterdir()):
        if not pkg.is_dir():
            continue
        if pkg.name.endswith(".bak") or ".tmp-" in pkg.name or ".corrupt-" in pkg.name:
            continue

        try:
            scenario = _load_single_package(pkg)
            scenarios.append(scenario)
            continue
        except Exception as exc:
            backup = root / f"{pkg.name}.bak"
            if backup.exists() and backup.is_dir():
                try:
                    scenario = _load_single_package(backup)
                    quarantine = root / f"{pkg.name}.corrupt-{_now_compact()}"
                    pkg.replace(quarantine)
                    shutil.copytree(backup, pkg)
                    scenarios.append(_load_single_package(pkg))
                    recovered_count += 1
                    warnings.append(
                        f"Recovered scenario '{scenario['name']}' from backup after corruption in {pkg.name}."
                    )
                    continue
                except Exception:
                    pass

            skipped_count += 1
            quarantine = root / f"{pkg.name}.corrupt-{_now_compact()}"
            try:
                pkg.replace(quarantine)
                warnings.append(
                    f"Skipped corrupt scenario package {pkg.name}; moved to {quarantine.name}."
                )
            except Exception:
                warnings.append(
                    f"Skipped corrupt scenario package {pkg.name}; quarantine failed ({exc})."
                )

    return ScenarioLoadReport(
        scenarios=scenarios,
        warnings=warnings,
        recovered_count=recovered_count,
        skipped_count=skipped_count,
    )


def _load_single_package(pkg_dir: Path) -> dict:
    manifest_path = pkg_dir / "manifest.json"
    inputs_path = pkg_dir / "inputs.json"

    if not manifest_path.exists() or not inputs_path.exists():
        raise ScenarioStorageError(f"Missing required files in {pkg_dir.name}.")

    manifest = _read_json(manifest_path)
    _validate_manifest(manifest)

    if _sha256_file(inputs_path) != manifest["inputs_hash"]:
        raise ScenarioStorageError(f"inputs.json checksum mismatch in {pkg_dir.name}.")

    inputs_data = _read_json(inputs_path)
    inputs = _inputs_from_dict(inputs_data)

    results: SimulationResults | None = None
    if manifest.get("has_results", False):
        results_path = pkg_dir / "results.npz"
        expected = manifest.get("results_hash")
        if not results_path.exists() or not expected:
            raise ScenarioStorageError(f"results.npz missing in {pkg_dir.name}.")
        if _sha256_file(results_path) != expected:
            raise ScenarioStorageError(f"results.npz checksum mismatch in {pkg_dir.name}.")
        results = _read_results_npz(results_path, inputs)

    return {
        "name": str(manifest["name"]),
        "inputs": inputs,
        "results": results,
        "saved_at_utc": manifest.get("saved_at_utc"),
        "package_dir": str(pkg_dir),
    }


def _write_results_npz(path: Path, results: SimulationResults) -> None:
    events = np.asarray(results.events).astype("<U16")
    np.savez_compressed(
        path,
        portfolio=results.portfolio,
        real_portfolio=results.real_portfolio,
        spend=results.spend,
        real_spend=results.real_spend,
        gross_wd=results.gross_wd,
        net_wd=results.net_wd,
        wr=results.wr,
        cum_inf=results.cum_inf,
        ss_income=results.ss_income,
        health_cost=results.health_cost,
        events=events,
        ret_draws=results.ret_draws,
        inf_draws=results.inf_draws,
        ages=np.asarray(results.ages, dtype=np.int64),
        n_paths=np.asarray([results.n_paths], dtype=np.int64),
        plan_years=np.asarray([results.plan_years], dtype=np.int64),
    )


def _read_results_npz(path: Path, inputs: SimulationInputs) -> SimulationResults:
    with np.load(path, allow_pickle=False) as data:
        required = {
            "portfolio",
            "real_portfolio",
            "spend",
            "real_spend",
            "gross_wd",
            "net_wd",
            "wr",
            "cum_inf",
            "ss_income",
            "health_cost",
            "events",
            "ret_draws",
            "inf_draws",
            "ages",
            "n_paths",
            "plan_years",
        }
        missing = sorted(required.difference(set(data.files)))
        if missing:
            raise ScenarioStorageError(f"results.npz is missing fields: {', '.join(missing)}")

        return SimulationResults(
            portfolio=np.array(data["portfolio"], copy=True),
            real_portfolio=np.array(data["real_portfolio"], copy=True),
            spend=np.array(data["spend"], copy=True),
            real_spend=np.array(data["real_spend"], copy=True),
            gross_wd=np.array(data["gross_wd"], copy=True),
            net_wd=np.array(data["net_wd"], copy=True),
            wr=np.array(data["wr"], copy=True),
            cum_inf=np.array(data["cum_inf"], copy=True),
            ss_income=np.array(data["ss_income"], copy=True),
            health_cost=np.array(data["health_cost"], copy=True),
            events=np.array(data["events"], copy=True),
            ret_draws=np.array(data["ret_draws"], copy=True),
            inf_draws=np.array(data["inf_draws"], copy=True),
            ages=[int(x) for x in np.array(data["ages"], copy=True).tolist()],
            n_paths=int(np.array(data["n_paths"], copy=True)[0]),
            plan_years=int(np.array(data["plan_years"], copy=True)[0]),
            inputs=inputs,
        )


def _inputs_from_dict(data: dict) -> SimulationInputs:
    spending_tiers = [
        SpendingTier(
            start_age=int(t["start_age"]),
            end_age=int(t["end_age"]),
            annual_spend=float(t["annual_spend"]),
        )
        for t in data.get("spending_tiers", [])
    ]

    return SimulationInputs(
        port_start=float(data["port_start"]),
        taxable_value=float(data.get("taxable_value", 0.0)),
        tax_deferred_value=float(data.get("tax_deferred_value", 0.0)),
        roth_value=float(data.get("roth_value", 0.0)),
        unrealized_gain_pct=float(data.get("unrealized_gain_pct", 0.30)),
        ltcg_rate=float(data.get("ltcg_rate", 0.15)),
        ord_income_rate=float(data.get("ord_income_rate", 0.22)),
        current_age=int(data.get("current_age", 65)),
        retire_age=int(data.get("retire_age", 65)),
        ss_start_age=int(data.get("ss_start_age", 67)),
        plan_years=int(data.get("plan_years", 35)),
        filing_status=str(data.get("filing_status", "Single")),
        spending_tiers=spending_tiers,
        spend_floor=float(data.get("spend_floor", 0.0)),
        spend_ceiling=float(data.get("spend_ceiling", 2_000_000.0)),
        ss_enabled=bool(data.get("ss_enabled", True)),
        ss_annual=float(data.get("ss_annual", 24_000.0)),
        ss_cola=float(data.get("ss_cola", 0.025)),
        health=HealthInsuranceConfig(**data.get("health", {})),
        ret_mean=float(data.get("ret_mean", 0.065)),
        ret_std=float(data.get("ret_std", 0.12)),
        ret_inf_corr=float(data.get("ret_inf_corr", 0.10)),
        inf_mean=float(data.get("inf_mean", 0.03)),
        inf_std=float(data.get("inf_std", 0.015)),
        inf_floor=float(data.get("inf_floor", 0.01)),
        n_paths=int(data.get("n_paths", 1_000)),
        random_seed=int(data.get("random_seed", 42)),
        gr1=GuardrailGR1Config(**data.get("gr1", {})),
        gr2=GuardrailGR2Config(**data.get("gr2", {})),
        gr3=GuardrailGR3Config(**data.get("gr3", {})),
        gr4=GuardrailGR4Config(**data.get("gr4", {})),
    )


def _validate_manifest(manifest: dict) -> None:
    required = {"schema_version", "name", "inputs_hash", "has_results"}
    missing = required.difference(set(manifest.keys()))
    if missing:
        raise ScenarioStorageError(f"manifest.json missing fields: {', '.join(sorted(missing))}")
    if int(manifest["schema_version"]) != SCENARIO_SCHEMA_VERSION:
        raise ScenarioStorageError(
            f"Unsupported schema version: {manifest['schema_version']}"
        )


def _write_json(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _slugify(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", name.strip().lower())
    cleaned = cleaned.strip("-")
    return cleaned or "scenario"


def _now_compact() -> str:
    return datetime.now(UTC).strftime("%Y%m%d%H%M%S")
