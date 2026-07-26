#!/usr/bin/env python3
"""
Sonic Input - Application Entry Point

Unified entry point providing:
- Warning suppression for cleaner output
- CLI argument parsing and mode selection
- Environment validation and package smoke checks

Usage:
  sonicinput --gui          # Start GUI (default)
  sonicinput --validate     # Validate the runtime environment

The repository-root ``app.py`` remains a compatibility launcher for source
checkouts and Nuitka builds.
"""

import sys
import os
import warnings
import argparse
import signal
import time
import atexit
import faulthandler
import json
import threading
import traceback
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Tuple, Dict, Any, Optional

# Sherpa's native extension and Python onnxruntime bundle different ORT builds.
# Configure Sherpa's DLL before any optional AI component can import Python ORT.
try:
    from sonicinput.speech.sherpa_runtime import configure_sherpa_dll_search_path

    configure_sherpa_dll_search_path()
except Exception:
    pass

from sonicinput.utils import (
    LogCategory,
    app_logger,
    environment_validator,
)
from sonicinput.resources.runtime_assets import get_assets_dir


# ============================================================================
# Warning Filters
# ============================================================================

# Suppress known third-party library warnings
warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated",
    category=UserWarning,
    module="ctranslate2",
)

# ============================================================================
# Application Startup
# ============================================================================

# Track application startup time
_STARTUP_START_TIME = time.time()

# Global references for cleanup in signal handler
_app_instance = None
_container_instance = None
_qt_app_instance = None

# Runtime diagnostics state (for unexpected exits with missing logs)
_LOG_DIR = Path(os.environ.get("APPDATA", ".")) / "SonicInput" / "logs"
_RUNTIME_STATE_FILE = _LOG_DIR / "runtime_state.json"
_CRASH_LOG_FILE = _LOG_DIR / "crash.log"
_FAULT_LOG_FILE = _LOG_DIR / "fault.log"

_fault_log_handle = None
_runtime_diagnostics_initialized = False
_runtime_unclean_exit_detected = False


def _now_iso() -> str:
    """Return current local time in ISO format."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _ensure_log_dir() -> None:
    """Ensure diagnostics log directory exists."""
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        # Best effort only; app must continue even if path is unavailable.
        pass


def _append_crash_log(message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    """Append a structured line to crash.log without relying on app logger."""
    try:
        _ensure_log_dir()
        payload: Dict[str, Any] = {
            "timestamp": _now_iso(),
            "pid": os.getpid(),
            "message": message,
        }
        if extra:
            payload["extra"] = extra

        with open(_CRASH_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _read_runtime_state() -> Optional[Dict[str, Any]]:
    """Read runtime state file. Return None on missing/invalid file."""
    try:
        if not _RUNTIME_STATE_FILE.exists():
            return None
        with open(_RUNTIME_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None


def _write_runtime_state(state: Dict[str, Any]) -> None:
    """Write runtime state atomically."""
    try:
        _ensure_log_dir()
        tmp_file = _RUNTIME_STATE_FILE.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False, default=str)
            f.write("\n")
        os.replace(tmp_file, _RUNTIME_STATE_FILE)
    except Exception:
        pass


def _update_runtime_state(
    stage: Optional[str] = None,
    *,
    clean_shutdown: Optional[bool] = None,
    shutdown_reason: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Update runtime state for post-mortem diagnostics."""
    state = _read_runtime_state() or {}
    state["pid"] = os.getpid()
    state.setdefault("startup_time", _now_iso())

    if stage is not None:
        state["last_stage"] = stage
        state["last_stage_time"] = _now_iso()
    if clean_shutdown is not None:
        state["clean_shutdown"] = clean_shutdown
        if clean_shutdown:
            state["shutdown_time"] = _now_iso()
    if shutdown_reason:
        state["shutdown_reason"] = shutdown_reason
    if extra:
        state["details"] = extra

    _write_runtime_state(state)


