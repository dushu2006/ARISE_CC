# ARISE - Makefile
# Complete development commands for the ARISE Personal Digital Operator AI System

.PHONY: help dev dev-core dev-tauri dev-frontend test test-unit test-integration test-contract test-e2e test-coverage lint lint-python lint-rust lint-typescript format format-python format-rust format-typescript type-check type-check-python type-check-rust type-check-typescript build build-core build-tauri build-frontend db-migrate db-rollback db-reset generate-api benchmark profile security-scan clean

# Default target
help:
	@echo "ARISE - Personal Digital Operator AI System"
	@echo ""
	@echo "Development:"
	@echo "  make dev              - Start all services (core + tauri + frontend)"
	@echo "  make dev-core         - Start core FastAPI server only"
	@echo "  make dev-tauri        - Start Tauri dev mode"
	@echo "  make dev-frontend     - Start Vite dev server only"
	@echo ""
	@echo "Testing:"
	@echo "  make test             - Run all tests"
	@echo "  make test-unit        - Run unit tests"
	@echo "  make test-integration - Run integration tests"
	@echo "  make test-contract    - Run contract tests"
	@echo "  make test-e2e         - Run E2E tests"
	@echo "  make test-coverage    - Run tests with coverage report"
	@echo ""
	@echo "Linting & Formatting:"
	@echo "  make lint             - Run all linters"
	@echo "  make lint-python      - Run ruff + mypy"
	@echo "  make lint-rust        - Run cargo clippy + cargo fmt --check"
	@echo "  make lint-typescript  - Run eslint + tsc --noEmit"
	@echo "  make format           - Format all code"
	@echo "  make format-python    - Run ruff format + black"
	@echo "  make format-rust      - Run cargo fmt"
	@echo "  make format-typescript- Run prettier"
	@echo ""
	@echo "Type Checking:"
	@echo "  make type-check       - Run all type checkers"
	@echo "  make type-check-python- Run mypy"
	@echo "  make type-check-rust  - Run cargo check"
	@echo "  make type-check-typescript - Run tsc --noEmit"
	@echo ""
	@echo "Building:"
	@echo "  make build            - Build all artifacts"
	@echo "  make build-core       - Build core (install deps, check types)"
	@echo "  make build-tauri      - Build Tauri app"
	@echo "  make build-frontend   - Build frontend"
	@echo ""
	@echo "Database:"
	@echo "  make db-migrate       - Run database migrations"
	@echo "  make db-rollback      - Rollback last migration"
	@echo "  make db-reset         - Reset database (drop + migrate)"
	@echo ""
	@echo "Code Generation:"
	@echo "  make generate-api     - Generate TypeScript API client from OpenAPI"
	@echo ""
	@echo "Performance & Profiling:"
	@echo "  make benchmark        - Run benchmarks"
	@echo "  make profile          - Run profiling"
	@echo ""
	@echo "Security:"
	@echo "  make security-scan    - Run security scans"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean            - Clean build artifacts"

# =============================================================================
# Development
# =============================================================================

dev:
	@echo "Starting all services..."
	@concurrently -k -n "CORE,TAURI,FRONTEND" -c "green,blue,yellow" \
		"make dev-core" \
		"make dev-tauri" \
		"make dev-frontend"

dev-core:
	@echo "Starting core FastAPI server..."
	@cd core && poetry run uvicorn core.runtime.main:app --reload --host 0.0.0.0 --port 8000

dev-tauri:
	@echo "Starting Tauri dev mode..."
	@cd src-tauri && cargo tauri dev

dev-frontend:
	@echo "Starting Vite dev server..."
	@cd src && npm run dev

# =============================================================================
# Testing
# =============================================================================

test: test-unit test-integration test-contract test-e2e

test-unit:
	@echo "Running unit tests..."
	@cd core && poetry run pytest tests/unit -v --tb=short -x
	@cd src-tauri && cargo test --lib
	@cd src && npm run test:run

