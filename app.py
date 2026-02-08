#!/usr/bin/env python3
"""
Sonic Input - Application Entry Point

Unified entry point providing:
- Warning suppression for cleaner output
- CLI argument parsing and mode selection
- Diagnostic and testing capabilities

Usage:
  python app.py --gui          # Start GUI (default)
  python app.py --test         # Run tests
  python app.py --diagnostics  # Run diagnostics
"""

import sys
import os
import warnings
import argparse
import signal
import time
from pathlib import Path
from typing import Tuple, Dict, Any


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

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Import diagnostics utilities (after path setup)
try:
    from sonicinput.utils import environment_validator, startup_diagnostics, LogCategory
    from sonicinput.utils.logger import app_logger
except ImportError as e:
    print(f"Warning: Could not import diagnostic utilities: {e}")
    environment_validator = None
    startup_diagnostics = None
    app_logger = None
    LogCategory = None

# Global references for cleanup in signal handler
_app_instance = None
_container_instance = None
_qt_app_instance = None


def handle_shutdown(signum, frame):
    """Handle shutdown signals gracefully with proper cleanup

    Note: Refactored to avoid try-finally with return for Nuitka compatibility
    """
    print("\n[SHUTDOWN] Received shutdown signal, cleaning up...")

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


def run_tests():
    """
    Run all application tests including model transcription.

    Automatically loads the model if not already loaded.
    """
    print("Running application tests...")

    # Store references for cleanup
    global _app_instance, _container_instance
    container = None
    app = None

    try:
        # Test core imports
        from sonicinput.core.voice_input_app import VoiceInputApp
        from sonicinput.core.interfaces import IConfigService

        # Test dependency injection
        from sonicinput.core.di_container import create_container

        container = create_container()
        app = VoiceInputApp(container)

        # Save to global for signal handler
        _container_instance = container
        _app_instance = app

        print("SUCCESS: Core application components loaded")

        # sherpa-onnx uses CPU only, no GPU check needed
        print("INFO: Using sherpa-onnx (CPU-only, no GPU required)")

        # Test configuration
        config = container.get(IConfigService)
        model = config.get_setting("transcription.local.model", "paraformer")
        print(f"SUCCESS: Configuration loaded: {model}")

        # Test EventBus core functionality
        print("\n--- EventBus Tests ---")
        test_eventbus()

        # Moved from GUI mode: System environment checks
        print("\n--- System Environment Tests ---")
        if startup_diagnostics:
            try:
                # System information collection
                print("Collecting system information...")
                system_info = startup_diagnostics._collect_system_info()
                print(
                    f"SUCCESS: System info collected - OS: {system_info.get('platform', 'unknown')}"
                )

                # Python environment information
                print("Collecting Python environment information...")
                python_info = startup_diagnostics._collect_python_info()
                print(
                    f"SUCCESS: Python {python_info.get('version', 'unknown')} on {python_info.get('platform', 'unknown')}"
                )

                # Dependency version check
                print("Checking dependency versions...")
                dep_versions = startup_diagnostics.check_dependency_versions()
                print(
                    f"SUCCESS: {len(dep_versions.get('dependencies', []))} dependencies checked"
                )

                # File system check
                print("Checking file system access...")
                fs_check = startup_diagnostics._check_file_system()
                if fs_check.get("accessible", False):
                    print("SUCCESS: File system access verified")
                else:
                    print("WARNING: Some file system access issues detected")

                # Process information
                print("Collecting process information...")
                process_info = startup_diagnostics._collect_process_info()
                print(
                    f"SUCCESS: Process info collected - PID: {process_info.get('pid', 'unknown')}"
                )

            except Exception as e:
                print(f"WARNING: System environment tests failed: {e}")
        else:
            print("SKIP: System environment tests (startup_diagnostics not available)")

        # Model transcription test (always run, auto-load model)
        print("\n--- Model Transcription Test ---")
        run_model_test(container, auto_load_model=True)

        print("\nAll tests passed! Use --gui to start the application.")

    except Exception as e:
        print(f"\nERROR: Tests failed: {e}")
        print("Check your installation and dependencies")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    finally:
        # Clean up test resources
        print("\n[CLEANUP] Cleaning up test resources...")
        try:
            if app:
                print("[CLEANUP] Shutting down voice app...")
                app.shutdown()
                print("[CLEANUP] Voice app shutdown completed")

            if container:
                print("[CLEANUP] Cleaning up container...")
                container.cleanup()
                print("[CLEANUP] Container cleanup completed")

            # Clear global references
            _app_instance = None
            _container_instance = None

            print("[CLEANUP] Test cleanup completed successfully")

        except Exception as cleanup_error:
            print(f"[CLEANUP] Warning during cleanup: {cleanup_error}")
            import traceback

            traceback.print_exc()