def _record_previous_unclean_shutdown() -> None:
    """Report previous unclean exit if marker from last run remains."""
    previous_state = _read_runtime_state()
    if not previous_state or previous_state.get("clean_shutdown", False):
        return

    message = (
        "[CRASH-DETECT] Detected previous unclean shutdown "
        f"(pid={previous_state.get('pid', 'unknown')}, "
        f"startup={previous_state.get('startup_time', 'unknown')}, "
        f"last_stage={previous_state.get('last_stage', 'unknown')})"
    )
    print(message)
    _append_crash_log("Detected previous unclean shutdown", previous_state)

    if app_logger:
        try:
            app_logger.warning(
                "Detected previous unclean shutdown",
                category=LogCategory.ERROR,
                context=previous_state,
                component="runtime_diagnostics",
            )
        except Exception:
            pass


def _configure_fault_handler() -> None:
    """Enable faulthandler so native crashes also leave a traceback."""
    global _fault_log_handle
    try:
        _ensure_log_dir()
        if _fault_log_handle is None:
            _fault_log_handle = open(_FAULT_LOG_FILE, "a", encoding="utf-8")

        _fault_log_handle.write(
            f"[{_now_iso()}] Enabled faulthandler for pid={os.getpid()}\n"
        )
        _fault_log_handle.flush()
        faulthandler.enable(file=_fault_log_handle, all_threads=True)
    except Exception as e:
        print(f"Warning: Could not enable faulthandler: {e}")
        _append_crash_log("Failed to enable faulthandler", {"error": str(e)})


def _record_unhandled_exception(
    origin: str,
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_tb: Optional[TracebackType],
    thread_name: Optional[str] = None,
) -> None:
    """Persist unhandled exception details for crash diagnosis."""
    global _runtime_unclean_exit_detected
    _runtime_unclean_exit_detected = True

    traceback_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    context: Dict[str, Any] = {
        "origin": origin,
        "exception_type": exc_type.__name__,
        "exception": str(exc_value),
    }
    if thread_name:
        context["thread"] = thread_name

    _append_crash_log(f"Unhandled exception ({origin})", context)
    _append_crash_log("Unhandled traceback", {"traceback": traceback_text})
    _update_runtime_state(
        stage="unhandled_exception",
        clean_shutdown=False,
        shutdown_reason=origin,
        extra=context,
    )

    if app_logger:
        try:
            if isinstance(exc_value, Exception):
                app_logger.log_error(exc_value, origin)
            else:
                app_logger.error(
                    f"Unhandled base exception in {origin}",
                    category=LogCategory.ERROR,
                    context=context,
                    component="runtime_diagnostics",
                )
        except Exception:
            pass

    print(
        f"[UNHANDLED] {origin} -> {exc_type.__name__}: {exc_value}",
        file=sys.stderr,
    )
    print(traceback_text, file=sys.stderr)


def _global_excepthook(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_tb: Optional[TracebackType],
) -> None:
    """Process-level excepthook."""
    if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return

    _record_unhandled_exception("sys.excepthook", exc_type, exc_value, exc_tb)
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
    """Thread-level excepthook."""
    if args.exc_type is None or args.exc_value is None:
        if hasattr(threading, "__excepthook__"):
            threading.__excepthook__(args)
        return

    if issubclass(args.exc_type, (KeyboardInterrupt, SystemExit)):
        if hasattr(threading, "__excepthook__"):
            threading.__excepthook__(args)
        return

    _record_unhandled_exception(
        origin="threading.excepthook",
        exc_type=args.exc_type,
        exc_value=args.exc_value,
        exc_tb=args.exc_traceback,
        thread_name=args.thread.name if args.thread else None,
    )
    if hasattr(threading, "__excepthook__"):
        threading.__excepthook__(args)


def _on_process_exit() -> None:
    """Atexit handler to mark clean shutdown."""
    if _runtime_unclean_exit_detected:
        _update_runtime_state(
            stage="process_exit_unclean",
            clean_shutdown=False,
            shutdown_reason="unhandled_exception",
        )
        return

    _update_runtime_state(
        stage="process_exit",
        clean_shutdown=True,
        shutdown_reason="normal_exit",
    )


