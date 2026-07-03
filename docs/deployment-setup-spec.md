# Streamlit Launcher Packaging Deployment Spec

This document rewrites the deployment spec for **Blockish/myfinmodel** as a step-by-step plan for shipping the existing Streamlit app as a **local desktop-style experience** instead of deploying it to a hosted server.

The app remains a Streamlit app and runs on `localhost`, but it is wrapped so users can launch it by double-clicking a packaged entry point.

It covers both supported release styles:

- **Portable folder distribution**: zip file, no installer
- **Installer-style distribution**: Windows installer built with Inno Setup

---

## 1) Objective

Deliver a repeatable Windows packaging flow for `myfinmodel` that:

1. Keeps the current Streamlit app architecture unchanged.
2. Starts locally from a double-click launcher.
3. Prefers `http://localhost:8501`.
4. Falls back to another available local port if `8501` is already in use.
5. Supports both portable and installer-based distribution.
6. Provides a clear validation path before final release.

---

## 2) Scope and non-goals

### In scope

- Packaging the existing `app.py` Streamlit entrypoint for local Windows use
- Adding a launcher layer around Streamlit
- Building a portable release artifact
- Building an installer-style release artifact with Inno Setup
- Defining smoke-test and acceptance steps

### Out of scope

- Rewriting the UI away from Streamlit
- Deploying to a public or internal web server
- Multi-user server hosting
- Auto-update infrastructure

---

## 3) Current application baseline

Current repo assumptions:

- App entrypoint is `app.py`
- App is launched in development with `streamlit run app.py`
- Core dependencies include Streamlit, Plotly, Pandas, NumPy, SciPy, and OpenPyXL
- The browser-based UI is acceptable as long as launch/setup feels like a local app

---

## 4) Required runtime behavior

The packaged launcher must perform the following steps:

1. Start the bundled Streamlit app in the background.
2. Try port `8501` first.
3. If `8501` is busy, select the next available local port from a defined fallback range.
4. Open the default browser automatically to the selected local URL.
5. Keep the Streamlit process running until the user closes the app window or stops the process.
6. Provide a simple failure path if startup does not succeed.

### Port behavior

- Preferred port: `8501`
- Fallback behavior: probe for the next free port in a small local range such as `8502` through `8510`
- The launcher should open the browser using the actual selected port
- The selected port should be written to a launcher log for troubleshooting

### Streamlit launch flags

- `--server.headless true`
- `--browser.gatherUsageStats false`
- `--server.port <selected-port>`

---

## 5) Packaging deliverables to maintain in the repo

The packaging spec should assume a repo structure like:

```text
packaging/
  launch_streamlit.py
  launch_myfinmodel.bat
  myfinmodel.spec
  build_windows.ps1
  inno/
    MyFinModel.iss
```

Expected purpose of each file:

- `launch_streamlit.py`: primary launcher wrapper that starts Streamlit and opens the browser
- `launch_myfinmodel.bat`: double-clickable entry point for portable distribution
- `myfinmodel.spec`: reproducible PyInstaller configuration
- `build_windows.ps1`: repeatable local build script for the packaging flow
- `inno/MyFinModel.iss`: installer definition for installer-style releases

---

## 6) Step-by-step deployment plan

### Step 1: Validate the app in development mode

Before packaging, confirm the existing app works in a clean environment.

```powershell
python -m venv .venv-build
.\.venv-build\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

Validation goal:

- App loads locally
- Charts render correctly
- Primary user flows work before packaging begins

### Step 2: Add the launcher wrapper

Create `packaging/launch_streamlit.py` as the launcher responsible for:

1. Resolving the correct path to `app.py`
2. Detecting packaged versus development execution
3. Choosing a local port
4. Starting Streamlit in the background
5. Waiting briefly for startup
6. Opening the browser to the running local URL
7. Writing minimal logs to `%LOCALAPPDATA%\MyFinModel\logs`
8. Returning a user-friendly error when launch fails

Launcher requirements:

- Prefer port `8501`
- Fall back automatically when `8501` is occupied
- Handle missing `app.py`
- Handle failed subprocess startup
- Avoid leaving a visible terminal window for normal user launch flows

### Step 3: Add the double-click entry point

Create `packaging/launch_myfinmodel.bat` for the portable distribution.

Purpose:

- Give non-technical users a double-click launch target
- Start the packaged launcher with minimal console noise
- Keep the launch path simple for testing and troubleshooting

### Step 4: Build the packaged launcher

Use PyInstaller in **onedir** mode as the default packaging strategy.

```powershell
pip install pyinstaller
pyinstaller --noconfirm --clean --onedir --name MyFinModelLauncher packaging\launch_streamlit.py
```

Rationale:

- `onedir` is the safer default for Streamlit and its dynamic assets
- `onefile` may be evaluated later, but it is not the primary delivery format for this plan

### Step 5: Assemble the portable folder release

Build the portable release from the PyInstaller output plus the user-facing launcher.

Target layout:

```text
MyFinModel/
  MyFinModelLauncher.exe
  launch_myfinmodel.bat
  _internal/
  VERSION.txt
  README-Run.txt
