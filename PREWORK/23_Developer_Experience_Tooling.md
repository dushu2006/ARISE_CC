# ARISE — Developer Experience & Tooling Guide

## Overview

Comprehensive developer tooling for building, debugging, profiling, and deploying ARISE. Optimized for the modular monolith architecture with Python, Rust, and TypeScript.

---

## 1. Project Structure

```
ARISE/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml              # Main CI pipeline
│   │   ├── release.yml         # Release automation
│   │   └── security.yml        # Security scanning
│   └── dependabot.yml
├── .vscode/
│   ├── settings.json           # Editor settings
│   ├── launch.json             # Debug configurations
│   ├── tasks.json              # Build tasks
│   └── extensions.json         # Recommended extensions
├── .devcontainer/
│   ├── devcontainer.json       # Codespaces/devcontainer config
│   └── Dockerfile
├── core/                       # Python monorepo (FastAPI + Task Engine)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py           # Pydantic Settings
│   │   ├── errors/             # Error hierarchy
│   │   ├── events/             # Event bus
│   │   ├── logging.py          # Structured logging
│   │   └── runtime/            # HTTP/WS servers
│   ├── task_engine/
│   ├── policy_engine/
│   ├── model_router/
│   ├── memory/
│   ├── agents/
│   ├── voice/
│   ├── automation/
│   └── security/
├── src-tauri/                  # Rust Tauri 2 application
│   ├── src/
│   │   ├── main.rs
│   │   ├── commands/           # Tauri commands
│   │   ├── system_tray.rs
│   │   ├── window.rs
│   │   └── updater.rs
│   ├── Cargo.toml
│   └── tauri.conf.json
├── src/                        # React TypeScript frontend
│   ├── components/
│   ├── hooks/
│   ├── stores/                 # Zustand/Redux
│   ├── pages/
│   ├── services/               # API clients
│   └── main.tsx
├── scripts/
│   ├── dev-setup.sh            # One-command setup
│   ├── db-migrate.py           # Database migrations
│   ├── generate-api.py         # OpenAPI client gen
│   └── benchmark.py            # Performance benchmarks
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── e2e/
│   └── fixtures/
├── docker/
│   ├── Dockerfile.core         # Python service
│   ├── Dockerfile.tauri        # Rust build
│   └── docker-compose.yml      # Local stack
├── docs/
│   ├── architecture/
│   ├── api/
│   └── runbooks/
├── pyproject.toml              # Python project config
├── Cargo.toml                  # Rust workspace
├── package.json                # Node workspace
├── Makefile                    # Common commands
└── README.md
```

---

## 2. Quick Start Commands

### 2.1 One-Command Setup

```bash
# scripts/dev-setup.sh
#!/usr/bin/env bash
set -euo pipefail

echo "🚀 Setting up ARISE development environment..."

# Check prerequisites
check_cmd() {
    if ! command -v "$1" &> /dev/null; then
        echo "❌ $1 not found. Please install $2"
        exit 1
    fi
}

check_cmd python3.11 "Python 3.11+"
check_cmd cargo "Rust (via rustup)"
check_cmd node "Node.js 20+"
check_cmd pnpm "pnpm (npm install -g pnpm)"
check_cmd docker "Docker"

# Python setup
echo "📦 Setting up Python environment..."
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev,test,docs]"

# Install pre-commit hooks
pre-commit install

# Rust setup
echo "🦀 Setting up Rust..."
cd src-tauri
cargo install tauri-cli --version "^2.0"
cd ..

# Node setup
echo "📦 Setting up Node..."
cd src
pnpm install
cd ..

# Database
echo "🗄️ Setting up database..."
docker-compose -f docker/docker-compose.yml up -d postgres redis
sleep 3
python scripts/db-migrate.py upgrade

# Generate API clients
echo "🔧 Generating API clients..."
python scripts/generate-api.py

echo "✅ Setup complete! Run 'make dev' to start development servers."
```

### 2.2 Makefile Commands

```makefile
# Makefile
.PHONY: help dev test lint format type-check build clean

# Default
help:
	@echo "ARISE Development Commands"
	@echo "=========================="
	@echo "make dev           - Start all dev servers"
	@echo "make test          - Run all tests"
	@echo "make lint          - Run all linters"
	@echo "make format        - Format all code"
	@echo "make type-check    - Run type checkers"
	@echo "make build         - Build all artifacts"
	@echo "make clean         - Clean build artifacts"

# Development
dev:
	docker-compose -f docker/docker-compose.yml up -d
	@echo "Starting Python API (FastAPI)..."
	cd core && poetry run uvicorn core.runtime.main:app --reload --port 8000 &
	@echo "Starting Tauri dev..."
	cd src-tauri && cargo tauri dev &
	@echo "Starting React dev (Vite)..."
	cd src && pnpm dev &
	wait

dev-core:
	cd core && poetry run uvicorn core.runtime.main:app --reload --port 8000

dev-tauri:
	cd src-tauri && cargo tauri dev

dev-frontend:
	cd src && pnpm dev

# Testing
test: test-unit test-integration test-contract

test-unit:
	cd core && poetry run pytest tests/unit -v --tb=short
	cd src-tauri && cargo test --lib
	cd src && pnpm test:unit

test-integration:
	cd core && poetry run pytest tests/integration -v --tb=short
	cd src && pnpm test:integration

test-contract:
	cd core && poetry run pytest tests/contract -v --tb=short
	cd src && pnpm test:contract

test-e2e:
	cd core && poetry run pytest tests/e2e -v --tb=short
	cd src && pnpm test:e2e

test-coverage:
	cd core && poetry run pytest --cov=core --cov-report=html
	cd src && pnpm test:coverage

# Linting
lint: lint-python lint-rust lint-typescript

lint-python:
	cd core && poetry run ruff check .
	cd core && poetry run mypy .

lint-rust:
	cd src-tauri && cargo clippy --all-targets --all-features -- -D warnings
	cd src-tauri && cargo fmt --check

lint-typescript:
	cd src && pnpm lint

# Formatting
format:
	cd core && poetry run ruff format .
	cd core && poetry run black .
	cd src-tauri && cargo fmt
	cd src && pnpm format

# Type checking
type-check:
	cd core && poetry run mypy --strict .
	cd src-tauri && cargo check --all-targets
	cd src && pnpm type-check

# Building
build: build-core build-tauri build-frontend

build-core:
	cd core && poetry build

build-tauri:
	cd src-tauri && cargo tauri build

build-frontend:
	cd src && pnpm build

# Database
db-migrate:
	python scripts/db-migrate.py upgrade

db-rollback:
	python scripts/db-migrate.py downgrade

db-reset:
	python scripts/db-migrate.py reset

# Cleaning
clean:
	rm -rf core/dist core/build core/*.egg-info
	cd src-tauri && cargo clean
	rm -rf src/dist src/node_modules
	docker-compose -f docker/docker-compose.yml down -v

# Benchmarks
benchmark:
	python scripts/benchmark.py --all

profile:
	python scripts/profile.py --function=task_engine.execute
```