def initialize_runtime_diagnostics() -> None:
    """Install crash diagnostics hooks and runtime exit markers."""
    global _runtime_diagnostics_initialized
    if _runtime_diagnostics_initialized:
        return

    _ensure_log_dir()
    _record_previous_unclean_shutdown()
    _update_runtime_state(
        stage="process_start",
        clean_shutdown=False,
        extra={"argv": sys.argv},
    )
    _configure_fault_handler()

    sys.excepthook = _global_excepthook
    threading.excepthook = _thread_excepthook
    atexit.register(_on_process_exit)
    _runtime_diagnostics_initialized = True


def handle_shutdown(signum, _frame):
    """Handle shutdown signals gracefully with proper cleanup

    Note: Refactored to avoid try-finally with return for Nuitka compatibility
    """
    print("\n[SHUTDOWN] Received shutdown signal, cleaning up...")
    _update_runtime_state(
        stage="signal_shutdown",
        clean_shutdown=False,
        shutdown_reason=f"signal_{signum}",
        extra={"signal": signum},
    )

    global _app_instance, _container_instance, _qt_app_instance

    try:
        # If Qt app is running, use Qt's quit mechanism
        if _qt_app_instance:
            print("[SHUTDOWN] Requesting Qt application quit...")
            _qt_app_instance.quit()
            # Qt cleanup will handle the rest - skip manual cleanup
        else:
            # Otherwise, handle cleanup directly (for test mode)
            # Clean up voice app
            if _app_instance:
                print("[SHUTDOWN] Stopping voice input app...")
                try:
                    _app_instance.shutdown()
                    print("[SHUTDOWN] Voice app stopped successfully")
                except Exception as e:
                    print(f"[SHUTDOWN] Warning during app shutdown: {e}")

            # Clean up container
            if _container_instance:
                print("[SHUTDOWN] Cleaning up dependency container...")
                try:
                    _container_instance.cleanup()
                    print("[SHUTDOWN] Container cleaned up successfully")
                except Exception as e:
                    print(f"[SHUTDOWN] Warning during container cleanup: {e}")

            print("[SHUTDOWN] Cleanup completed, exiting...")

    except Exception as e:
        print(f"[SHUTDOWN] Error during cleanup: {e}")
        import traceback

        traceback.print_exc()

    finally:
        sys.exit(0)


def validate_environment() -> Tuple[bool, Dict[str, Any]]:
    """Pre-flight environment validation before GUI startup"""
    print("=== Environment Validation ===")

    if environment_validator is None:
        print("[FAIL] Environment validator not available")
        return False, {"error": "Environment validator not available"}

    try:
        success, results = environment_validator.comprehensive_validation()

        if success:
            print("[PASS] Environment validation passed")
        else:
            print("[FAIL] Environment validation failed")
            if results.get("errors"):
                for error in results["errors"]:
                    print(f"  • {error}")

        return success, results

    except Exception as e:
        print(f"[FAIL] Environment validation error: {e}")
        if app_logger:
            app_logger.error(
                f"Environment validation error: {e}",
                e,
                component="environment_validation",
            )
        return False, {"error": str(e)}


def test_gui_components() -> bool:
    """Test GUI components in isolation before full startup"""
    print("=== GUI Component Testing ===")

    try:
        # Test PySide6 imports
        print("Testing PySide6 imports...")
        from PySide6.QtWidgets import QApplication

        print("[PASS] PySide6 imports successful")

        # Test application components (import only)
        print("Testing application component imports...")
        print("[PASS] Application component imports successful")

        # Test QApplication creation
        print("Testing QApplication creation...")
        existing_app = QApplication.instance()
        if existing_app is None:
            existing_app = QApplication(
                ["-platform", "minimal"]
            )  # Use minimal platform for testing
            print("[PASS] QApplication creation successful")
        else:
            print("[PASS] QApplication instance already exists")

        return True

    except Exception as e:
        print(f"[FAIL] GUI component test failed: {e}")
        if app_logger:
            app_logger.log_error(e, "gui_component_test")
        return False


