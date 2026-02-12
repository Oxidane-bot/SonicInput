#!/bin/bash
# ACT本地测试环境设置脚本

set -e

echo "=== ACT Local CI/CD Test Setup ==="
echo ""

# 检查必要工具
echo "1. Checking required tools..."

if ! command -v act &> /dev/null; then
    echo "ERROR: act is not installed. Please install it first:"
    echo "  Windows: choco install act-cli"
    echo "  Linux: curl https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash"
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is not installed or not running."
    echo "Please install Docker and ensure it's running."
    exit 1
fi

echo "✓ act version: $(act --version)"
echo "✓ docker is available"

# 检查Docker状态
if ! docker info &> /dev/null; then
    echo "ERROR: Docker is not running. Please start Docker."
    exit 1
fi

echo "✓ docker is running"
echo ""

# 拉取ACT基础镜像
echo "2. Pulling ACT base image..."
docker pull catthehacker/ubuntu:act-latest
echo "✓ Base image pulled"
echo ""

# 创建必要的目录
echo "3. Creating directories..."
mkdir -p .github/workflows
mkdir -p scripts
mkdir -p dist
echo "✓ Directories created"
echo ""

# 设置环境变量
echo "4. Setting up environment variables..."
export CI=true
export GITHUB_ACTIONS=true
export GITHUB_REPOSITORY="local-test/sonicinput"
export GITHUB_RUN_ID="local_run_$(date +%s)"
export GITHUB_SHA="local_sha_$(git rev-parse HEAD 2>/dev/null || echo 'unknown')"
export GITHUB_REF="refs/heads/main"
echo "✓ Environment variables set"
echo ""

# 显示可用的workflows
echo "5. Available workflows:"
if [ -f ".github/workflows/ci.yml" ]; then
    echo "  - CI Checks (ACT-supported jobs)"
    echo "    Command: act -j lint"
    echo "    Command: act -j security"
    echo "    Note: tests job uses windows-latest and is not supported by ACT"
fi

echo "  - Build is local-only (not via ACT)"
echo "    Use: ./scripts/release.ps1"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Usage:"
echo "  # Run ACT-supported CI jobs"
echo "  act -j lint"
echo "  act -j security"
echo ""
echo "  # Check available jobs"
echo "  act -l"
echo ""
echo "  # Run with specific event"
echo "  act -j lint -e push"
echo ""