```

Portable release steps:

1. Copy the PyInstaller output into a clean release folder
2. Add `launch_myfinmodel.bat`
3. Add `VERSION.txt`
4. Add `README-Run.txt` with unzip and launch instructions
5. Zip the folder as the portable artifact

Portable artifact name:

- `MyFinModel-vX.Y.Z-portable.zip`

### Step 6: Build the installer-style release

After the portable flow is working, build the installer version with Inno Setup.

Installer responsibilities:

- Install into `Program Files` by default
- Copy the packaged launcher and bundled files
- Create Start Menu shortcut
- Optionally create Desktop shortcut
- Register uninstall information
- Optionally offer to launch the app at the end of setup

Target output:

- `MyFinModel-Setup-vX.Y.Z.exe`

### Step 7: Run deployment testing

Test both release styles on a Windows machine that represents the target user environment.

Required checks:

1. Portable zip launches by double-click
2. Installer-based install launches by shortcut
3. Browser opens automatically
4. Port `8501` is used when available
5. Port fallback works when `8501` is already occupied
6. App functions without a preinstalled system Python runtime
7. Core app workflows behave the same as development mode

### Step 8: Publish release artifacts

For each release candidate:

1. Finalize version number
2. Build portable artifact
3. Smoke test portable artifact
4. Build installer artifact
5. Smoke test installer artifact
6. Publish both artifacts together

---

## 7) Portable folder distribution spec

### Distribution intent

Use this option for:

- internal testing
- rapid stakeholder review
- users who prefer unzip-and-run delivery

### End-user flow

1. Download the zip file
2. Extract it to a writable folder
3. Double-click `launch_myfinmodel.bat`
4. Wait for the browser to open locally

### Advantages

- Fastest packaging and validation loop
- No installer or admin workflow required

### Limitations

- No Start Menu integration
- No uninstall registration
- Users must keep the full extracted folder intact

---

## 8) Installer-style distribution spec

### Distribution intent

Use this option for:

- broader Windows rollout
- cleaner user setup
- easier uninstall and shortcut management

### Inno Setup requirements

`packaging/inno/MyFinModel.iss` should define:

- application name and version
- install directory
- file copy list from the packaged build output
- Start Menu shortcut
- optional Desktop shortcut
- uninstall behavior
- optional post-install launch checkbox

### End-user flow

1. Run `MyFinModel-Setup-vX.Y.Z.exe`
2. Accept the installation path or use the default
3. Complete the setup wizard
4. Launch from Start Menu or Desktop shortcut

### Advantages

- Most polished user experience
- Standard install/uninstall behavior

### Limitations

- Additional packaging step
- Installer maintenance overhead

---

## 9) Testing plan

### Functional test matrix

Test these scenarios for both release styles where applicable:

- Fresh Windows machine
- Standard user account
- Different default browsers
- Port `8501` available
- Port `8501` already occupied
- Repeated close and relaunch cycle
- Normal chart rendering and tab usage

### Failure-path testing

Confirm the launcher handles:

- missing packaged files
- launcher startup failure
- port-selection fallback
- browser launch delay

### Acceptance criteria

The spec is satisfied when:

- users can launch by double-click
- the app still runs as Streamlit on `localhost`
- `8501` is preferred
- a fallback port is used automatically when needed
- both portable and installer release paths are documented and testable

---

## 10) Security and operational notes

- Do not bundle secrets, API keys, or environment-specific credentials
- Keep logs minimal and free of sensitive financial inputs
- Expect some unsigned executables to trigger antivirus warnings on some systems
- Consider code-signing for wider distribution

---

## 11) Recommended implementation order

1. Validate current Streamlit behavior in a clean environment
2. Implement and test the launcher wrapper
3. Produce and verify the portable folder release first
4. Add and verify the Inno Setup installer second
5. Publish both artifacts only after the launcher and fallback-port behavior are confirmed

---

## 12) Open questions for final confirmation

These points should be confirmed before final packaging implementation begins:

1. Is Windows the only target platform for the packaged release?
2. Should the portable distribution launch from `.bat`, `.exe`, or both?
3. What fallback port range should be considered acceptable beyond `8501`?
4. Do you want installer builds to create a Desktop shortcut by default or make it optional?

---

This deployment spec preserves the current Streamlit app, shifts delivery to a double-click local launcher model, and supports both a portable zip flow and a polished Inno Setup installer flow.