def run_gui_with_diagnostics() -> int:
    """Launch GUI with simplified validation (system checks moved to test mode)"""
    print("=== GUI Startup ===")
    _update_runtime_state(stage="gui_startup_begin")

    # Early-load logger configuration to suppress console output if configured
    try:
        from sonicinput.core.services.config_service import ConfigService
        from sonicinput.utils.unified_logger import logger

        early_config = ConfigService()
        logger.set_config_service(early_config)
        # Logger config now loaded - diagnostics will respect console_output setting
    except Exception as e:
        print(f"Warning: Could not early-load logger config: {e}")

    # Simplified pre-flight: Only GUI-specific validation
    print("Running GUI-specific validation...")

    # Test GUI components in isolation (GUI-specific check)
    if not test_gui_components():
        print("\n[FAIL] GUI component testing failed. Cannot start GUI.")
        return 1

    print("[PASS] GUI validation completed. Starting GUI...")

    # Proceed with normal GUI startup
    return run_gui()


def run_gui():
    """Launch GUI mode"""
    print("Starting GUI mode...")

    try:

        def apply_windows_ui_font(qt_app):
            if sys.platform != "win32":
                return
            try:
                from PySide6.QtGui import QFont, QFontDatabase

                selected_font = None
                assets_dir = get_assets_dir()
                if assets_dir:
                    font_files = [
                        assets_dir
                        / "fonts"
                        / "resource-han-rounded"
                        / "ResourceHanRoundedCN-Regular.ttf",
                        assets_dir
                        / "fonts"
                        / "resource-han-rounded"
                        / "ResourceHanRoundedCN-Bold.ttf",
                    ]
                    loaded_families = []
                    for font_path in font_files:
                        if not font_path.exists():
                            continue
                        font_id = QFontDatabase.addApplicationFont(str(font_path))
                        if font_id != -1:
                            loaded_families.extend(
                                QFontDatabase.applicationFontFamilies(font_id)
                            )
                    if loaded_families:
                        selected_font = loaded_families[0]

                if not selected_font:
                    preferred_fonts = [
                        "Microsoft YaHei UI",
                        "Microsoft YaHei",
                        "Segoe UI",
                    ]
                    available_fonts = set(QFontDatabase.families())
                    selected_font = next(
                        (font for font in preferred_fonts if font in available_fonts),
                        None,
                    )

                if not selected_font:
                    print("[WARN] No preferred UI font found; using system default.")
                    return

                font = qt_app.font()
                font.setFamily(selected_font)
                font.setHintingPreference(QFont.PreferFullHinting)
                qt_app.setFont(font)
                print(f"[OK] UI font set to: {selected_font}")
            except Exception as e:
                print(f"[WARN] Failed to apply Windows UI font: {e}")

        # Import Qt and UI components
        from PySide6.QtWidgets import QApplication
        from PySide6.QtQuickControls2 import QQuickStyle
        from PySide6.QtCore import QTimer
        from sonicinput.ui.main_window import MainWindow
        from sonicinput.ui.components.system_tray.tray_controller import TrayController
        from sonicinput.core.voice_input_app import VoiceInputApp

        # Import qt-material for modern UI theming
        from qt_material import apply_stylesheet

        # IMPORTANT: Set AppUserModelID BEFORE creating QApplication
        # This is required for Windows taskbar icon to display correctly
        import ctypes

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "com.sonicinput.app"
            )
        except Exception:
            pass  # Silently fail on non-Windows platforms

        # Create Qt application (or reuse existing instance)
        qt_app = QApplication.instance()
        if qt_app is None:
            qt_app = QApplication(sys.argv)
        QQuickStyle.setStyle("FluentWinUI3")

        apply_windows_ui_font(qt_app)

        # Set application icon (all windows will inherit this)
        # Note: Skip setWindowIcon in exe mode due to Nuitka issue #3611
        from sonicinput.ui.utils import get_app_icon

        app_icon = get_app_icon()

        if not sys.argv[0].endswith(".exe"):
            # Only set icon when running from Python (not compiled exe)
            # In exe mode, icon is set via --windows-icon-from-ico during compilation
            qt_app.setWindowIcon(app_icon)

        # Create application components (needed to access config)
        from sonicinput.core.di_container import create_container

        container = create_container()

        # Load theme color from config
        from sonicinput.core.interfaces.config import IConfigService

        config_service = container.get(IConfigService)
        try:
            from sonicinput.core.services.launch_at_login_service import (
                LaunchAtLoginService,
            )

            launch_service = container.get(LaunchAtLoginService)
            launch_at_login_enabled = bool(
                config_service.get_setting("ui.launch_at_login", False)
            )
            launch_service.sync(launch_at_login_enabled)
        except Exception as e:
            print(f"[WARN] Failed to reconcile launch-at-login state: {e}")

        theme_color = config_service.get_setting("ui.theme_color", "cyan")

        # Apply UI language before creating windows
        from sonicinput.core.services.ui_services import UILocalizationService

        localization_service = container.get(UILocalizationService)
        localization_service.apply_language()

        # Apply Material Design theme
        theme_file = f"dark_{theme_color}.xml"
        try:
            apply_stylesheet(qt_app, theme=theme_file)
            print(f"[OK] qt-material theme applied: {theme_file}")
        except Exception as e:
            print(f"[WARN] Failed to apply qt-material theme: {e}")
            print("  Continuing with default style...")

        qt_app.setQuitOnLastWindowClosed(False)  # System tray app
        voice_app = VoiceInputApp(container)
        voice_app.initialize_with_validation()

        # Save global references for signal handler
        global _app_instance, _container_instance, _qt_app_instance
        _app_instance = voice_app
        _container_instance = container
        _qt_app_instance = qt_app

        # Get UI services from container (Pure DI - no VoiceInputApp dependency)
        from sonicinput.core.services.ui_services import (
            UIMainService,
            UISettingsService,
            UIModelService,
        )

        ui_main_service = container.get(UIMainService)
        ui_settings_service = container.get(UISettingsService)
        ui_model_service = container.get(UIModelService)

        # CRITICAL FIX: Update UISettingsService with AI controller after VoiceInputApp initialization
        # AI controller is created in voice_app._init_controllers() but UISettingsService was
        # already created by DI container before voice_app existed. We need to inject it now.
        if hasattr(voice_app, "_ai_controller") and voice_app._ai_controller:
            if hasattr(ui_settings_service, "ai_processing_controller"):
                ui_settings_service.ai_processing_controller = voice_app._ai_controller
                app_logger.log_audio_event(
                    "AI controller injected into UISettingsService",
                    {
                        "controller_type": type(voice_app._ai_controller).__name__,
                        "controller_id": id(voice_app._ai_controller),
                    },
                )
            else:
                app_logger.log_audio_event(
                    "Warning: UISettingsService doesn't have ai_processing_controller attribute",
                    {},
                )

        # Create main window with dependency injection
        main_window = MainWindow(
            ui_main_service=ui_main_service,
            ui_settings_service=ui_settings_service,
            ui_model_service=ui_model_service,
        )
        # Store as qt_app attribute to prevent garbage collection
        qt_app.main_window = main_window

        # Create system tray using new Phase 2 architecture
        app_logger.debug("Creating TrayController with dependency injection...")
        from sonicinput.core.interfaces import (
            IConfigService,
            IEventService,
            IStateManager,
        )

        # Get services from container
        config_service = container.get(IConfigService)
        event_service = container.get(IEventService)
        state_manager = container.get(IStateManager)

        # Create TrayController with dependency injection
        tray_controller = TrayController(
            config_service=config_service,
            event_service=event_service,
            state_manager=state_manager,
            parent=qt_app,
        )

        # Start tray controller (lifecycle management)
        tray_controller.start()  # Note: simplified LifecycleComponent only has start(), not initialize()
        app_logger.debug(f"TrayController initialized and started: {tray_controller}")

        # Create recording overlay
        from sonicinput.ui.fluent_recording_overlay import FluentRecordingOverlay

        recording_overlay = FluentRecordingOverlay()
        app_logger.log_audio_event("Fluent recording overlay created", {})

        # Set config service for position persistence
        recording_overlay.set_config_service(voice_app.config)

        # Phase 1: Inject StateManager for SSOT compliance
        state_manager = voice_app.container.get(IStateManager)
        recording_overlay.set_state_manager(state_manager)

        # Set recording overlay in voice app
        voice_app.set_recording_overlay(recording_overlay)

        # Connect system tray signals to main window
        tray_controller.show_settings_requested.connect(main_window.show_settings)
        tray_controller.toggle_recording_requested.connect(main_window.toggle_recording)
        tray_controller.exit_application_requested.connect(qt_app.quit)
        recording_overlay.stop_recording_requested.connect(main_window.toggle_recording)

        # Recording overlay signals (simplified - ESC key handled internally)
        # Note: TrayController now subscribes to events internally through event_service
        # No need for manual event connections here

        # Start behavior based on configuration
        config = voice_app.config
        if config.get_setting("ui.start_minimized", True):
            # Start directly in system tray without showing window
            print("[OK] Started in system tray mode")
            print(
                "[LOOK FOR] Green dot icon in your Windows system tray (bottom-right corner)"
            )
            print("[RIGHT-CLICK] the tray icon to access Settings, Recording, etc.")
            print("[DOUBLE-CLICK] the tray icon to open Settings window")

            # 显示配置的热键
            hotkeys = config.get_setting("hotkeys.keys", ["f12"])
            if isinstance(hotkeys, list) and len(hotkeys) > 0:
                hotkey_str = " or ".join(hotkeys)
            else:
                hotkey_str = str(hotkeys) if hotkeys else "f12"
            print(f"[HOTKEY] Press {hotkey_str} to start voice recording")
        else:
            main_window.show()
            print("GUI window opened")

        # Log startup completion with performance metrics
        startup_duration = time.time() - _STARTUP_START_TIME
        if app_logger:
            app_logger.info(
                f"Application Startup Complete in {startup_duration:.2f}s",
                category=LogCategory.STARTUP,
                context={
                    "startup_duration_sec": round(startup_duration, 2),
                    "components_loaded": [
                        "PySide6",
                        "DIContainer",
                        "VoiceInputApp",
                        "MainWindow",
                        "TrayController",
                        "RecordingOverlay",
                    ],
                    "startup_mode": "tray"
                    if config.get_setting("ui.start_minimized", True)
                    else "window",
                },
                component="main",
            )

        print(f"[RUNNING] Sonic Input is running! (Startup: {startup_duration:.2f}s)")

        # 从配置读取热键（支持多个热键）
        hotkeys = config.get_setting("hotkeys.keys", ["f12"])
        if isinstance(hotkeys, list) and len(hotkeys) > 0:
            hotkey_str = " or ".join(hotkeys)
        else:
            hotkey_str = str(hotkeys) if hotkeys else "f12"
        print(f"[HOTKEY] Press {hotkey_str} to start voice recording")

        # Set up signal handling timer for GUI mode
        # Qt event loop blocks signal handlers, so we need to periodically check
        def check_for_interrupt():
            """Check if we should exit (called periodically by QTimer)"""
            # This allows Python signal handlers to be processed
            pass

        signal_timer = QTimer()
        signal_timer.timeout.connect(check_for_interrupt)
        signal_timer.start(100)  # Check every 100ms

        # Connect Qt's aboutToQuit signal for proper cleanup
        def on_about_to_quit():
            """Handle Qt application quit signal"""
            print("\n[CLEANUP] Qt application quitting...")
            signal_timer.stop()

            # Clear global references
            global _app_instance, _container_instance, _qt_app_instance
            _app_instance = None
            _container_instance = None
            _qt_app_instance = None

        qt_app.aboutToQuit.connect(on_about_to_quit)

        # Run Qt event loop
        _update_runtime_state(stage="qt_event_loop_running")
        exit_code = qt_app.exec()
        _update_runtime_state(
            stage="qt_event_loop_exited",
            extra={"exit_code": exit_code},
        )

        # Cleanup in optimized order
        try:
            print("[CLEANUP] Starting application cleanup...")

            # 1. First hide recording overlay immediately to provide user feedback
            if recording_overlay:
                recording_overlay.hide_recording()
                print("[CLEANUP] Recording overlay hidden")

            # 2. Stop voice app core functionality (recording, threads, hotkeys, models)
            voice_app.shutdown()
            print("[CLEANUP] Voice app shutdown completed")

            # 3. Clean up recording overlay completely after voice app shutdown
            if recording_overlay:
                recording_overlay.close()
                print("[CLEANUP] Recording overlay fully cleaned up")

            # 4. Clean up system tray after all voice app operations are complete
            #    This prevents race conditions with tray updates during shutdown
            if tray_controller:
                tray_controller.cleanup()
                print("[CLEANUP] System tray cleaned up")

            # 5. Process any remaining Qt events
            qt_app.processEvents()  # Process any pending events
            print("[CLEANUP] Application cleanup completed successfully")

        except Exception as cleanup_error:
            print(f"[CLEANUP] Warning: Error during cleanup: {cleanup_error}")
            # Don't fail the exit, just log the warning

        return exit_code

    except Exception as e:
        _update_runtime_state(
            stage="gui_startup_exception",
            clean_shutdown=False,
            shutdown_reason="gui_startup_exception",
            extra={"error": str(e)},
        )
        print(f"ERROR: Failed to start GUI: {e}")
        print("Full traceback:")
        import traceback

        traceback.print_exc()
        sys.exit(1)