---

## 3. VS Code Configuration

### 3.1 Settings

```json
// .vscode/settings.json
{
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.organizeImports": "explicit",
    "source.fixAll": "explicit"
  },
  "editor.defaultFormatter": "esbenp.prettier-vscode",
  "editor.rulers": [100, 120],
  "editor.tabSize": 2,
  "files.trimTrailingWhitespace": true,
  "files.insertFinalNewline": true,
  
  // Python
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.mypyEnabled": true,
  "python.linting.ruffEnabled": true,
  "python.formatting.provider": "none",
  "python.analysis.typeCheckingMode": "strict",
  "python.analysis.autoImportCompletions": true,
  
  // Rust
  "rust-analyzer.checkOnSave": true,
  "rust-analyzer.check.command": "clippy",
  "rust-analyzer.cargo.allFeatures": true,
  "rust-analyzer.inlayHints.typeHints.enable": true,
  "rust-analyzer.inlayHints.parameterNames.enable": true,
  
  // TypeScript
  "typescript.preferences.importModuleSpecifier": "non-relative",
  "typescript.updateImportsOnFileMove.enabled": "always",
  "typescript.inlayHints.parameterNames.enabled": "all",
  "typescript.inlayHints.parameterTypes.enabled": true,
  
  // Files
  "files.exclude": {
    "**/__pycache__": true,
    "**/*.pyc": true,
    "**/target": true,
    "**/node_modules": true,
    "**/dist": true,
    "**/.venv": true
  },
  
  // Search
  "search.exclude": {
    "**/target": true,
    "**/node_modules": true,
    "**/dist": true,
    "**/.venv": true,
    "**/*.lock": true
  }
}
```

### 3.2 Launch Configurations

```json
// .vscode/launch.json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Debug FastAPI",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": [
        "core.runtime.main:app",
        "--reload",
        "--port", "8000",
        "--log-level", "debug"
      ],
      "cwd": "${workspaceFolder}/core",
      "env": {
        "PYTHONPATH": "${workspaceFolder}/core",
        "ARISE_ENV": "development"
      },
      "console": "integratedTerminal",
      "justMyCode": false
    },
    {
      "name": "Debug Tauri (Rust)",
      "type": "lldb",
      "request": "launch",
      "cargo": {
        "args": ["build", "--manifest-path", "${workspaceFolder}/src-tauri/Cargo.toml"],
        "filter": {
          "name": "arise",
          "kind": "bin"
        }
      },
      "args": [],
      "cwd": "${workspaceFolder}/src-tauri",
      "env": {
        "RUST_LOG": "debug,tauri=trace",
        "ARISE_ENV": "development"
      }
    },
    {
      "name": "Debug Tauri (Attach)",
      "type": "lldb",
      "request": "attach",
      "pid": "${command:pickProcess}",
      "cwd": "${workspaceFolder}/src-tauri"
    },
    {
      "name": "Debug React (Chrome)",
      "type": "chrome",
      "request": "launch",
      "url": "http://localhost:5173",
      "webRoot": "${workspaceFolder}/src",
      "sourceMapPathOverrides": {
        "webpack:///src/*": "${webRoot}/*"
      }
    },
    {
      "name": "Debug React (Edge)",
      "type": "msedge",
      "request": "launch",
      "url": "http://localhost:5173",
      "webRoot": "${workspaceFolder}/src"
    },
    {
      "name": "Debug Python Tests",
      "type": "python",
      "request": "launch",
      "module": "pytest",
      "args": [
        "tests/",
        "-v",
        "--tb=long",
        "-k", "${input:testFilter}"
      ],
      "cwd": "${workspaceFolder}/core",
      "env": {
        "PYTHONPATH": "${workspaceFolder}/core",
        "ARISE_ENV": "test"
      },
      "console": "integratedTerminal"
    },
    {
      "name": "Debug Rust Tests",
      "type": "lldb",
      "request": "launch",
      "cargo": {
        "args": ["test", "--manifest-path", "${workspaceFolder}/src-tauri/Cargo.toml", "--", "${input:testFilter}"],
        "filter": {
          "name": "arise",
          "kind": "lib"
        }
      },
      "cwd": "${workspaceFolder}/src-tauri"
    }
  ],
  "inputs": [
    {
      "id": "testFilter",
      "type": "promptString",
      "description": "Test filter (e.g. test_task_lifecycle)",
      "default": ""
    }
  ]
}
```

### 3.3 Tasks

