# Phase 4 Implementation Plan — Results UI, Charts, and Exports

## Context
This plan captures the approved Phase 4 execution approach for MyFinModel and is intended for multi-session implementation continuity.

Inputs for this plan:
- Approved functional requirements in docs/MonteCarloRetirementPlanner-FuncSpec.md (Sections 4.1–4.6)
- Development guidance in docs/dev-design-spec.md (Phase 4)
- Existing Phase 1–3 implementation and passing test baseline
- User-approved UX decision: consolidated 6-tab results model + conditional Compare view

## Scope
In scope:
- Results tab rewrite in ui/outputs.py
- Chart utility rewrite in utils/charts.py
- CSV export tables in Results / Raw Data
- Scenario comparison view (conditional)
- New chart smoke tests
- Results/tables/charts mockup artifact for review-first workflow

Out of scope:
- Engine algorithm changes unrelated to results rendering
- Major validator refactors (except minimal compatibility fix if discovered as hard dependency)
- Deployment/packaging changes

## UX Decision Baseline
Use consolidated result tabs:
1. Success Metrics
2. Portfolio
3. Spending
4. Analysis (Guardrails + Inflation combined)
5. Tax Efficiency
6. Raw Data

Comparison tab/panel appears only when at least 2 saved scenarios with results are available.

## Architecture Constraints
- Keep simulation and validation layers free of Streamlit dependencies.
- Keep utils/charts.py free of Streamlit dependencies; return Plotly figures only.
- Keep app.py responsible for orchestration, stale banner state, and run metadata.
- Reuse SimulationResults array contract already produced by simulation/engine.py.

## Implementation Phases

### Phase A — Data Shaping Foundation (Blocking)
Objective:
- Centralize metrics and table-data derivation from SimulationResults in ui/outputs.py pure helper functions.

Deliverables:
- Canonical event-code ordering and display map.
- Metric derivation helpers for:
  - Portfolio outcomes
  - Spending outcomes
  - Guardrail trigger frequencies
  - Withdrawal-rate stats
- Depletion-age summary helper with all-survive handling.

Why first:
- All charts, cards, and downloadable tables depend on consistent computed aggregates.

### Phase B — Chart Utilities Rewrite
Objective:
- Replace legacy chart helpers with explicit Phase 4 chart builders in utils/charts.py.

Required chart builders:
1. Portfolio percentile fan (nominal/real)
2. Spending percentile fan (nominal/real + floor/ceiling overlays)
3. Guardrail event stacked bar by age
4. Survival donut
5. Withdrawal rate chart (fan or box mode)
6. Inflation fan with reference lines
7. Scenario comparison overlay (median lines)

Standards:
- Age-based x-axis.
- Shared annotation helper for SS start and Medicare lines.
- Stable color palette for event categories.

### Phase C — Results Layout Rewrite
Objective:
- Rebuild ui/outputs.py rendering from placeholder output to full tabbed Results experience.

Deliverables:
- 8 summary metric cards.
- Consolidated 6-tab structure.
- Per-chart toggles:
  - Nominal vs real for portfolio/spending
  - Fan vs box for withdrawal rate
- Conditional compare section when criteria met.

Integration notes:
- Preserve existing stale-results signaling and metadata rendering behavior driven by app.py.

### Phase D — Raw Data Tables + CSV Exports
Objective:
- Add all 5 required downloadable tables in Raw Data.

Tables:
1. Percentile Portfolio Paths
2. Percentile Spending Paths
3. Guardrail Event Frequency by Age
4. Inflation Statistics
5. Full Path Export (on-demand)

Guardrail:
- Add pre-generation warning with estimated row/file size for full-path export.

### Phase E — Testing and Verification
Objective:
- Add test coverage for charts and helper computations while preserving existing green baseline.

Deliverables:
- tests/test_charts.py with smoke + structural assertions.
- Optional pure-helper tests for outputs data shaping.
- Full pytest pass after integration.

Manual QA checklist:
- All tabs render with valid results.
- Toggle behavior updates charts correctly.
- Event counts align across cards/tables/charts.
- Compare appears only when valid scenarios exist.
- CSV downloads produce expected column sets.

### Phase F — Review Artifact First (Mockup)
Objective:
- Produce visual mockup before heavy implementation to confirm layout and expectations.

Deliverable:
- docs/results-tables-charts-mockup.html (single-file results-focused visual artifact)

Content:
- Results metadata row
- 8-card dashboard
- Consolidated sub-tab layout
- Chart placeholders and controls
- Raw data table/export treatment
- Conditional comparison visualization

## Risks and Mitigations
1. Risk: metric inconsistencies across cards/charts/tables.
Mitigation: single shared computation helpers used everywhere.

2. Risk: expensive full-path table render for large simulations.
Mitigation: on-demand generation with explicit warning.

3. Risk: compare mode ambiguity when scenarios have no results payload.
Mitigation: filter compare candidates to scenarios with attached results.

4. Risk: requirement drift between spec text and latest UX decisions.
Mitigation: preserve user-approved consolidated tab model as current source of truth for Phase 4 UI.

## Session Handoff Notes
Implementation can be split safely across sessions in this order:
1. Mockup artifact
2. Chart utilities
3. Outputs layout integration
4. Exports
5. Tests and QA

Blocking dependency order:
- Data-shaping helpers block chart/table consistency.
- Chart utility availability blocks final outputs tab assembly.

Parallelizable:
- Chart test scaffolding can begin once chart function signatures are fixed.
- Mockup artifact can be produced immediately and reviewed before coding charts.

## Acceptance Criteria
- Results UI matches approved consolidated tab structure.
- All required charts render and use age-based axes.
- Raw Data exports include required tables with working CSV download.
- Compare view works for at least two scenarios with stored results.
- New tests added and full suite passes.
- Mockup reviewed and approved prior to final UI polish.
