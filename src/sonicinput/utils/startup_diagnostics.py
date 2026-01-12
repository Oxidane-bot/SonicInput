"""Startup diagnostic utilities for comprehensive application health checking"""

import ctypes
import importlib
import os
import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from sonicinput.utils.logger import app_logger

from .environment_validator import environment_validator


class StartupDiagnostics:
    """Comprehensive startup diagnostic system"""

    def __init__(self):
        self.diagnostic_start_time = datetime.now()
        self.test_results = {}
        self.import_results = {}
        self.system_info = {}

    def generate_environment_report(self) -> Dict[str, Any]:
        """Generate comprehensive environment diagnostic report"""
        app_logger.log_audio_event("Generating environment report", {})

        report = {
            "timestamp": self.diagnostic_start_time.isoformat(),
            "system_info": self._collect_system_info(),
            "python_info": self._collect_python_info(),
            "environment_validation": {},
            "import_tests": {},
            "dependency_check": {},
            "file_system_check": {},
            "process_info": self._collect_process_info(),
            "summary": {
                "overall_status": "unknown",
                "critical_issues": [],
                "warnings": [],
                "recommendations": [],
            },
        }

        try:
            # Run environment validation
            env_success, env_results = environment_validator.comprehensive_validation()
            report["environment_validation"] = env_results

            # Run import tests
            report["import_tests"] = self.test_all_imports()

            # Check dependencies
            report["dependency_check"] = self.check_dependency_versions()

            # File system checks
            report["file_system_check"] = self._check_file_system()
            report["runtime_checks"] = {
                "assets": self._check_assets(),
                "samplerate": self._check_samplerate(),
                "qt_plugins": self._check_qt_plugins(),
                "local_asr": self._check_local_asr(),
            }

            # Generate summary
            report["summary"] = self._generate_summary(report)

            app_logger.log_audio_event(
                "Environment report generated",
                {
                    "overall_status": report["summary"]["overall_status"],
                    "critical_issues": len(report["summary"]["critical_issues"]),
                    "warnings": len(report["summary"]["warnings"]),
                },
            )

        except Exception as e:
            app_logger.log_error(e, "environment_report_generation")
            report["summary"]["critical_issues"].append(f"Report generation error: {e}")
            report["summary"]["overall_status"] = "error"

        return report

    def test_all_imports(self) -> Dict[str, bool]:
        """Test all critical imports for the application"""
        app_logger.log_audio_event("Testing all critical imports", {})

        import_tests = {}

        # Core PySide6 imports
        qt_imports = ["PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"]

        # Application imports
        app_imports = [
            "sonicinput.core.voice_input_app",
            "sonicinput.core.di_container",
            "sonicinput.core.hotkey_manager",
            "sonicinput.ui.main_window",
            "sonicinput.ui.recording_overlay",
            "sonicinput.audio.recorder",
        ]

        # GPU 后端在大多数用户环境下不是必需，默认跳过；显式开启时再检测
        if os.getenv("VOICE_INPUT_ENABLE_GPU") or os.getenv("CUDA_VISIBLE_DEVICES"):
            app_imports.append("sonicinput.speech.gpu_manager")

        # External dependencies
        external_imports = ["pynput", "loguru", "requests", "numpy", "samplerate"]

        all_imports = qt_imports + app_imports + external_imports

        for module_name in all_imports:
            try:
                importlib.import_module(module_name)
                import_tests[module_name] = True
                app_logger.log_audio_event(f"Import successful: {module_name}", {})
            except ImportError as e:
                import_tests[module_name] = False
                app_logger.log_error(e, f"import_test_{module_name}")
            except Exception as e:
                import_tests[module_name] = False
                app_logger.log_error(e, f"import_test_error_{module_name}")

        success_count = sum(import_tests.values())
        total_count = len(import_tests)

        app_logger.log_audio_event(
            "Import testing completed",
            {
                "success_count": success_count,
                "total_count": total_count,
                "success_rate": success_count / total_count if total_count > 0 else 0,
            },
        )

        return import_tests

    def check_dependency_versions(self) -> Dict[str, str]:
        """Check versions of all dependencies with detailed info"""
        app_logger.log_audio_event("Checking dependency versions", {})

        versions = {}

        # Critical dependencies with expected version info
        dependencies = [
            "PySide6",
            "pynput",
            "loguru",
            "requests",
            "numpy",
            "samplerate",
            "sherpa_onnx",
        ]

        for dep in dependencies:
            try:
                module = importlib.import_module(dep)

                # Try different ways to get version
                version = None
                for attr in ["__version__", "VERSION", "version"]:
                    if hasattr(module, attr):
                        version = getattr(module, attr)
                        break

                if version is None:
                    # Try package metadata using importlib.metadata (替代已废弃的pkg_resources)
                    try:
                        from importlib.metadata import version as get_version

                        version = get_version(dep)
                    except Exception:
                        version = "Version unknown"

                versions[dep] = str(version)

            except ImportError:
                versions[dep] = "Not installed"
            except Exception as e:
                versions[dep] = f"Error: {e}"

        # System info
        versions["Python"] = sys.version.split()[0]
        versions["Platform"] = platform.platform()
        versions["Architecture"] = platform.architecture()[0]

        app_logger.log_audio_event(
            "Dependency version check completed",
            {
                "dependencies_checked": len(dependencies),
                "python_version": versions["Python"],
            },
        )

        return versions

    def validate_file_permissions(self) -> bool:
        """Validate file system permissions and access"""
        try:
            # Application data directory
            app_data_dir = Path(os.environ.get("APPDATA", ".")) / "SonicInput"
            app_data_dir.mkdir(parents=True, exist_ok=True)

            # Test write access
            test_file = app_data_dir / "permission_test.tmp"
            with open(test_file, "w") as f:
                f.write("permission test")

            # Test read access
            with open(test_file, "r"):
                pass

            # Cleanup
            test_file.unlink()

            app_logger.log_audio_event(
                "File permissions validated", {"app_data_dir": str(app_data_dir)}
            )
            return True

        except Exception as e:
            app_logger.log_error(e, "file_permission_validation")
            return False

    def _collect_system_info(self) -> Dict[str, Any]:
        """Collect comprehensive system information"""
        system_info = {
            "platform": platform.platform(),
            "system": platform.system(),
            "version": platform.version(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "architecture": platform.architecture(),
            "python_version": sys.version,
            "python_executable": sys.executable,
            "environment_variables": {},
        }

        # Important environment variables
        env_vars_of_interest = [
            "PATH",
            "PYTHONPATH",
            "QT_API",
            "QT_PLUGIN_PATH",
            "DISPLAY",
            "HOME",
            "APPDATA",
            "USERPROFILE",
        ]

        for var in env_vars_of_interest:
            system_info["environment_variables"][var] = os.environ.get(var, "Not set")

        return system_info

    def _collect_python_info(self) -> Dict[str, Any]:
        """Collect Python-specific information"""
        python_info = {
            "version": sys.version,
            "version_info": sys.version_info,
            "executable": sys.executable,
            "prefix": sys.prefix,
            "path": sys.path[:5],  # First 5 entries to avoid too much data
            "modules": list(sys.modules.keys())[:20],  # First 20 loaded modules
        }

        return python_info

    def _collect_process_info(self) -> Dict[str, Any]:
        """Collect current process information"""
        process_info = {
            "pid": os.getpid(),
            "cwd": os.getcwd(),
            "command_line": " ".join(sys.argv),
        }

        try:
            import psutil

            process = psutil.Process()
            process_info.update(
                {
                    "memory_info": process.memory_info()._asdict(),
                    "cpu_percent": process.cpu_percent(),
                    "num_threads": process.num_threads(),
                }
            )
        except ImportError:
            process_info["psutil"] = "Not available"
        except Exception as e:
            process_info["psutil_error"] = str(e)

        return process_info

    def _check_file_system(self) -> Dict[str, Any]:
        """Check file system related issues"""
        fs_check = {
            "current_directory_writable": False,
            "app_data_directory_writable": False,
            "temp_directory_writable": False,
            "disk_space_available": "unknown",
        }

        try:
            # Current directory write test
            test_file = Path.cwd() / "temp_write_test.tmp"
            with open(test_file, "w") as f:
                f.write("test")
            test_file.unlink()
            fs_check["current_directory_writable"] = True
        except Exception:
            fs_check["current_directory_writable"] = False

        try:
            # App data directory write test
            app_data_dir = Path(os.environ.get("APPDATA", ".")) / "SonicInput"
            app_data_dir.mkdir(parents=True, exist_ok=True)
            test_file = app_data_dir / "temp_write_test.tmp"
            with open(test_file, "w") as f:
                f.write("test")
            test_file.unlink()
            fs_check["app_data_directory_writable"] = True
        except Exception:
            fs_check["app_data_directory_writable"] = False

        try:
            # Temp directory write test
            import tempfile

            with tempfile.NamedTemporaryFile(delete=True) as f:
                f.write(b"test")
            fs_check["temp_directory_writable"] = True
        except Exception:
            fs_check["temp_directory_writable"] = False

        try:
            # Disk space check
            import shutil

            total, used, free = shutil.disk_usage(Path.cwd())
            fs_check["disk_space_available"] = {
                "total_gb": total // (1024**3),
                "used_gb": used // (1024**3),
                "free_gb": free // (1024**3),
            }
        except Exception:
            fs_check["disk_space_available"] = "Cannot determine"

        return fs_check

    def _resolve_assets_dir(self) -> Path | None:
        current = Path(__file__).resolve()
        for parent in current.parents:
            assets_dir = parent / "assets"
            if assets_dir.is_dir():
                return assets_dir
        return None

    def _check_assets(self) -> Dict[str, Any]:
        """Verify packaged assets are present."""
        result = {
            "assets_dir": None,
            "icon_present": False,
            "fonts_present": False,
            "translations_present": False,
            "font_sizes": {},
            "translation_files": [],
            "errors": [],
            "warnings": [],
        }

        assets_dir = self._resolve_assets_dir()
        if not assets_dir:
            result["errors"].append("Assets directory not found")
            return result

        result["assets_dir"] = str(assets_dir)

        icon_path = assets_dir / "icon.png"
        result["icon_present"] = icon_path.exists()
        if not result["icon_present"]:
            result["warnings"].append("Missing icon.png in assets")

        fonts_dir = assets_dir / "fonts" / "resource-han-rounded"
        font_files = [
            fonts_dir / "ResourceHanRoundedCN-Regular.ttf",
            fonts_dir / "ResourceHanRoundedCN-Bold.ttf",
        ]
        result["fonts_present"] = all(font.exists() for font in font_files)
        for font_path in font_files:
            if font_path.exists():
                result["font_sizes"][font_path.name] = font_path.stat().st_size
        if not result["fonts_present"]:
            result["warnings"].append("Bundled fonts missing")

        translations_dir = assets_dir / "i18n"
        qm_files = sorted(translations_dir.glob("*.qm"))
        result["translations_present"] = len(qm_files) > 0
        result["translation_files"] = [file.name for file in qm_files]
        if not result["translations_present"]:
            result["warnings"].append("No compiled translations found")

        return result

    def _check_samplerate(self) -> Dict[str, Any]:
        """Verify samplerate dependency can resample data."""
        result = {
            "available": False,
            "resample_ok": False,
            "errors": [],
            "warnings": [],
        }

        try:
            import numpy as np
            from samplerate import converters as sr_converters

            result["available"] = True
            samples = np.linspace(0.0, 1.0, 16000, endpoint=False).astype(np.float32)
            resampled = sr_converters.resample(samples, 0.5, converter_type="sinc_best")
            if 7900 <= len(resampled) <= 8100:
                result["resample_ok"] = True
            else:
                result["warnings"].append(
                    f"Unexpected resample length: {len(resampled)}"
                )
        except Exception as exc:
            result["errors"].append(f"samplerate check failed: {exc}")

        return result

    def _check_qt_plugins(self) -> Dict[str, Any]:
        """Check Qt platform plugins are discoverable."""
        result = {
            "plugins_path": None,
            "platforms_path": None,
            "checked_paths": [],
            "qwindows_present": False,
            "errors": [],
            "warnings": [],
        }

        try:
            from PySide6.QtCore import QCoreApplication, QLibraryInfo

            candidate_paths = [
                Path(QLibraryInfo.path(QLibraryInfo.PluginsPath)),
            ]

            try:
                candidate_paths.extend(
                    Path(path) for path in QCoreApplication.libraryPaths()
                )
            except Exception:
                pass

            qt_plugin_env = os.environ.get("QT_PLUGIN_PATH")
            if qt_plugin_env:
                candidate_paths.extend(
                    Path(path)
                    for path in qt_plugin_env.split(os.pathsep)
                    if path.strip()
                )

            seen = set()
            for path in candidate_paths:
                if not path:
                    continue
                key = str(path)
                if key in seen:
                    continue
                seen.add(key)
                result["checked_paths"].append(key)

                platforms_path = path / "platforms"
                qwindows_path = platforms_path / "qwindows.dll"
                if qwindows_path.exists():
                    result["qwindows_present"] = True
                    result["plugins_path"] = str(path)
                    result["platforms_path"] = str(platforms_path)
                    break

            if not result["qwindows_present"]:
                result["plugins_path"] = result["plugins_path"] or (
                    result["checked_paths"][0] if result["checked_paths"] else None
                )
                result["platforms_path"] = result["platforms_path"] or (
                    str(Path(result["plugins_path"]) / "platforms")
                    if result["plugins_path"]
                    else None
                )
                result["warnings"].append("Qt platform plugin qwindows.dll not found")
        except Exception as exc:
            result["errors"].append(f"Qt plugin check failed: {exc}")

        return result

    def _check_local_asr(self) -> Dict[str, Any]:
        """Check sherpa-onnx local ASR runtime dependencies."""
        result = {
            "available": False,
            "sherpa_onnx_found": False,
            "sherpa_onnx_path": None,
            "pyd_path": None,
            "pyd_exists": False,
            "pyd_load_ok": False,
            "pyd_load_error": None,
            "onnxruntime_locations_checked": [],
            "onnxruntime_found": False,
            "model_cached": False,
            "model_dir": None,
            "model_cache_root": None,
            "model_cache_source": None,
            "model_missing_files": [],
            "vc_runtime_present": {},
            "errors": [],
            "warnings": [],
        }

        sherpa_base = None
        try:
            spec = importlib.util.find_spec("sherpa_onnx")
            if spec and spec.submodule_search_locations:
                sherpa_base = Path(list(spec.submodule_search_locations)[0])
                result["sherpa_onnx_found"] = True
                result["sherpa_onnx_path"] = str(sherpa_base)
                pyd_path = sherpa_base / "lib" / "_sherpa_onnx.pyd"
                result["pyd_path"] = str(pyd_path)
                result["pyd_exists"] = pyd_path.exists()
                if pyd_path.exists():
                    try:
                        ctypes.CDLL(str(pyd_path))
                        result["pyd_load_ok"] = True
                    except OSError as exc:
                        result["pyd_load_error"] = str(exc)
                        result["errors"].append(f"_sherpa_onnx.pyd load failed: {exc}")
                else:
                    result["warnings"].append("Missing _sherpa_onnx.pyd")
            else:
                result["warnings"].append("sherpa_onnx not installed")
        except Exception as exc:
            result["errors"].append(f"sherpa_onnx inspection failed: {exc}")

        exe_dir = Path(sys.executable).resolve().parent
        onnx_candidates = [exe_dir / "onnxruntime.dll"]
        if sherpa_base:
            onnx_candidates.append(sherpa_base / "lib" / "onnxruntime.dll")
        system32 = Path(os.environ.get("SystemRoot", r"C:\\Windows")) / "System32"
        onnx_candidates.append(system32 / "onnxruntime.dll")

        result["onnxruntime_locations_checked"] = [
            str(path) for path in onnx_candidates
        ]
        result["onnxruntime_found"] = any(path.exists() for path in onnx_candidates)
        if not result["onnxruntime_found"]:
            result["warnings"].append("onnxruntime.dll not found in common locations")

        vc_runtime = ["vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll"]
        result["vc_runtime_present"] = {
            dll: (system32 / dll).exists() for dll in vc_runtime
        }
        missing_vc = [
            dll for dll, present in result["vc_runtime_present"].items() if not present
        ]
        if missing_vc:
            result["warnings"].append(
                f"Missing VC++ runtime DLLs: {', '.join(missing_vc)}"
            )

        # 3) 模型缓存检查（默认 paraformer）
        try:
            from sonicinput.speech.sherpa_models import SherpaModelManager

            model_mgr = SherpaModelManager()
            result["model_cache_root"] = str(model_mgr.cache_dir)
            result["model_cache_source"] = getattr(model_mgr, "cache_dir_source", None)
            model_dir = model_mgr._get_model_dir("paraformer")
            result["model_dir"] = str(model_dir)
            required = ["tokens.txt", "encoder.int8.onnx", "decoder.int8.onnx"]
            missing_files = [f for f in required if not (model_dir / f).exists()]
            result["model_missing_files"] = missing_files
            result["model_cached"] = len(missing_files) == 0

            # 检查缓存目录可写（下载/解压需要）
            model_mgr.cache_dir.mkdir(parents=True, exist_ok=True)
            test_file = model_mgr.cache_dir / ".diag_write"
            try:
                test_file.touch()
            finally:
                test_file.unlink(missing_ok=True)

            if missing_files:
                result["warnings"].append(
                    f"Model not cached or incomplete: missing {', '.join(missing_files)}"
                )
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(f"Model cache check failed: {exc}")

        result["available"] = (
            result["sherpa_onnx_found"]
            and result["pyd_exists"]
            and result["pyd_load_ok"]
            and result["onnxruntime_found"]
        )

        return result

    def _generate_summary(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary with status and recommendations"""
        summary = {
            "overall_status": "healthy",
            "critical_issues": [],
            "warnings": [],
            "recommendations": [],
        }

        # Check environment validation
        env_validation = report.get("environment_validation", {})
        if not env_validation.get("overall_success", False):
            summary["overall_status"] = "critical"
            summary["critical_issues"].append("Environment validation failed")

            if env_validation.get("errors"):
                summary["critical_issues"].extend(env_validation["errors"])

            if env_validation.get("warnings"):
                summary["warnings"].extend(env_validation["warnings"])

        # Check import tests
        import_tests = report.get("import_tests", {})
        failed_imports = [name for name, success in import_tests.items() if not success]

        critical_imports = [
            "PySide6",
            "PySide6.QtWidgets",
            "sonicinput.core.voice_input_app",
        ]
        critical_failures = [imp for imp in failed_imports if imp in critical_imports]

        if critical_failures:
            summary["overall_status"] = "critical"
            summary["critical_issues"].append(
                f"Critical imports failed: {critical_failures}"
            )

        optional_ignore = {"sonicinput.speech.gpu_manager"}  # GPU 后端非必需
        optional_failures = [
            imp
            for imp in failed_imports
            if imp not in critical_imports and imp not in optional_ignore
        ]
        if optional_failures:
            summary["warnings"].append(f"Optional imports failed: {optional_failures}")

        # Check file system
        fs_check = report.get("file_system_check", {})
        if not fs_check.get("app_data_directory_writable", False):
            summary["critical_issues"].append(
                "Cannot write to application data directory"
            )
            summary["overall_status"] = "critical"
        # 低磁盘空间预警（模型解压/下载容易失败）
        disk = fs_check.get("disk_space_available", {})
        free_gb = disk.get("free_gb")
        if isinstance(free_gb, (int, float)) and free_gb < 10:
            summary["warnings"].append(
                f"Low free disk space: {free_gb} GB remaining (may block model download)"
            )

        # Generate recommendations
        if summary["critical_issues"]:
            summary["recommendations"].append(
                "Fix critical issues before running the application"
            )

        if "PySide6" in failed_imports:
            summary["recommendations"].append("Install PySide6: pip install PySide6")

        if env_validation.get("import_conflicts"):
            summary["recommendations"].append(
                "Resolve package conflicts - consider using virtual environment"
            )

        runtime_checks = report.get("runtime_checks", {})
        for check_name in ("assets", "samplerate", "qt_plugins", "local_asr"):
            details = runtime_checks.get(check_name, {})
            if details.get("errors"):
                summary["critical_issues"].extend(details["errors"])
                summary["overall_status"] = "critical"
            if details.get("warnings"):
                summary["warnings"].extend(details["warnings"])
            # 专门标记本地 ASR 可用性
            if check_name == "local_asr" and not details.get("available", False):
                summary["warnings"].append("Local ASR unavailable; will fall back to cloud/stub")

        # Final status determination
        if len(summary["critical_issues"]) > 0:
            summary["overall_status"] = "critical"
        elif len(summary["warnings"]) > 2:
            summary["overall_status"] = "warning"
        else:
            summary["overall_status"] = "healthy"

        return summary

    def print_diagnostic_summary(self, report: Dict[str, Any]) -> None:
        """Print a human-readable diagnostic summary"""
        print("\n" + "=" * 60)
        print("VOICE INPUT SOFTWARE - STARTUP DIAGNOSTICS")
        print("=" * 60)

        summary = report["summary"]
        status = summary["overall_status"]

        status_symbols = {
            "healthy": "[PASS]",
            "warning": "[WARN] ",
            "critical": "[FAIL]",
            "error": "[ERROR]",
        }

        print(f"\nOverall Status: {status_symbols.get(status, '?')} {status.upper()}")

        if summary["critical_issues"]:
            print(f"\n[FAIL] CRITICAL ISSUES ({len(summary['critical_issues'])}):")
            for issue in summary["critical_issues"]:
                print(f"  • {issue}")

        if summary["warnings"]:
            print(f"\n[WARN]  WARNINGS ({len(summary['warnings'])}):")
            for warning in summary["warnings"]:
                print(f"  • {warning}")

        if summary["recommendations"]:
            print("\n[INFO] RECOMMENDATIONS:")
            for rec in summary["recommendations"]:
                print(f"  • {rec}")

        # Import status summary
        import_tests = report.get("import_tests", {})
        if import_tests:
            success_count = sum(import_tests.values())
            total_count = len(import_tests)
            print(f"\n[INFO] IMPORTS: {success_count}/{total_count} successful")

            failed = [name for name, success in import_tests.items() if not success]
            if failed:
                print(
                    f"   Failed: {', '.join(failed[:3])}{'...' if len(failed) > 3 else ''}"
                )

        # Environment summary
        env_validation = report.get("environment_validation", {})
        if env_validation:
            print("\n[INFO]  ENVIRONMENT:")
            pyside6_validation = env_validation.get("pyside6_validation", {})
            print(
                f"   PySide6: {'[PASS]' if pyside6_validation.get('pyside6_available') else '[FAIL]'}"
            )
            print(
                f"   Display: {'[PASS]' if env_validation.get('display_available') else '[FAIL]'}"
            )
            print(
                f"   System Tray: {'[PASS]' if env_validation.get('system_tray_support') else '[FAIL]'}"
            )

        runtime_checks = report.get("runtime_checks", {})
        if runtime_checks:
            assets_check = runtime_checks.get("assets", {})
            samplerate_check = runtime_checks.get("samplerate", {})
            qt_plugins_check = runtime_checks.get("qt_plugins", {})
            local_asr_check = runtime_checks.get("local_asr", {})
            assets_ok = not assets_check.get("errors")
            samplerate_ok = samplerate_check.get("available") and samplerate_check.get(
                "resample_ok"
            )
            qt_plugins_ok = not qt_plugins_check.get("errors") and qt_plugins_check.get(
                "qwindows_present"
            )
            if local_asr_check.get("errors"):
                local_asr_status = "[FAIL]"
            elif local_asr_check.get("available"):
                local_asr_status = "[PASS]"
            else:
                local_asr_status = "[WARN] "
            print("\n[INFO]  RUNTIME CHECKS:")
            print(f"   Assets: {'[PASS]' if assets_ok else '[FAIL]'}")
            print(f"   Samplerate: {'[PASS]' if samplerate_ok else '[FAIL]'}")
            print(f"   Qt Plugins: {'[PASS]' if qt_plugins_ok else '[FAIL]'}")
            print(f"   Local ASR: {local_asr_status}")

        print("\n" + "=" * 60 + "\n")


# Create global instance
startup_diagnostics = StartupDiagnostics()