```json
// .vscode/tasks.json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Build All",
      "dependsOn": ["Build Core", "Build Tauri", "Build Frontend"],
      "group": "build"
    },
    {
      "label": "Build Core",
      "type": "shell",
      "command": "poetry build",
      "cwd": "${workspaceFolder}/core",
      "group": "build",
      "problemMatcher": "$python"
    },
    {
      "label": "Build Tauri",
      "type": "shell",
      "command": "cargo tauri build",
      "cwd": "${workspaceFolder}/src-tauri",
      "group": "build",
      "problemMatcher": "$rustc"
    },
    {
      "label": "Build Frontend",
      "type": "shell",
      "command": "pnpm build",
      "cwd": "${workspaceFolder}/src",
      "group": "build",
      "problemMatcher": "$tsc"
    },
    {
      "label": "Run Tests",
      "dependsOn": ["Test Core", "Test Tauri", "Test Frontend"],
      "group": "test"
    },
    {
      "label": "Test Core",
      "type": "shell",
      "command": "poetry run pytest tests/ -v",
      "cwd": "${workspaceFolder}/core",
      "group": "test",
      "problemMatcher": "$python"
    },
    {
      "label": "Test Tauri",
      "type": "shell",
      "command": "cargo test",
      "cwd": "${workspaceFolder}/src-tauri",
      "group": "test",
      "problemMatcher": "$rustc"
    },
    {
      "label": "Test Frontend",
      "type": "shell",
      "command": "pnpm test",
      "cwd": "${workspaceFolder}/src",
      "group": "test",
      "problemMatcher": "$tsc"
    },
    {
      "label": "Generate API Client",
      "type": "shell",
      "command": "python scripts/generate-api.py",
      "cwd": "${workspaceFolder}",
      "group": "none"
    },
    {
      "label": "Database Migrate",
      "type": "shell",
      "command": "python scripts/db-migrate.py upgrade",
      "cwd": "${workspaceFolder}",
      "group": "none"
    }
  ]
}
```

### 3.4 Recommended Extensions

```json
// .vscode/extensions.json
{
  "recommendations": [
    // Python
    "charliermarsh.ruff",
    "ms-python.python",
    "ms-python.mypy-type-checker",
    "ms-python.black-formatter",
    
    // Rust
    "rust-lang.rust-analyzer",
    "tamasfe.even-better-toml",
    "serayuzgur.crates",
    
    // TypeScript/React
    "dbaeumer.vscode-eslint",
    "esbenp.prettier-vscode",
    "bradlc.vscode-tailwindcss",
    "formulahendry.auto-rename-tag",
    
    // General
    "github.vscode-github-actions",
    "ms-azuretools.vscode-docker",
    "redhat.vscode-yaml",
    "streetsidesoftware.code-spell-checker",
    "usernamehw.errorlens",
    "gruntfuggly.todo-tree",
    
    // Tauri
    "tauri-apps.tauri-vscode",
    
    // Database
    "mtxr.sqltools",
    "mtxr.sqltools-driver-pg",
    
    // Profiling
    "ms-python.python-debugpy"
  ]
}
```

---

## 4. Dev Container

```json
// .devcontainer/devcontainer.json
{
  "name": "ARISE Development",
  "build": {
    "dockerfile": "Dockerfile",
    "args": {
      "RUST_VERSION": "1.78",
      "NODE_VERSION": "20"
    }
  },
  "customizations": {
    "vscode": {
      "extensions": [
        "charliermarsh.ruff",
        "ms-python.python",
        "rust-lang.rust-analyzer",
        "dbaeumer.vscode-eslint",
        "esbenp.prettier-vscode",
        "tauri-apps.tauri-vscode"
      ],
      "settings": {
        "terminal.integrated.defaultProfile.linux": "zsh",
        "python.defaultInterpreterPath": "/workspace/.venv/bin/python"
      }
    }
  },
  "forwardPorts": [8000, 5173, 5432, 6379],
  "postCreateCommand": "bash scripts/dev-setup.sh",
  "remoteUser": "vscode",
  "features": {
    "ghcr.io/devcontainers/features/docker-in-docker:2": {},
    "ghcr.io/devcontainers/features/github-cli:1": {}
  }
}
```

```dockerfile
# .devcontainer/Dockerfile
FROM mcr.microsoft.com/devcontainers/base:ubuntu-22.04

ARG RUST_VERSION=1.78
ARG NODE_VERSION=20

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.11 python3.11-venv python3.11-dev \
    postgresql-client redis-tools \
    libwebkit2gtk-4.1-dev \
    libayatana-appindicator3-1 \
    librsvg2-dev \
    patchelf \
    && rm -rf /var/lib/apt/lists/*

# Install Rust
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain ${RUST_VERSION}
ENV PATH="/root/.cargo/bin:${PATH}"

# Install Node via nvm
RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
ENV NVM_DIR="/root/.nvm"
RUN . "$NVM_DIR/nvm.sh" && nvm install ${NODE_VERSION} && nvm use ${NODE_VERSION}

# Install pnpm
RUN . "$NVM_DIR/nvm.sh" && npm install -g pnpm

# Install Python tools
RUN python3.11 -m pip install --upgrade pip poetry pre-commit

WORKDIR /workspace
```

---

## 5. CI/CD Pipeline

### 5.1 Main CI Workflow

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

env:
  PYTHON_VERSION: "3.11"
  RUST_VERSION: "1.78"
  NODE_VERSION: "20"

