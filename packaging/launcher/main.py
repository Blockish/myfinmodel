"""Portable launcher for running the Streamlit app with port fallback."""

from __future__ import annotations

import logging
import multiprocessing
import os
import socket
import sys
import time
import webbrowser
from pathlib import Path
from typing import Iterable

APP_NAME = "MyFinModel"
PREFERRED_PORT = 8501
MAX_PORT = 8510
FALLBACK_PORTS = range(8502, MAX_PORT + 1)
STARTUP_TIMEOUT_SECONDS = 20
POLL_INTERVAL_SECONDS = 0.25


def _logs_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_NAME / "logs"
    return Path.home() / "AppData" / "Local" / APP_NAME / "logs"


def _configure_logger() -> logging.Logger:
    log_dir = _logs_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("myfinmodel.launcher")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    file_handler = logging.FileHandler(log_dir / "launcher.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger


def _iterate_candidate_ports() -> Iterable[int]:
    yield PREFERRED_PORT
    yield from FALLBACK_PORTS


def _is_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


def _select_port() -> int:
    for port in _iterate_candidate_ports():
        if _is_port_available(port):
            return port
    raise RuntimeError(
        f"No available local port found from {PREFERRED_PORT} through {MAX_PORT}."
    )


def _repository_root() -> Path:
    if getattr(sys, "frozen", False):
        # PyInstaller one-dir uses _MEIPASS; fallback to executable folder when unavailable.
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parents[2]


def _resolve_app_path() -> Path:
    app_path = _repository_root() / "app.py"
    if not app_path.exists():
        raise FileNotFoundError(f"Could not find Streamlit entrypoint: {app_path}")
    return app_path


def _wait_for_port(port: int, timeout_seconds: int) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(POLL_INTERVAL_SECONDS)
    return False


def _run_streamlit(app_path: str, port: int) -> None:
    from streamlit.web import cli as stcli

    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
        "--server.address",
        "127.0.0.1",
        "--server.port",
        str(port),
    ]
    stcli.main()


def main() -> int:
    multiprocessing.freeze_support()
    logger = _configure_logger()

    def _notify_user(message: str) -> None:
        """Best-effort user-visible error for windowless launcher builds."""
        try:
            import ctypes  # type: ignore[attr-defined]

            ctypes.windll.user32.MessageBoxW(0, message, APP_NAME, 0x10)
        except Exception:
            print(message)

    try:
        app_path = _resolve_app_path()
        port = _select_port()
        logger.info("Selected local port: %s", port)
    except Exception as exc:
        logger.exception("Failed during launcher setup: %s", exc)
        _notify_user(f"{APP_NAME} failed to start: {exc}")
        return 1

    streamlit_process = multiprocessing.Process(
        target=_run_streamlit,
        args=(str(app_path), port),
        daemon=False,
    )

    try:
        streamlit_process.start()
    except Exception as exc:
        logger.exception("Failed to start Streamlit process: %s", exc)
        _notify_user(f"{APP_NAME} failed to start: {exc}")
        return 1

    if not _wait_for_port(port, STARTUP_TIMEOUT_SECONDS):
        logger.error("Streamlit did not start within timeout (%ds).", STARTUP_TIMEOUT_SECONDS)
        streamlit_process.terminate()
        streamlit_process.join(timeout=3)
        _notify_user(f"{APP_NAME} failed to start. See launcher log for details.")
        return 1

    url = f"http://127.0.0.1:{port}"
    logger.info("Opening browser at %s", url)
    webbrowser.open(url)

    streamlit_process.join()
    return streamlit_process.exitcode or 0
