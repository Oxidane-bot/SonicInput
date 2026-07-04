"""Helper utilities and convenience functions

Provides common utility functions, formatters, converters,
and other helper functions used throughout the application.
"""

import functools
import hashlib
import json
import os
import platform
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from ..core.services.config.app_constants import Paths

# Windows平台窗口隐藏标志
if sys.platform == "win32":
    CREATE_NO_WINDOW = 0x08000000
else:
    CREATE_NO_WINDOW = 0


def get_app_data_dir() -> Path:
    """Get application data directory

    Returns:
        Path to application data directory
    """
    if platform.system() == "Windows":
        app_data = os.environ.get("APPDATA", str(Path.home()))
        return Path(app_data) / Paths.CONFIG_DIR_NAME
    elif platform.system() == "Darwin":  # macOS
        return Path.home() / "Library" / "Application Support" / Paths.CONFIG_DIR_NAME
    else:  # Linux and others
        return Path.home() / ".config" / Paths.CONFIG_DIR_NAME


def ensure_directory(path: Union[str, Path]) -> Path:
    """Ensure directory exists, create if necessary

    Args:
        path: Directory path

    Returns:
        Path object of the directory

    Raises:
        OSError: If directory cannot be created
    """
    path_obj = Path(path)
    path_obj.mkdir(parents=True, exist_ok=True)
    return path_obj


def safe_json_load(file_path: Union[str, Path], default: Any = None) -> Any:
    """Safely load JSON file with error handling

    Args:
        file_path: Path to JSON file
        default: Default value if loading fails

    Returns:
        Loaded JSON data or default value
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return default


def safe_json_save(data: Any, file_path: Union[str, Path], indent: int = 2) -> bool:
    """Safely save data to JSON file

    Args:
        data: Data to save
        file_path: Path to save file
        indent: JSON indentation

    Returns:
        True if successful, False otherwise
    """
    try:
        # Ensure parent directory exists
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        return True
    except (OSError, TypeError, ValueError):
        return False


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted size string
    """
    if size_bytes == 0:
        return "0 B"

    size_names = ["B", "KB", "MB", "GB", "TB"]
    size_index = 0
    size = float(size_bytes)

    while size >= 1024 and size_index < len(size_names) - 1:
        size /= 1024.0
        size_index += 1

    return f"{size:.1f} {size_names[size_index]}"


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted duration string
    """
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds // 60
        remaining_seconds = seconds % 60
        return f"{minutes:.0f}m {remaining_seconds:.0f}s"
    else:
        hours = seconds // 3600
        remaining_minutes = (seconds % 3600) // 60
        return f"{hours:.0f}h {remaining_minutes:.0f}m"


def format_timestamp(
    timestamp: Optional[float] = None, format_str: str = "%Y-%m-%d %H:%M:%S"
) -> str:
    """Format timestamp to string

    Args:
        timestamp: Unix timestamp (defaults to current time)
        format_str: Format string

    Returns:
        Formatted timestamp string
    """
    if timestamp is None:
        timestamp = time.time()

    return datetime.fromtimestamp(timestamp).strftime(format_str)


def get_system_info() -> Dict[str, Any]:
    """Get system information

    Returns:
        Dictionary with system information
    """
    return {
        "platform": platform.system(),
        "platform_version": platform.version(),
        "architecture": platform.architecture()[0],
        "processor": platform.processor(),
        "python_version": platform.python_version(),
        "hostname": platform.node(),
        "username": os.environ.get("USERNAME", os.environ.get("USER", "unknown")),
    }


def get_gpu_info() -> Dict[str, Any]:
    """Get GPU information

    Returns:
        Dictionary with GPU information
    """
    try:
        import torch

        if torch.cuda.is_available():
            return {
                "cuda_available": True,
                "cuda_version": torch.version.cuda,
                "device_count": torch.cuda.device_count(),
                "current_device": torch.cuda.current_device(),
                "device_name": torch.cuda.get_device_name(),
                "memory_total": torch.cuda.get_device_properties(0).total_memory,
                "memory_allocated": torch.cuda.memory_allocated(),
                "memory_cached": torch.cuda.memory_reserved(),
            }
    except ImportError:
        pass

    return {"cuda_available": False}


def is_admin() -> bool:
    """Check if running with administrator privileges

    Returns:
        True if running as admin, False otherwise
    """
    try:
        if platform.system() == "Windows":
            import ctypes

            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        else:
            # os.geteuid only exists on Unix; this branch never runs on Windows
            return getattr(os, "geteuid")() == 0
    except Exception:
        return False


def restart_application(args: Optional[List[str]] = None) -> None:
    """Restart the application

    Args:
        args: Additional command-line arguments
    """
    if args is None:
        args = sys.argv[1:]

    if platform.system() == "Windows":
        # Use python -m to ensure same Python interpreter
        subprocess.Popen(
            [sys.executable, "-m"] + sys.argv + args, creationflags=CREATE_NO_WINDOW
        )
    else:
        os.execv(sys.executable, [sys.executable] + sys.argv + args)


def debounce(delay: float) -> Callable:
    """Decorator to debounce function calls

    Args:
        delay: Delay in seconds

    Returns:
        Decorated function
    """

    def decorator(func: Callable) -> Callable:
        timer = None

        @functools.wraps(func)
        def debounced(*args, **kwargs):
            nonlocal timer

            def call_func():
                func(*args, **kwargs)

            if timer is not None:
                timer.cancel()

            timer = threading.Timer(delay, call_func)
            timer.start()

        return debounced

    return decorator


def throttle(delay: float) -> Callable:
    """Decorator to throttle function calls

    Args:
        delay: Minimum delay between calls in seconds

    Returns:
        Decorated function
    """

    def decorator(func: Callable) -> Callable:
        last_called = [0.0]

        @functools.wraps(func)
        def throttled(*args, **kwargs):
            now = time.time()
            if now - last_called[0] >= delay:
                last_called[0] = now
                return func(*args, **kwargs)

        return throttled

    return decorator


def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0) -> Callable:
    """Decorator to retry function calls on failure

    Args:
        max_attempts: Maximum number of attempts
        delay: Initial delay between attempts
        backoff: Backoff multiplier

    Returns:
        Decorated function
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        time.sleep(current_delay)
                        current_delay *= backoff

            # If all attempts failed, raise the last exception
            raise last_exception

        return wrapper

    return decorator


