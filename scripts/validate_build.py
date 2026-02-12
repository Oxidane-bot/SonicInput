#!/usr/bin/env python3
"""
Pre-build validation script for SonicInput CI/CD pipeline
Validates that the build environment is ready and configuration is correct
"""

import os
import sys
import re
import subprocess
from pathlib import Path
from typing import Dict, Any, Tuple


def load_pyproject_version() -> str:
    """Extract version from pyproject.toml"""
    pyproject_path = Path("pyproject.toml")
    if not pyproject_path.exists():
        return None, "pyproject.toml not found"

    content = pyproject_path.read_text(encoding="utf-8")
    match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
    if match:
        return match.group(1), None
    else:
        return None, "Could not extract version from pyproject.toml"


def validate_ci_workflow() -> Tuple[bool, str]:
    """Validate CI workflow configuration"""
    ci_path = Path(".github/workflows/ci.yml")
    if not ci_path.exists():
        return False, "CI workflow file not found"

    # Basic YAML syntax check
    try:
        content = ci_path.read_text(encoding="utf-8")
        if "jobs:" not in content:
            return False, "CI workflow missing jobs section"

        # Check for required jobs in current CI workflow
        required_jobs = ["lint", "tests", "security"]
        for job in required_jobs:
            if f"{job}:" not in content:
                return False, f"CI workflow missing {job} job"

        return True, "CI workflow validation passed"
    except Exception as e:
        return False, f"CI workflow validation error: {e}"


def validate_build_workflow() -> Tuple[bool, str]:
    """Validate optional build workflow configuration"""
    build_path = Path(".github/workflows/build.yml")
    if not build_path.exists():
        return True, "Build workflow not present (using local build script)"

    try:
        content = build_path.read_text(encoding="utf-8")

        # Check for version extraction step
        if "Extract version from pyproject.toml" not in content:
            return False, "Build workflow missing version extraction step"

        # Check for proper executable naming
        if "SonicInput-v$version-win64.exe" not in content:
            return False, "Build workflow missing optimized executable naming"

        return True, "Build workflow validation passed"
    except Exception as e:
        return False, f"Build workflow validation error: {e}"


def validate_icon_file() -> Tuple[bool, str]:
    """Validate that icon file exists"""
    icon_path = Path("src/sonicinput/resources/icons/app_icon.ico")
    if not icon_path.exists():
        return False, "Icon file not found"

    size = icon_path.stat().st_size
    if size < 1000:  # Less than 1KB seems wrong for an icon
        return False, f"Icon file seems too small: {size} bytes"

    return True, f"Icon file valid ({size} bytes)"


def validate_dependencies() -> Tuple[bool, str]:
    """Validate that required dependencies are available"""
    try:
        # Check if uv is available
        result = subprocess.run(["uv", "--version"], capture_output=True, text=True)
        if result.returncode != 0:
            return False, "uv is not available"

        # Check if we can read dependencies
        result = subprocess.run(["uv", "pip", "list"], capture_output=True, text=True)
        if result.returncode != 0:
            return False, "Cannot list uv packages"

        # Check for key dependencies
        packages = result.stdout.lower()
        required_packages = ["pyside6", "requests", "pydantic"]
        missing = []
        for pkg in required_packages:
            if pkg not in packages:
                missing.append(pkg)

        if missing:
            return False, f"Missing required packages: {', '.join(missing)}"

        return True, "Dependencies validation passed"
    except Exception as e:
        return False, f"Dependency validation error: {e}"


def validate_ci_tests() -> Tuple[bool, str]:
    """Validate test suite layout"""
    test_dir = Path("tests")
    if not test_dir.exists():
        return False, "tests directory not found"

    test_files = list(test_dir.rglob("test_*.py"))
    if not test_files:
        return False, "No test files found under tests/"

    return True, f"Test suite layout valid ({len(test_files)} test files)"


def validate_nuitka() -> Tuple[bool, str]:
    """Validate Nuitka installation"""
    try:
        result = subprocess.run(
            ["uv", "run", "nuitka", "--version"], capture_output=True, text=True
        )

        if result.returncode == 0:
            version = result.stdout.strip()
            return True, f"Nuitka available: {version}"
        else:
            return False, "Nuitka not found or not working"
    except Exception as e:
        return False, f"Nuitka validation error: {e}"


def generate_build_info() -> Dict[str, Any]:
    """Generate build information"""
    version, error = load_pyproject_version()
    if version is None:
        return {"error": error}

    return {
        "version": version,
        "executable_name": f"SonicInput-v{version}-win64.exe",
        "build_mode": "local",
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
        "working_directory": os.getcwd(),
    }


def main():
    """Main validation function"""
    print("=== SonicInput CI/CD Pre-Build Validation ===")
    print()

    # Get version info once
    version, version_error = load_pyproject_version()

    validations = [
        (
            "Version Configuration",
            version is not None,
            version_error if version is None else f"Version {version}",
        ),
        ("CI Workflow", *validate_ci_workflow()),
        ("Build Workflow", *validate_build_workflow()),
        ("Icon File", *validate_icon_file()),
        ("Dependencies", *validate_dependencies()),
        ("CI Tests", *validate_ci_tests()),
        ("Nuitka", *validate_nuitka()),
    ]

    all_passed = True
    for name, passed, message in validations:
        status = "PASS" if passed else "FAIL"
        print(f"{name:20} : {status:5} - {message}")
        if not passed:
            all_passed = False

    print()

    if all_passed:
        print("=== All validations passed! ===")
        print()
        build_info = generate_build_info()
        if "error" not in build_info:
            print("Build Configuration:")
            print(f"  Version: {build_info['version']}")
            print(f"  Executable: {build_info['executable_name']}")
            print(f"  Mode: {build_info['build_mode']}")
            print(f"  Python: {build_info['python_version']}")
            print()
            print("Ready for CI/CD pipeline!")
        else:
            print(f"Error generating build info: {build_info['error']}")
            sys.exit(1)
    else:
        print("=== Some validations failed! ===")
        print("Please fix the issues before pushing to GitHub.")
        sys.exit(1)


if __name__ == "__main__":
    main()