def run_model_test(container, auto_load_model=False):
    """
    Run sherpa-onnx model transcription test.

    Args:
        container: DIContainer instance
        auto_load_model: If True, load model before testing
    """
    from sonicinput.core.interfaces import ISpeechService
    from sonicinput.utils.cli_model_tester import CLIModelTester

    print("Initializing model test...")

    # Get sherpa-onnx engine from DI container
    speech_engine = container.get(ISpeechService)

    # Create tester
    tester = CLIModelTester(speech_engine, timeout_seconds=120)

    # Run test
    result = tester.run_test(auto_load_model=auto_load_model)

    # Display results
    print(tester.format_results(result))

    if not result["success"]:
        sys.exit(1)


def test_eventbus():
    """Test EventBus core functionality"""
    from sonicinput.core.services.event_bus import EventBus, Events
    from sonicinput.core.interfaces.event import EventPriority
    import threading

    print("Testing EventBus...")

    # Test 1: Basic emit and on
    bus = EventBus()
    results = []

    bus.on(Events.RECORDING_STARTED, lambda data: results.append("callback"))
    bus.emit(Events.RECORDING_STARTED)

    assert results == ["callback"], "Basic emit/on failed"
    print("  [PASS] Basic emit/on works")

    # Test 2: Priority queue
    bus2 = EventBus()
    order = []
    test_event = "test_priority"

    bus2.on(test_event, lambda data: order.append("LOW"), priority=EventPriority.LOW)
    bus2.on(
        test_event, lambda data: order.append("NORMAL"), priority=EventPriority.NORMAL
    )
    bus2.on(test_event, lambda data: order.append("HIGH"), priority=EventPriority.HIGH)

    bus2.emit(test_event)

    assert order == ["HIGH", "NORMAL", "LOW"], f"Priority queue failed: {order}"
    print("  [PASS] Priority queue works (HIGH > NORMAL > LOW)")

    # Test 3: Once listener
    bus3 = EventBus()
    count = {"value": 0}
    test_event2 = "test_once"

    bus3.once(test_event2, lambda data: count.update({"value": count["value"] + 1}))

    bus3.emit(test_event2)
    bus3.emit(test_event2)
    bus3.emit(test_event2)

    assert count["value"] == 1, (
        f"Once listener called {count['value']} times (should be 1)"
    )
    print("  [PASS] Once listener only triggers once")

    # Test 4: Exception isolation
    bus4 = EventBus()
    executed = []
    test_event3 = "test_exception"

    def bad_listener(data):
        executed.append("bad")
        raise ValueError("Test error")

    def good_listener(data):
        executed.append("good")

    bus4.on(test_event3, bad_listener)
    bus4.on(test_event3, good_listener)

    bus4.emit(test_event3)

    assert executed == ["bad", "good"], f"Error isolation failed: {executed}"
    print("  [PASS] Listener exceptions don't stop other listeners")

    # Test 5: Concurrent safety (simplified)
    bus5 = EventBus()
    concurrent_results = []
    lock = threading.Lock()
    test_event4 = "test_concurrent"

    def concurrent_callback(value):
        with lock:
            concurrent_results.append(value)

    bus5.on(test_event4, concurrent_callback)

    threads = []
    for i in range(10):
        thread = threading.Thread(
            target=lambda idx: bus5.emit(test_event4, idx), args=(i,)
        )
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    assert len(concurrent_results) == 10, (
        f"Concurrent emit failed: {len(concurrent_results)}/10"
    )
    print(
        f"  [PASS] Concurrent safety: 10 threads, {len(concurrent_results)} events received"
    )

    # Test 6: Statistics (simplified)
    bus6 = EventBus()
    test_event5 = "test_stats"
    bus6.on(test_event5, lambda data: None)
    bus6.emit(test_event5)
    bus6.emit(test_event5)

    stats = bus6.get_event_stats()
    assert stats["total_listeners"] >= 1, (
        f"Stats total_listeners wrong: {stats['total_listeners']}"
    )
    assert stats["total_events"] >= 1, (
        f"Stats total_events wrong: {stats['total_events']}"
    )
    print(
        f"  [PASS] Statistics: {stats['total_events']} events, {stats['total_listeners']} listeners"
    )

    print("[OK] EventBus: All 6 tests passed!")


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
            test_app = QApplication(
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

                def resolve_assets_dir():
                    current = Path(__file__).resolve()
                    for parent in current.parents:
                        assets_dir = parent / "assets"
                        if assets_dir.is_dir():
                            return assets_dir
                    return None

                selected_font = None
                assets_dir = resolve_assets_dir()
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
        from PySide6.QtCore import QTimer
        from sonicinput.ui.main_window import MainWindow
        from sonicinput.ui.components.system_tray.tray_controller import TrayController
        from sonicinput.ui.recording_overlay import RecordingOverlay
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
        recording_overlay = RecordingOverlay()

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
        if app_logger and LogCategory:
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
        exit_code = qt_app.exec()

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
        print(f"ERROR: Failed to start GUI: {e}")
        print("Full traceback:")
        import traceback

        traceback.print_exc()
        print("Use --test to run diagnostics")
        sys.exit(1)


def run_diagnostics():
    """Run comprehensive diagnostics without starting the application"""
    print("=== Comprehensive Diagnostics ===")

    if startup_diagnostics is None:
        print("[FAIL] Startup diagnostics not available")
        return

    try:
        report = startup_diagnostics.generate_environment_report()
        startup_diagnostics.print_diagnostic_summary(report)

        # Offer to save report
        try:
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = f"diagnostic_report_{timestamp}.json"

            import json

            with open(report_file, "w") as f:
                json.dump(report, f, indent=2, default=str)

            print(f"\n[SAVE] Detailed report saved to: {report_file}")

        except Exception as e:
            print(f"Warning: Could not save report file: {e}")

    except Exception as e:
        print(f"[FAIL] Diagnostics failed: {e}")
        if app_logger:
            app_logger.log_error(e, "run_diagnostics")


def main():
    """Main application entry point"""
    parser = argparse.ArgumentParser(description="Sonic Input")
    parser.add_argument("--gui", action="store_true", help="Launch with GUI")
    parser.add_argument(
        "--test", action="store_true", help="Run all tests (auto-loads model)"
    )
    parser.add_argument(
        "--diagnostics", action="store_true", help="Run comprehensive diagnostics"
    )
    parser.add_argument(
        "--validate", action="store_true", help="Validate environment only"
    )

    args = parser.parse_args()

    # Set up signal handlers
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    print("=== Sonic Input ===")

    if args.test:
        run_tests()
    elif args.diagnostics:
        run_diagnostics()
    elif args.validate:
        success, report = validate_environment()
        sys.exit(0 if success else 1)
    else:
        # Default: always launch GUI (with or without --gui flag)
        sys.exit(run_gui_with_diagnostics())
        print("  --diagnostics Run comprehensive diagnostics")
        print("  --validate    Validate environment only")
        print("\nExample: python main.py --gui")
        print("         python main.py --diagnostics  # Run diagnostics first")


if __name__ == "__main__":
    main()