jobs:
  # Python checks
  python-lint:
    name: Python Lint & Type Check
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: ./core
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install -e ".[dev,test]"
      - name: Ruff check
        run: ruff check .
      - name: Ruff format check
        run: ruff format --check .
      - name: MyPy type check
        run: mypy --strict .

  python-test:
    name: Python Tests
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: ./core
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: postgres
        ports: [5432:5432]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7
        ports: [6379:6379]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install -e ".[dev,test]"
      - name: Run migrations
        run: python ../scripts/db-migrate.py upgrade
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/arise
      - name: Run tests
        run: pytest tests/ -v --tb=short --cov=core --cov-report=xml
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/arise
          REDIS_URL: redis://localhost:6379/0
          ARISE_ENV: test
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: ./core/coverage.xml

  # Rust checks
  rust-lint:
    name: Rust Lint & Check
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: ./src-tauri
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
        with:
          toolchain: ${{ env.RUST_VERSION }}
          components: rustfmt, clippy
      - name: Cache cargo
        uses: Swatinem/rust-cache@v2
      - name: Check formatting
        run: cargo fmt --check
      - name: Clippy
        run: cargo clippy --all-targets --all-features -- -D warnings
      - name: Check
        run: cargo check --all-targets

  rust-test:
    name: Rust Tests
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: ./src-tauri
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
        with:
          toolchain: ${{ env.RUST_VERSION }}
      - name: Cache cargo
        uses: Swatinem/rust-cache@v2
      - name: Run tests
        run: cargo test --all-targets

  # TypeScript checks
  ts-lint:
    name: TypeScript Lint & Type Check
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: ./src
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: 'pnpm'
      - name: Install dependencies
        run: pnpm install --frozen-lockfile
      - name: Lint
        run: pnpm lint
      - name: Type check
        run: pnpm type-check
      - name: Format check
        run: pnpm format:check

  ts-test:
    name: TypeScript Tests
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: ./src
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: 'pnpm'
      - name: Install dependencies
        run: pnpm install --frozen-lockfile
      - name: Run tests
        run: pnpm test --coverage
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: ./src/coverage/lcov.info

  # Integration tests
  integration-test:
    name: Integration Tests
    runs-on: ubuntu-latest
    needs: [python-test, rust-test, ts-test]
    steps:
      - uses: actions/checkout@v4
      - name: Start services
        run: docker-compose -f docker/docker-compose.yml up -d
      - name: Wait for services
        run: sleep 10
      - name: Run integration tests
        run: |
          cd core && poetry run pytest tests/integration -v
          cd ../src && pnpm test:integration
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/arise
          REDIS_URL: redis://localhost:6379/0

  # Build artifacts
  build:
    name: Build Artifacts
    runs-on: ubuntu-latest
    needs: [python-lint, python-test, rust-lint, rust-test, ts-lint, ts-test]
    steps:
      - uses: actions/checkout@v4
      - name: Build Python package
        run: |
          cd core && poetry build
      - name: Build Tauri app
        run: |
          cd src-tauri && cargo tauri build
      - name: Build Frontend
        run: |
          cd src && pnpm build
      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: build-artifacts
          path: |
            core/dist/
            src-tauri/target/release/bundle/
            src/dist/

  # Security scanning
  security:
    name: Security Scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Trivy
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          scan-ref: '.'
          format: 'sarif'
          output: 'trivy.sarif'
      - name: Upload Trivy results
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: 'trivy.sarif'
      - name: Python security
        run: |
          cd core && pip install safety && safety check
      - name: Rust security
        run: |
          cd src-tauri && cargo install cargo-audit && cargo audit
      - name: Node security
        run: |
          cd src && pnpm audit

  # E2E tests (scheduled)
  e2e-test:
    name: E2E Tests
    runs-on: windows-latest  # Need Windows for UI Automation
    if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      - name: Setup Rust
        uses: dtolnay/rust-toolchain@stable
        with:
          toolchain: ${{ env.RUST_VERSION }}
      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: 'pnpm'
      - name: Install dependencies
        run: |
          cd core && pip install -e ".[dev,test]"
          cd ../src-tauri && cargo build --release
          cd ../src && pnpm install --frozen-lockfile && pnpm build
      - name: Run E2E tests
        run: |
          cd core && poetry run pytest tests/e2e -v
          cd ../src && pnpm test:e2e
```

---

## 6. Debugging & Profiling Tools

### 6.1 Python Debugging

```python
# scripts/debug_task.py
#!/usr/bin/env python
"""Debug task execution with detailed tracing"""

import asyncio
import sys
sys.path.insert(0, "core")

from core.task_engine import TaskEngine
from core.task_engine.models import Task, TaskStatus
from core.logging import setup_logging
import logging