test-integration:
	@echo "Running integration tests..."
	@cd core && poetry run pytest tests/integration -v --tb=short -x
	@cd src-tauri && cargo test --test integration

test-contract:
	@echo "Running contract tests..."
	@cd core && poetry run pytest tests/contract -v --tb=short -x
	@cd src && npm run test:run -- tests/contract

test-e2e:
	@echo "Running E2E tests..."
	@cd src && npm run test:run -- tests/e2e

test-coverage:
	@echo "Running tests with coverage..."
	@cd core && poetry run pytest tests/unit tests/integration --cov=core --cov-report=html --cov-report=term-missing --cov-fail-under=80
	@cd src-tauri && cargo tarpaulin --out Html --output-dir coverage
	@cd src && npm run test:coverage

# =============================================================================
# Linting
# =============================================================================

lint: lint-python lint-rust lint-typescript

lint-python:
	@echo "Linting Python..."
	@cd core && poetry run ruff check . && poetry run mypy .

lint-rust:
	@echo "Linting Rust..."
	@cd src-tauri && cargo clippy -- -D warnings && cargo fmt --check

lint-typescript:
	@echo "Linting TypeScript..."
	@cd src && npm run lint && npm run type-check

# =============================================================================
# Formatting
# =============================================================================

format: format-python format-rust format-typescript

format-python:
	@echo "Formatting Python..."
	@cd core && poetry run ruff format . && poetry run black .

format-rust:
	@echo "Formatting Rust..."
	@cd src-tauri && cargo fmt

format-typescript:
	@echo "Formatting TypeScript..."
	@cd src && npm run format

# =============================================================================
# Type Checking
# =============================================================================

type-check: type-check-python type-check-rust type-check-typescript

type-check-python:
	@echo "Type checking Python..."
	@cd core && poetry run mypy .

type-check-rust:
	@echo "Type checking Rust..."
	@cd src-tauri && cargo check

type-check-typescript:
	@echo "Type checking TypeScript..."
	@cd src && npm run type-check

# =============================================================================
# Building
# =============================================================================

build: build-core build-tauri build-frontend

build-core:
	@echo "Building core..."
	@cd core && poetry install --no-interaction && poetry run mypy . && poetry run ruff check .

build-tauri:
	@echo "Building Tauri app..."
	@cd src-tauri && cargo tauri build

build-frontend:
	@echo "Building frontend..."
	@cd src && npm run build

# =============================================================================
# Database
# =============================================================================

db-migrate:
	@echo "Running database migrations..."
	@cd core && poetry run alembic upgrade head

db-rollback:
	@echo "Rolling back last migration..."
	@cd core && poetry run alembic downgrade -1

db-reset:
	@echo "Resetting database..."
	@cd core && poetry run alembic downgrade base && poetry run alembic upgrade head

# =============================================================================
# Code Generation
# =============================================================================

generate-api:
	@echo "Generating TypeScript API client from OpenAPI..."
	@cd src && npx openapi-typescript-codegen -i http://localhost:8000/openapi.json -o src/services/api/generated -c axios

# =============================================================================
# Performance & Profiling
# =============================================================================

benchmark:
	@echo "Running benchmarks..."
	@cd core && poetry run pytest tests/performance -v --tb=short
	@cd src && npm run test:run -- tests/performance

profile:
	@echo "Running profiling..."
	@cd core && poetry run python -m cProfile -o profile.stats scripts/profile.py

# =============================================================================
# Security
# =============================================================================

security-scan:
	@echo "Running security scans..."
	@cd core && poetry run bandit -r . -f json -o bandit-report.json && poetry run safety check --json
	@cd src-tauri && cargo audit
	@cd src && npm audit --json

# =============================================================================
# Clean
# =============================================================================

clean:
	@echo "Cleaning build artifacts..."
	@cd core && rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache htmlcov coverage .coverage
	@cd src-tauri && cargo clean
	@cd src && rm -rf dist node_modules/.vite coverage
	@rm -rf docker/build