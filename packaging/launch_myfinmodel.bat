@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "LAUNCHER_EXE=%SCRIPT_DIR%MyFinModelLauncher.exe"

if not exist "%LAUNCHER_EXE%" (
  echo Could not find MyFinModelLauncher.exe in:
  echo %SCRIPT_DIR%
  echo.
  echo Re-extract the full portable folder and try again.
  pause
  exit /b 1
)

start "" "%LAUNCHER_EXE%"
exit /b 0