setup_logging(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def debug_task():
    engine = TaskEngine()
    await engine.initialize()
    
    # Create test task
    task = Task(
        kind="shell.exec",
        payload={"command": "echo hello", "timeout": 10},
        metadata={"debug": True}
    )
    
    # Execute with tracing
    logger.info(f"Submitting task: {task.id}")
    result = await engine.submit_and_wait(task, timeout=30)
    
    logger.info(f"Task completed: {result.status}")
    logger.info(f"Result: {result.output}")
    
    # Print execution trace
    trace = await engine.get_execution_trace(task.id)
    for event in trace:
        logger.info(f"  {event.timestamp} [{event.state}] {event.message}")

if __name__ == "__main__":
    asyncio.run(debug_task())
```

### 6.2 Profiling

```python
# scripts/profile.py
#!/usr/bin/env python
"""Performance profiling for ARISE components"""

import asyncio
import cProfile
import pstats
import sys
from pathlib import Path
sys.path.insert(0, "core")

from core.task_engine import TaskEngine
from core.model_router import ModelRouter
from core.memory import MemorySystem

async def profile_task_engine():
    """Profile task engine execution"""
    engine = TaskEngine()
    await engine.initialize()
    
    # Create multiple tasks
    tasks = []
    for i in range(100):
        task = Task(
            kind="shell.exec",
            payload={"command": f"echo task-{i}", "timeout": 5}
        )
        tasks.append(engine.submit(task))
    
    await asyncio.gather(*tasks)
    await engine.shutdown()

async def profile_model_router():
    """Profile model router with various providers"""
    router = ModelRouter()
    await router.initialize()
    
    # Test different task types
    test_cases = [
        ("coding", "Write a Python function to parse JSON"),
        ("analysis", "Analyze the sentiment of this text"),
        ("creative", "Write a short story about AI"),
        ("reasoning", "Solve this logic puzzle..."),
    ]
    
    for task_type, prompt in test_cases:
        await router.complete(task_type, prompt)
    
    await router.shutdown()

def run_profile(target: str, output: str = "profile.stats"):
    """Run profiler on target function"""
    profiler = cProfile.Profile()
    
    if target == "task_engine":
        profiler.enable()
        asyncio.run(profile_task_engine())
        profiler.disable()
    elif target == "model_router":
        profiler.enable()
        asyncio.run(profile_model_router())
        profiler.disable()
    else:
        print(f"Unknown target: {target}")
        return
    
    # Save stats
    stats = pstats.Stats(profiler).sort_stats('cumulative')
    stats.dump_stats(output)
    
    # Print summary
    stats.print_stats(20)
    print(f"\nFull stats saved to {output}")
    print(f"Run: python -m pstats {output}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--function", choices=["task_engine", "model_router"], required=True)
    parser.add_argument("--output", default="profile.stats")
    args = parser.parse_args()
    
    run_profile(args.function, args.output)
```

### 6.3 Rust Profiling

```toml
# src-tauri/Cargo.toml (profile section)
[profile.release]
debug = true          # Include debug symbols
lto = "fat"           # Link-time optimization
codegen-units = 1     # Better optimization
panic = "abort"       # Smaller binary

[profile.profiling]
inherits = "release"
debug = true

# Enable profiling
[features]
profiling = ["pgo", "backtrace"]
```

```bash
# Profile with perf (Linux)
cargo build --profile profiling --features profiling
perf record --call-graph=dwarf ./target/profiling/arise
perf report

# Profile with samply (cross-platform)
cargo install samply
samply record ./target/profiling/arise
samply open
```

### 6.4 Frontend Profiling

```typescript
// src/lib/profiling.ts
import { PerformanceObserver, performance } from 'perf_hooks';

export function startProfiling(name: string) {
  performance.mark(`${name}-start`);
}

export function endProfiling(name: string) {
  performance.mark(`${name}-end`);
  performance.measure(name, `${name}-start`, `${name}-end`);
  
  const measure = performance.getEntriesByName(name)[0];
  console.log(`[Profile] ${name}: ${measure.duration.toFixed(2)}ms`);
  
  return measure.duration;
}

// React component profiling
export function useRenderProfiler(componentName: string) {
  const renderStart = performance.now();
  
  return () => {
    const duration = performance.now() - renderStart;
    if (duration > 16) { // Log slow renders (>1 frame)
      console.warn(`[Slow Render] ${componentName}: ${duration.toFixed(2)}ms`);
    }
  };
}

// Memory profiling
export async function profileMemory() {
  if ('memory' in performance) {
    const mem = (performance as any).memory;
    return {
      used: mem.usedJSHeapSize / 1024 / 1024,
      total: mem.totalJSHeapSize / 1024 / 1024,
      limit: mem.jsHeapSizeLimit / 1024 / 1024,
    };
  }
  return null;
}
```

---

## 7. Database Tooling

### 7.1 Migration System

```python
# scripts/db-migrate.py
#!/usr/bin/env python
"""Database migration management"""

import asyncio
import sys
from pathlib import Path
sys.path.insert(0, "core")

from core.database import Database
from alembic.config import Config
from alembic import command

def get_alembic_config() -> Config:
    cfg = Config("core/alembic.ini")
    cfg.set_main_option("script_location", "core/migrations")
    return cfg

def upgrade(revision: str = "head"):
    """Apply migrations"""
    cfg = get_alembic_config()
    command.upgrade(cfg, revision)
    print(f"Upgraded to {revision}")

def downgrade(revision: str = "-1"):
    """Rollback migrations"""
    cfg = get_alembic_config()
    command.downgrade(cfg, revision)
    print(f"Downgraded to {revision}")

def create_revision(message: str):
    """Create new migration"""
    cfg = get_alembic_config()
    command.revision(cfg, message=message, autogenerate=True)
    print(f"Created revision: {message}")

def current():
    """Show current revision"""
    cfg = get_alembic_config()
    command.current(cfg)

def history():
    """Show migration history"""
    cfg = get_alembic_config()
    command.history(cfg)

def reset():
    """Reset database (DANGEROUS)"""
    confirm = input("This will destroy all data. Type 'yes' to confirm: ")
    if confirm != "yes":
        print("Aborted")
        return
    
    cfg = get_alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    print("Database reset complete")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    subparsers.add_parser("upgrade", help="Apply migrations").add_argument("revision", nargs="?", default="head")
    subparsers.add_parser("downgrade", help="Rollback migrations").add_argument("revision", nargs="?", default="-1")
    subparsers.add_parser("create", help="Create migration").add_argument("message")
    subparsers.add_parser("current", help="Show current revision")
    subparsers.add_parser("history", help="Show migration history")
    subparsers.add_parser("reset", help="Reset database")
    
    args = parser.parse_args()
    
    if args.command == "upgrade":
        upgrade(args.revision)
    elif args.command == "downgrade":
        downgrade(args.revision)
    elif args.command == "create":
        create_revision(args.message)
    elif args.command == "current":
        current()
    elif args.command == "history":
        history()
    elif args.command == "reset":
        reset()
```

### 7.2 Database Inspection

```python
# scripts/db-inspect.py
#!/usr/bin/env python
"""Database inspection utilities"""

import sys
sys.path.insert(0, "core")

from core.database import Database
from sqlalchemy import inspect, text
import asyncio

async def list_tables():
    db = Database()
    await db.initialize()
    
    async with db.engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT tablename, pg_size_pretty(pg_total_relation_size(tablename::regclass)) as size
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY pg_total_relation_size(tablename::regclass) DESC
        """))
        
        print("Tables:")
        for row in result:
            print(f"  {row.tablename:30} {row.size}")

async def table_stats(table: str):
    db = Database()
    await db.initialize()
    
    async with db.engine.connect() as conn:
        # Row count
        result = await conn.execute(text(f"SELECT count(*) FROM {table}"))
        count = result.scalar()
        
        # Size
        result = await conn.execute(text(f"""
            SELECT pg_size_pretty(pg_total_relation_size('{table}'::regclass))
        """))
        size = result.scalar()
        
        # Indexes
        result = await conn.execute(text(f"""
            SELECT indexname, pg_size_pretty(pg_relation_size(indexname::regclass)) as size
            FROM pg_indexes
            WHERE tablename = '{table}'
        """))
        
        print(f"Table: {table}")
        print(f"  Rows: {count:,}")
        print(f"  Size: {size}")
        print(f"  Indexes:")
        for row in result:
            print(f"    {row.indexname:40} {row.size}")

async def slow_queries(limit: int = 10):
    db = Database()
    await db.initialize()
    
    async with db.engine.connect() as conn:
        result = await conn.execute(text(f"""
            SELECT query, calls, mean_exec_time, total_exec_time
            FROM pg_stat_statements
            ORDER BY mean_exec_time DESC
            LIMIT {limit}
        """))
        
        print("Slowest Queries:")
        for row in result:
            print(f"  {row.mean_exec_time:.2f}ms avg ({row.calls} calls)")
            print(f"    {row.query[:100]}...")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    subparsers.add_parser("tables", help="List all tables")
    subparsers.add_parser("stats", help="Table statistics").add_argument("table")
    subparsers.add_parser("slow", help="Slow queries").add_argument("--limit", type=int, default=10)
    
    args = parser.parse_args()
    
    if args.command == "tables":
        asyncio.run(list_tables())
    elif args.command == "stats":
        asyncio.run(table_stats(args.table))
    elif args.command == "slow":
        asyncio.run(slow_queries(args.limit))
```

---

## 8. API Development Tools

### 8.1 API Client Generation

```python
# scripts/generate-api.py
#!/usr/bin/env python
"""Generate TypeScript API clients from OpenAPI spec"""

import subprocess
import sys
from pathlib import Path

def generate_openapi():
    """Generate OpenAPI spec from FastAPI"""
    # Start server temporarily
    import uvicorn
    from multiprocessing import Process
    import time
    import requests
    
    def run_server():
        uvicorn.run("core.runtime.main:app", host="127.0.0.1", port=8001, log_level="error")
    
    proc = Process(target=run_server)
    proc.start()
    time.sleep(2)
    
    try:
        # Fetch OpenAPI spec
        resp = requests.get("http://127.0.0.1:8001/openapi.json")
        resp.raise_for_status()
        
        spec_path = Path("docs/api/openapi.json")
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(resp.text)
        print(f"OpenAPI spec saved to {spec_path}")
    finally:
        proc.terminate()

def generate_typescript_client():
    """Generate TypeScript client using openapi-typescript-codegen"""
    spec_path = "docs/api/openapi.json"
    output_dir = "src/services/api"
    
    subprocess.run([
        "npx", "openapi-typescript-codegen",
        "-i", spec_path,
        "-o", output_dir,
        "--client", "fetch",
        "--use-options",
        "--export-schemas",
        "--export-services",
        "--name", "arise-api"
    ], check=True)
    
    print(f"TypeScript client generated in {output_dir}")

def generate_python_client():
    """Generate Python client using openapi-python-client"""
    spec_path = "docs/api/openapi.json"
    output_dir = "core/generated"
    
    subprocess.run([
        "openapi-python-client",
        "generate",
        "--path", spec_path,
        "--output-path", output_dir,
        "--config", "scripts/openapi-config.yml"
    ], check=True)
    
    print(f"Python client generated in {output_dir}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--openapi", action="store_true", help="Generate OpenAPI spec")
    parser.add_argument("--ts", action="store_true", help="Generate TypeScript client")
    parser.add_argument("--py", action="store_true", help="Generate Python client")
    parser.add_argument("--all", action="store_true", help="Generate all")
    
    args = parser.parse_args()
    
    if args.all or args.openapi:
        generate_openapi()
    if args.all or args.ts:
        generate_typescript_client()
    if args.all or args.py:
        generate_python_client()
```

### 8.2 API Testing

```python
# tests/api/test_contract.py
"""Contract tests for API endpoints"""

import pytest
from httpx import AsyncClient
from core.runtime.main import app

@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

class TestTaskAPI:
    async def test_create_task(self, client):
        response = await client.post("/api/v1/tasks", json={
            "kind": "shell.exec",
            "payload": {"command": "echo hello"},
        })
        assert response.status_code == 201
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "created"
    
    async def test_get_task(self, client):
        # Create task first
        create_resp = await client.post("/api/v1/tasks", json={
            "kind": "shell.exec",
            "payload": {"command": "echo hello"},
        })
        task_id = create_resp.json()["task_id"]
        
        # Get task
        response = await client.get(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
    
    async def test_cancel_task(self, client):
        create_resp = await client.post("/api/v1/tasks", json={
            "kind": "shell.exec",
            "payload": {"command": "sleep 10"},
        })
        task_id = create_resp.json()["task_id"]
        
        response = await client.post(f"/api/v1/tasks/{task_id}/cancel")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelling"

class TestMemoryAPI:
    async def test_store_memory(self, client):
        response = await client.post("/api/v1/memory", json={
            "kind": "semantic",
            "content": "User prefers dark mode",
            "confidence": 0.9,
        })
        assert response.status_code == 201
        data = response.json()
        assert "memory_id" in data
    
    async def test_query_memory(self, client):
        # Store first
        await client.post("/api/v1/memory", json={
            "kind": "semantic",
            "content": "User prefers dark mode",
            "confidence": 0.9,
        })
        
        response = await client.get("/api/v1/memory", params={
            "query": "dark mode",
            "kind": "semantic",
            "limit": 5,
        })
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) > 0
```

---

## 9. Monitoring & Observability

### 9.1 Structured Logging

```python
# core/logging.py
import logging
import json
import sys
from datetime import datetime
from typing import Any, Dict
from contextvars import ContextVar
import uuid

# Context variables for correlation
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")
task_id_var: ContextVar[str] = ContextVar("task_id", default="")
agent_id_var: ContextVar[str] = ContextVar("agent_id", default="")

class StructuredFormatter(logging.Formatter):
    """JSON formatter with context"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id_var.get(),
            "task_id": task_id_var.get(),
            "agent_id": agent_id_var.get(),
        }
        
        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in ["name", "msg", "args", "levelname", "levelno", 
                          "pathname", "filename", "module", "lineno",
                          "funcName", "created", "msecs", "relativeCreated",
                          "thread", "threadName", "processName", "process",
                          "getMessage", "exc_info", "exc_text", "stack_info"]:
                log_data[key] = value
        
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, default=str)