def safe_call(func: Callable, *args, default: Any = None, **kwargs) -> Any:
    """Safely call a function with error handling

    Args:
        func: Function to call
        *args: Function arguments
        default: Default value if function fails
        **kwargs: Function keyword arguments

    Returns:
        Function result or default value
    """
    try:
        return func(*args, **kwargs)
    except Exception:
        return default


def deep_merge(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries

    Args:
        dict1: First dictionary
        dict2: Second dictionary (takes precedence)

    Returns:
        Merged dictionary
    """
    result = dict1.copy()

    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def generate_hash(data: str, algorithm: str = "sha256") -> str:
    """Generate hash for data

    Args:
        data: Data to hash
        algorithm: Hash algorithm

    Returns:
        Hex hash string
    """
    hasher = hashlib.new(algorithm)
    hasher.update(data.encode("utf-8"))
    return hasher.hexdigest()


def normalize_path(path: Union[str, Path]) -> Path:
    """Normalize and resolve path

    Args:
        path: Path to normalize

    Returns:
        Normalized Path object
    """
    return Path(path).resolve()


def find_available_port(
    start_port: int = 8000, max_attempts: int = 100
) -> Optional[int]:
    """Find an available port

    Args:
        start_port: Port to start searching from
        max_attempts: Maximum ports to try

    Returns:
        Available port number or None if not found
    """
    import socket

    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("localhost", port))
                return port
        except OSError:
            continue

    return None


class SingletonMeta(type):
    """Singleton metaclass"""

    _instances: Dict[type, Any] = {}
    _lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class PerformanceTimer:
    """Performance timing context manager"""

    def __init__(self, operation_name: str = "Operation"):
        self.operation_name = operation_name
        self.start_time = None
        self.end_time = None

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.perf_counter()

    @property
    def elapsed(self) -> float:
        """Get elapsed time in seconds"""
        if self.start_time is None:
            return 0.0
        end = self.end_time if self.end_time is not None else time.perf_counter()
        return end - self.start_time

    def __str__(self) -> str:
        return f"{self.operation_name}: {format_duration(self.elapsed)}"


class EventEmitter:
    """Simple event emitter"""

    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()

    def on(self, event: str, callback: Callable) -> None:
        """Add event listener"""
        with self._lock:
            if event not in self._listeners:
                self._listeners[event] = []
            self._listeners[event].append(callback)

    def off(self, event: str, callback: Callable) -> None:
        """Remove event listener"""
        with self._lock:
            if event in self._listeners:
                try:
                    self._listeners[event].remove(callback)
                except ValueError:
                    pass

    def emit(self, event: str, *args, **kwargs) -> None:
        """Emit event to all listeners"""
        listeners = []
        with self._lock:
            if event in self._listeners:
                listeners = self._listeners[event].copy()

        for callback in listeners:
            try:
                callback(*args, **kwargs)
            except Exception:
                pass  # Don't let one bad listener break others


def version_compare(version1: str, version2: str) -> int:
    """Compare two version strings

    Args:
        version1: First version string
        version2: Second version string

    Returns:
        -1 if version1 < version2, 0 if equal, 1 if version1 > version2
    """

    def normalize_version(version: str) -> List[int]:
        return [int(x) for x in version.split(".")]

    v1 = normalize_version(version1)
    v2 = normalize_version(version2)

    # Pad shorter version with zeros
    max_len = max(len(v1), len(v2))
    v1.extend([0] * (max_len - len(v1)))
    v2.extend([0] * (max_len - len(v2)))

    for i in range(max_len):
        if v1[i] < v2[i]:
            return -1
        elif v1[i] > v2[i]:
            return 1

    return 0


def is_version_compatible(current: str, required: str) -> bool:
    """Check if current version meets minimum requirements

    Args:
        current: Current version string
        required: Required minimum version string

    Returns:
        True if compatible, False otherwise
    """
    return version_compare(current, required) >= 0