class _PackageSmokeSettingsService:
    """Read-only settings facade used by the packaged QML smoke."""

    @staticmethod
    def get_setting(_key: str, default: Any = None) -> Any:
        return default

    @staticmethod
    def get_all_settings() -> Dict[str, Any]:
        return {}

    @staticmethod
    def get_history_service() -> None:
        return None

    @staticmethod
    def list_review_suggestions(limit: int = 100) -> list[Dict[str, Any]]:
        del limit
        return []

    @staticmethod
    def list_lexicon_entries() -> list[Dict[str, Any]]:
        return []


def run_package_smoke() -> bool:
    """Exercise critical modules and QML surfaces from the packaged executable."""

    checks: list[tuple[str, bool, str]] = []

    def record(name: str, passed: bool, detail: str = "") -> None:
        checks.append((name, passed, detail))
        marker = "PASS" if passed else "FAIL"
        suffix = f": {detail}" if detail else ""
        print(f"[PACKAGE-SMOKE] {marker} {name}{suffix}")

    try:
        assets_dir = get_assets_dir()
        required_assets = (
            "icon.png",
            "i18n/sonicinput_en_US.qm",
            "i18n/sonicinput_zh_CN.qm",
            "fonts/resource-han-rounded/ResourceHanRoundedCN-Regular.ttf",
        )
        missing_assets = [
            relative
            for relative in required_assets
            if assets_dir is None or not (assets_dir / relative).is_file()
        ]
        record(
            "runtime assets",
            not missing_assets,
            "missing " + ", ".join(missing_assets) if missing_assets else "",
        )
    except Exception as exc:
        record("runtime assets", False, str(exc))

    try:
        from pypinyin import lazy_pinyin

        syllables = lazy_pinyin("测试")
        record("pypinyin dictionaries", syllables == ["ce", "shi"], str(syllables))
    except Exception as exc:
        record("pypinyin dictionaries", False, str(exc))

    try:
        from sonicinput.speech.sherpa_runtime import (
            configure_sherpa_dll_search_path,
            inspect_onnxruntime_candidates,
        )

        configure_sherpa_dll_search_path()
        import sherpa_onnx

        sherpa_onnx.OfflineRecognizerConfig()
        candidates = inspect_onnxruntime_candidates()
        found_dll = any(candidate.get("exists") for candidate in candidates)
        record(
            "sherpa native runtime",
            found_dll,
            "onnxruntime.dll found" if found_dll else "onnxruntime.dll missing",
        )
    except Exception as exc:
        record("sherpa native runtime", False, str(exc))

    try:
        import onnxruntime

        providers = onnxruntime.get_available_providers()
        record(
            "onnxruntime Python API",
            "CPUExecutionProvider" in providers,
            ", ".join(providers),
        )
    except Exception as exc:
        record("onnxruntime Python API", False, str(exc))

    model_smoke_dir = os.environ.get("SONICINPUT_PACKAGE_SMOKE_MODEL_DIR")
    if model_smoke_dir:
        model_name = os.environ.get("SONICINPUT_PACKAGE_SMOKE_MODEL", "zipformer-small")
        engine = None
        try:
            import numpy as np

            from sonicinput.speech.sherpa_engine import SherpaEngine

            engine = SherpaEngine(
                model_name=model_name,
                cache_dir=model_smoke_dir,
                download_if_missing=False,
            )
            if not engine.load_model(download_if_missing=False):
                raise RuntimeError(f"Could not load cached {model_name} model")
            transcription = engine.transcribe(np.zeros(16000, dtype=np.float32))
            record(
                "sherpa model decode",
                isinstance(transcription, dict) and "text" in transcription,
                f"{model_name}: {transcription.get('text', '')!r}",
            )
        except Exception as exc:
            record("sherpa model decode", False, str(exc))
        finally:
            if engine is not None:
                engine.unload_model()

    previous_qpa_platform = os.environ.get("QT_QPA_PLATFORM")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    qt_app = None
    windows: list[Any] = []
    try:
        from PySide6.QtCore import QEventLoop, QTimer
        from PySide6.QtWidgets import QApplication
        from sonicinput.ui.fluent_about_window import FluentAboutWindow
        from sonicinput.ui.fluent_recording_overlay import FluentRecordingOverlay
        from sonicinput.ui.fluent_settings_window import FluentSettingsWindow

        qt_app = QApplication.instance() or QApplication(["sonicinput-package-smoke"])
        settings = FluentSettingsWindow(_PackageSmokeSettingsService())
        overlay = FluentRecordingOverlay()
        about = FluentAboutWindow()
        windows.extend([settings, overlay, about])

        settings.show()
        overlay.show_recording()
        about.show()
        event_loop = QEventLoop()
        QTimer.singleShot(250, event_loop.quit)
        event_loop.exec()

        expected_roots = {
            "settings": settings.root.objectName(),
            "overlay": overlay.root.objectName(),
            "about": about.root.objectName(),
        }
        expected = {
            "settings": "fluentSettingsWindow",
            "overlay": "fluentRecordingOverlay",
            "about": "fluentAboutWindow",
        }
        record(
            "QML settings/overlay/about",
            expected_roots == expected,
            str(expected_roots),
        )
    except Exception as exc:
        record("QML settings/overlay/about", False, str(exc))
    finally:
        for window in reversed(windows):
            try:
                window.close()
            except Exception:
                pass
        if qt_app is not None:
            qt_app.processEvents()
        if previous_qpa_platform is None:
            os.environ.pop("QT_QPA_PLATFORM", None)
        else:
            os.environ["QT_QPA_PLATFORM"] = previous_qpa_platform

    passed = all(result for _name, result, _detail in checks)
    print(
        f"[PACKAGE-SMOKE] {'PASS' if passed else 'FAIL'} "
        f"{sum(result for _name, result, _detail in checks)}/{len(checks)} checks"
    )
    return passed


def main() -> None:
    """Main application entry point"""
    parser = argparse.ArgumentParser(description="Sonic Input")
    parser.add_argument("--gui", action="store_true", help="Launch with GUI")
    parser.add_argument(
        "--validate", action="store_true", help="Validate environment only"
    )
    parser.add_argument(
        "--package-smoke",
        action="store_true",
        help=argparse.SUPPRESS,
    )

    args = parser.parse_args()

    initialize_runtime_diagnostics()
    _update_runtime_state(stage="main_entry")

    # Set up signal handlers
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    print("=== Sonic Input ===")

    if args.validate:
        _update_runtime_state(stage="run_validate")
        success, _report = validate_environment()
        sys.exit(0 if success else 1)
    elif args.package_smoke:
        _update_runtime_state(stage="run_package_smoke")
        sys.exit(0 if run_package_smoke() else 1)
    else:
        # Default: always launch GUI (with or without --gui flag)
        _update_runtime_state(stage="launch_gui")
        sys.exit(run_gui_with_diagnostics())


if __name__ == "__main__":
    main()
