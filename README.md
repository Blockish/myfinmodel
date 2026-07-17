# myfinmodel

Monte Carlo Retirement Planner is a Streamlit app that simulates thousands of retirement portfolio outcomes using correlated return and inflation draws, then applies up to four dynamic guardrail rules — portfolio value, withdrawal rate, ACA MAGI, and inflation — to adjust spending automatically each year. Users configure custom spending tiers (front-loaded early retirement, post–Social Security, late-life), choose from preset or custom portfolio styles, and explore results through interactive percentile fan charts, guardrail event analysis, survival metrics, and downloadable data tables. It's built for early retirees, pre-Medicare households managing ACA cliffs, and anyone who wants a transparent, reproducible alternative to static spreadsheet projections.

Check out `docs/myfinmodel-user-guide.md` for details on using the app.

Dependency management and execution are uv-first in this repository.
The project intentionally uses `pyproject.toml` + `uv.lock` as the dependency source of truth.

## Quick start (fork and run from source)

1. Fork this repository in GitHub.
2. Clone your fork locally.
3. Install `uv` (https://docs.astral.sh/uv/).
4. Sync dependencies and run the app.

```bash
git clone <your-fork-url>
cd myfinmodel
uv sync --group dev
uv run streamlit run app.py --server.address localhost
```
See "Portable distribution" section for other setup and run options.

### Development checks

Run tests:

```bash
uv run pytest tests/ -v
```

Run slow/performance tests only:

```bash
uv run pytest -m slow -v
```

## Portable distribution (zip, no installer)

Use this path when you want a local, double-click launch experience for Windows users.

### Packaging assets and purpose

- `packaging/build_portable.ps1`: repeatable build script for the portable artifact.
- `packaging/myfinmodel.spec`: PyInstaller spec used by the build.
- `packaging/launch_myfinmodel.bat`: user-facing launcher included in the portable folder.
- `packaging/README-Run.txt`: end-user run instructions included in the portable folder.
- `packaging/launcher/main.py`: launcher entry logic that starts the app and opens the browser.

### Build a portable artifact (Windows)

From repository root:

```powershell
./packaging/build_portable.ps1 -Version "0.1.0"
```

Expected output:

- `dist/MyFinModel-vX.Y.Z-portable.zip`
- `dist/MyFinModel/` (assembled folder used to create the zip)

### Test the portable method

1. Extract the zip to a writable folder.
2. Open the extracted `MyFinModel` folder.
3. Double-click `launch_myfinmodel.bat`.
4. Confirm the default browser opens on localhost and the app loads.

Keep the extracted folder contents together, including `_internal` and `MyFinModelLauncher.exe`.

## Notes

- `requirements.txt` has been removed as an install path in favor of uv-managed dependencies.
- For deeper packaging details, see `docs/deployment-setup-spec.md`.
