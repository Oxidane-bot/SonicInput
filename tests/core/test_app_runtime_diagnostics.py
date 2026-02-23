"""Runtime diagnostics tests for app entrypoint crash markers."""

import importlib.util
import json
import os
from pathlib import Path


def _load_app_module():
    module_path = Path(__file__).resolve().parents[2] / "app.py"
    spec = importlib.util.spec_from_file_location("sonicinput_app_entry", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


app = _load_app_module()


def _prepare_isolated_runtime(monkeypatch, tmp_path):
    """Isolate runtime diagnostics paths and side effects for tests."""
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(app, "_LOG_DIR", log_dir, raising=False)
    monkeypatch.setattr(app, "_RUNTIME_STATE_FILE", log_dir / "runtime_state.json", raising=False)
    monkeypatch.setattr(app, "_CRASH_LOG_FILE", log_dir / "crash.log", raising=False)
    monkeypatch.setattr(app, "_FAULT_LOG_FILE", log_dir / "fault.log", raising=False)
    monkeypatch.setattr(app, "_runtime_diagnostics_initialized", False, raising=False)
    monkeypatch.setattr(app, "_runtime_unclean_exit_detected", False, raising=False)
    monkeypatch.setattr(app, "_fault_log_handle", None, raising=False)
    monkeypatch.setattr(app, "app_logger", None, raising=False)
    monkeypatch.setattr(app, "LogCategory", None, raising=False)
    monkeypatch.setattr(app, "_configure_fault_handler", lambda: None, raising=False)

    registered_handlers = []
    monkeypatch.setattr(
        app.atexit,
        "register",
        lambda handler: registered_handlers.append(handler),
    )
    return registered_handlers


def test_initialize_runtime_diagnostics_writes_start_state(monkeypatch, tmp_path):
    registered_handlers = _prepare_isolated_runtime(monkeypatch, tmp_path)

    app.initialize_runtime_diagnostics()

    state = app._read_runtime_state()
    assert state is not None
    assert state["pid"] == os.getpid()
    assert state["clean_shutdown"] is False
    assert state["last_stage"] == "process_start"
    assert app._runtime_diagnostics_initialized is True
    assert registered_handlers == [app._on_process_exit]


def test_initialize_runtime_diagnostics_detects_previous_unclean_exit(
    monkeypatch, tmp_path
):
    _prepare_isolated_runtime(monkeypatch, tmp_path)
    app._write_runtime_state(
        {
            "pid": 99999,
            "startup_time": "2026-01-01T00:00:00+00:00",
            "clean_shutdown": False,
            "last_stage": "qt_event_loop_running",
        }
    )

    app.initialize_runtime_diagnostics()

    assert app._CRASH_LOG_FILE.exists()
    records = [
        json.loads(line)
        for line in app._CRASH_LOG_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(r.get("message") == "Detected previous unclean shutdown" for r in records)


def test_on_process_exit_marks_clean_shutdown(monkeypatch, tmp_path):
    _prepare_isolated_runtime(monkeypatch, tmp_path)
    app.initialize_runtime_diagnostics()

    app._runtime_unclean_exit_detected = False
    app._on_process_exit()

    state = app._read_runtime_state()
    assert state is not None
    assert state["clean_shutdown"] is True
    assert state["shutdown_reason"] == "normal_exit"
    assert state["last_stage"] == "process_exit"


def test_on_process_exit_preserves_unclean_shutdown(monkeypatch, tmp_path):
    _prepare_isolated_runtime(monkeypatch, tmp_path)
    app.initialize_runtime_diagnostics()

    app._runtime_unclean_exit_detected = True
    app._on_process_exit()

    state = app._read_runtime_state()
    assert state is not None
    assert state["clean_shutdown"] is False
    assert state["shutdown_reason"] == "unhandled_exception"
    assert state["last_stage"] == "process_exit_unclean"