def setup_logging(level: int = logging.INFO, json_output: bool = True):
    """Configure structured logging"""
    handler = logging.StreamHandler(sys.stdout)
    
    if json_output:
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s"
        ))
    
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]
    
    # Reduce noise from libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

# Context managers
class CorrelationContext:
    def __init__(self, correlation_id: str = None):
        self.correlation_id = correlation_id or str(uuid.uuid4())[:8]
        self.token = None
    
    def __enter__(self):
        self.token = correlation_id_var.set(self.correlation_id)
        return self.correlation_id
    
    def __exit__(self, *args):
        correlation_id_var.reset(self.token)

class TaskContext:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.token = None
    
    def __enter__(self):
        self.token = task_id_var.set(self.task_id)
        return self
    
    def __exit__(self, *args):
        task_id_var.reset(self.token)
```

### 9.2 Metrics Collection

```python
# core/metrics.py
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry
from functools import wraps
import time
import asyncio

# Registry
registry = CollectorRegistry()

# Metrics
task_submitted = Counter(
    "arise_tasks_submitted_total",
    "Total tasks submitted",
    ["kind", "priority"],
    registry=registry
)

task_completed = Counter(
    "arise_tasks_completed_total",
    "Total tasks completed",
    ["kind", "status"],
    registry=registry
)

