# Issue #13 Lean Technical Spec — Persistent Saved Scenarios

## Goal

Enable saved scenarios to persist across app restarts while preserving exact saved results for later comparison.

## Scope

- Persist scenario inputs and results snapshots to local disk.
- Load saved scenarios automatically at app startup.
- Keep existing in-session scenario UX in the sidebar.
- Ensure loaded scenarios can be compared immediately without recomputation.

## Non-Goals (for this change)

- Cloud sync or multi-device sharing.
- Cross-version migration beyond schema validation.
- Dedicated "recompute and verify" workflow.

## User Workflow

1. User runs simulation.
2. User saves scenario from sidebar.
3. App persists:
   - inputs snapshot
   - results snapshot (if results are current, not stale)
   - manifest metadata (name, timestamps, schema version, seed, hashes)
4. On next app start, saved scenarios are discovered and loaded.
5. User can load a saved scenario and immediately view/compare exact saved results.
6. User may still click "Run Simulation" to recompute from loaded inputs.

## Storage Design

- Root directory:
  - Windows default: `%LOCALAPPDATA%/MyFinModel/scenarios`
  - Fallback: `~/.myfinmodel/scenarios`
- Per-scenario package directory (slug from scenario name)
- Files per package:
  - `manifest.json`
  - `inputs.json`
  - `results.npz` (optional if no current results)

## Data Integrity

- `manifest.json` stores SHA-256 checksums for inputs and optional results payload.
- Loader verifies checksums and required fields before accepting a scenario.
- Corrupt packages are skipped with warning and do not block app startup.

## Atomicity and Recovery

- Save uses temp-directory write then atomic rename.
- On overwrite, previous package is retained as `<slug>.bak` backup.
- If current package is corrupt and backup is valid, loader restores from backup.
- If neither current nor backup is valid, package is quarantined as `<slug>.corrupt-<timestamp>`.

## Session-State Contract

- `st.session_state["scenarios"]` remains list[dict] with keys:
  - `name`
  - `inputs`
  - `results`
- Additional optional metadata keys may be present for display/debug and are ignored by compare logic.

## Testing Plan

- Round-trip save/load preserves inputs and result arrays exactly.
- Overwrite creates backup.
- Corrupt current package recovers from backup.
- Corrupt package without backup is quarantined and skipped.

## PR Chunks

### Chunk 1

- Add storage module and serialization/deserialization.
- Wire `ui/scenarios.py` to auto-load and persist saves.
- Keep existing UX intact.

### Chunk 2

- Add corruption handling and backup recovery paths.
- Add persistence tests for round-trip and recovery.
- Update user guide behavior notes.
