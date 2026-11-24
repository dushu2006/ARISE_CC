#!/bin/bash
# Post-create script for ARISE dev container

set -euo pipefail

echo "🔧 Running post-create setup..."

# Navigate to workspace
cd /workspace

# Install Python dependencies
echo "📦 Installing Python dependencies..."
cd /workspace/core
poetry install --no-interaction --with voice,automation,memory,dev

# Install pre-commit hooks
echo "🪝 Installing pre-commit hooks..."
poetry run pre-commit install
poetry run pre-commit install --hook-type commit-msg

# Install Node.js dependencies
echo "📦 Installing Node.js dependencies..."
cd /workspace/src
npm ci

# Fetch Rust dependencies
echo "📦 Fetching Rust dependencies..."
cd /workspace/src-tauri
cargo fetch

# Build Tauri to verify setup
echo "🔨 Building Tauri (verification)..."
cargo build 2>&1 | tail -10

# Run database migrations if database is available
echo "🗄️ Checking database..."
cd /workspace/core
if poetry run python -c "import asyncpg; asyncpg.connect('postgresql://arise:arise@localhost:5432/arise')" 2>/dev/null; then
    echo "📊 Running database migrations..."
    poetry run alembic upgrade head
else
    echo "⚠️ Database not available, skipping migrations"
fi

echo "✅ Post-create setup complete!"
echo ""
echo "🚀 To start development:"
echo "   make dev"
echo ""
echo "📚 Useful commands:"
echo "   make test          - Run all tests"
echo "   make lint          - Run all linters"
echo "   make format        - Format all code"
echo "   make build         - Build all artifacts"