task_duration = Histogram(
    "arise_task_duration_seconds",
    "Task execution duration",
    ["kind"],
    registry=registry
)

model_requests = Counter(
    "arise_model_requests_total",
    "Total model requests",
    ["provider", "task_type", "status"],
    registry=registry
)

model_latency = Histogram(
    "arise_model_latency_seconds",
    "Model request latency",
    ["provider", "task_type"],
    registry=registry
)

memory_operations = Counter(
    "arise_memory_operations_total",
    "Memory operations",
    ["kind", "operation", "status"],
    registry=registry
)

active_tasks = Gauge(
    "arise_active_tasks",
    "Currently active tasks",
    registry=registry
)

agent_health = Gauge(
    "arise_agent_healthy",
    "Agent health status (1=healthy, 0=unhealthy)",
    ["agent_id", "role"],
    registry=registry
)

# Decorators
def track_task_duration(kind: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.time()
            active_tasks.inc()
            try:
                result = await func(*args, **kwargs)
                task_completed.labels(kind=kind, status="success").inc()
                return result
            except Exception as e:
                task_completed.labels(kind=kind, status="error").inc()
                raise
            finally:
                task_duration.labels(kind=kind).observe(time.time() - start)
                active_tasks.dec()
        return wrapper
    return decorator

def track_model_request(provider: str, task_type: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                model_requests.labels(provider=provider, task_type=task_type, status="success").inc()
                return result
            except Exception as e:
                model_requests.labels(provider=provider, task_type=task_type, status="error").inc()
                raise
            finally:
                model_latency.labels(provider=provider, task_type=task_type).observe(time.time() - start)
        return wrapper
    return decorator

# Metrics endpoint
from fastapi import Response
from prometheus_client import generate_latest

async def metrics_endpoint():
    return Response(
        content=generate_latest(registry),
        media_type="text/plain"
    )
```

---

## 10. Release Automation

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags:
      - "v*"

permissions:
  contents: write
  packages: write

jobs:
  release:
    name: Create Release
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      
      - name: Generate changelog
        id: changelog
        run: |
          git log $(git describe --tags --abbrev=0 HEAD^)..HEAD --pretty=format:"- %s (%an)" > changelog.md
          echo "changelog<<EOF" >> $GITHUB_OUTPUT
          cat changelog.md >> $GITHUB_OUTPUT
          echo "EOF" >> $GITHUB_OUTPUT
      
      - name: Create GitHub Release
        uses: softprops/action-gh-release@v1
        with:
          body_path: changelog.md
          draft: false
          prerelease: ${{ contains(github.ref, 'rc') || contains(github.ref, 'beta') || contains(github.ref, 'alpha') }}
      
      - name: Build and upload Python package
        run: |
          cd core && poetry build
          twine upload dist/*
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_TOKEN }}
      
      - name: Build Tauri app
        uses: tauri-apps/tauri-action@v0
        with:
          tagName: ${{ github.ref_name }}
          releaseName: "ARISE ${{ github.ref_name }}"
          releaseBodyPath: changelog.md
          args: --target universal-apple-darwin
      
      - name: Build Windows Tauri
        uses: tauri-apps/tauri-action@v0
        with:
          tagName: ${{ github.ref_name }}
          releaseName: "ARISE ${{ github.ref_name }}"
          releaseBodyPath: changelog.md
          args: --target x86_64-pc-windows-msvc
```

---

## 11. Development Workflows

### 11.1 Feature Development

```bash
# 1. Create feature branch
git checkout -b feature/amazing-feature

# 2. Make changes with tests
# Edit code...

# 3. Run pre-commit checks
pre-commit run --all-files

# 4. Run tests
make test

# 5. Commit with conventional commits
git add .
git commit -m "feat(task-engine): add parallel task execution

- Implement TaskQueue with priority support
- Add max_concurrent_tasks config
- Include integration tests"

# 6. Push and create PR
git push origin feature/amazing-feature
gh pr create --title "feat: parallel task execution" --body "..."

# 7. After review, squash merge
gh pr merge --squash
```

### 11.2 Hotfix Workflow

```bash
# 1. Create hotfix branch from main
git checkout main
git pull
git checkout -b hotfix/critical-bug

# 2. Fix with minimal changes
# Edit code...

# 3. Add regression test
# tests/unit/test_regression_critical_bug.py

# 4. Test thoroughly
make test

# 5. Commit
git commit -m "fix(security): prevent credential leak in audit logs

- Sanitize sensitive fields before logging
- Add test for credential redaction"

# 6. Push and create PR targeting main
git push origin hotfix/critical-bug
gh pr create --base main --title "fix: credential leak in audit logs"
```

### 11.3 Dependency Updates

```bash
# Python
cd core
poetry update --dry-run    # Check updates
poetry update              # Apply updates
make test                  # Verify

# Rust
cd src-tauri
cargo update --dry-run
cargo update
cargo test

# Node
cd src
pnpm outdated
pnpm update --latest
pnpm test
```

---

## 12. Troubleshooting Guide

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `ModuleNotFoundError` | Python path | `export PYTHONPATH=core:$PYTHONPATH` |
| `cargo build` fails | Missing system deps | Install `libwebkit2gtk-4.1-dev` (Linux) |
| `pnpm install` fails | Lockfile mismatch | `rm pnpm-lock.yaml && pnpm install` |
| Database connection refused | Postgres not ready | `docker-compose up -d && sleep 5` |
| Tauri dev doesn't start | Port conflict | Check ports 8000, 5173, 3000 free |
| TypeScript errors | Generated API out of sync | `python scripts/generate-api.py --all` |
| Tests flaky | Async timing | Add proper await/retries in tests |

### Debug Commands

```bash
# Check service health
curl http://localhost:8000/health
curl http://localhost:8000/metrics

# View logs
docker-compose logs -f postgres
docker-compose logs -f redis

# Database shell
docker-compose exec postgres psql -U postgres -d arise

# Redis CLI
docker-compose exec redis redis-cli

# Python REPL with context
cd core && poetry run python -c "
from core.task_engine import TaskEngine
import asyncio
engine = TaskEngine()
await engine.initialize()
# ... interactive debugging
"

# Rust REPL
cd src-tauri && cargo run --example debug_repl
```

---

## 13. Performance Benchmarks

```python
# scripts/benchmark.py
#!/usr/bin/env python
"""Performance benchmarks for ARISE components"""

import asyncio
import time
import statistics
import sys
sys.path.insert(0, "core")

from core.task_engine import TaskEngine
from core.model_router import ModelRouter
from core.memory import MemorySystem

class Benchmark:
    def __init__(self, name: str):
        self.name = name
        self.results = []
    
    async def run(self, func, iterations: int = 100, warmup: int = 10):
        # Warmup
        for _ in range(warmup):
            await func()
        
        # Benchmark
        for i in range(iterations):
            start = time.perf_counter()
            await func()
            elapsed = time.perf_counter() - start
            self.results.append(elapsed)
        
        self.print_results()
    
    def print_results(self):
        if not self.results:
            return
        
        print(f"\n{self.name} Benchmark Results:")
        print(f"  Iterations: {len(self.results)}")
        print(f"  Mean:       {statistics.mean(self.results)*1000:.2f}ms")
        print(f"  Median:     {statistics.median(self.results)*1000:.2f}ms")
        print(f"  Stdev:      {statistics.stdev(self.results)*1000:.2f}ms")
        print(f"  Min:        {min(self.results)*1000:.2f}ms")
        print(f"  Max:        {max(self.results)*1000:.2f}ms")
        print(f"  P95:        {statistics.quantiles(self.results, n=20)[18]*1000:.2f}ms")
        print(f"  P99:        {statistics.quantiles(self.results, n=100)[98]*1000:.2f}ms")
        print(f"  Throughput: {1/statistics.mean(self.results):.1f} ops/sec")

async def benchmark_task_submission():
    engine = TaskEngine()
    await engine.initialize()
    
    async def submit_task():
        task = Task(kind="shell.exec", payload={"command": "echo test"})
        await engine.submit(task)
    
    bench = Benchmark("Task Submission")
    await bench.run(submit_task, iterations=1000)
    await engine.shutdown()

async def benchmark_memory_store():
    memory = MemorySystem()
    await memory.initialize()
    
    async def store_memory():
        await memory.store(
            kind="semantic",
            content=f"Benchmark data {time.time()}",
            confidence=0.9
        )
    
    bench = Benchmark("Memory Store")
    await bench.run(store_memory, iterations=500)
    await memory.shutdown()

async def benchmark_model_router():
    router = ModelRouter()
    await router.initialize()
    
    async def route_request():
        await router.complete("coding", "Write a hello world function")
    
    bench = Benchmark("Model Router")
    await bench.run(route_request, iterations=50)
    await router.shutdown()

async def main():
    print("Running ARISE benchmarks...\n")
    
    await benchmark_task_submission()
    await benchmark_memory_store()
    await benchmark_model_router()
    
    print("\n✅ All benchmarks complete")

if __name__ == "__main__":
    asyncio.run(main())
```

---

*This developer experience guide provides all tooling needed for productive ARISE development. Run `make dev` to start, `make test` to verify, and `make build` to produce release artifacts.*