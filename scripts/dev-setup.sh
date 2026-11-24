#!/bin/bash
# ARISE - One-Command Development Setup Script
# This script sets up the complete development environment for ARISE

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

log_info "Starting ARISE development environment setup..."
log_info "Project root: $PROJECT_ROOT"

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check version
check_version() {
    local cmd="$1"
    local min_version="$2"
    local version_output="$3"
    # Simple version check - in practice you'd want more robust parsing
    log_info "$cmd version: $version_output"
}

# =============================================================================
# Prerequisites Check
# =============================================================================

log_info "Checking prerequisites..."

# Check for required tools
REQUIRED_TOOLS=("git" "curl" "python3" "node" "npm" "cargo" "poetry" "docker" "kubectl" "helm")
MISSING_TOOLS=()

for tool in "${REQUIRED_TOOLS[@]}"; do
    if command_exists "$tool"; then
        log_success "$tool found"
    else
        log_warning "$tool not found"
        MISSING_TOOLS+=("$tool")
    fi
done

if [ ${#MISSING_TOOLS[@]} -gt 0 ]; then
    log_warning "Some tools are missing: ${MISSING_TOOLS[*]}"
    log_info "Please install missing tools before continuing."
    log_info "On Windows, consider using winget, choco, or scoop."
    log_info "On macOS, use brew. On Linux, use your package manager."

    # Try to install some common ones
    if command_exists "winget"; then
        log_info "Windows detected with winget. Installing missing tools..."
        for tool in "${MISSING_TOOLS[@]}"; do
            case $tool in
                "node") winget install OpenJS.NodeJS ;;
                "python3") winget install Python.Python.3.11 ;;
                "poetry") winget install Python.Poetry ;;
                "cargo") winget install Rustlang.Rust ;;
                "docker") winget install Docker.DockerDesktop ;;
                "kubectl") winget install Kubernetes.kubectl ;;
                "helm") winget install Helm.Helm ;;
            esac
        done
    fi
fi

# =============================================================================
# Python Environment Setup
# =============================================================================

log_info "Setting up Python environment..."

cd "$PROJECT_ROOT/core"

if command_exists "poetry"; then
    log_info "Installing Python dependencies with Poetry..."
    poetry config virtualenvs.in-project true
    poetry install --no-interaction --with voice,automation,memory,dev
    log_success "Python dependencies installed"
else
    log_error "Poetry not found. Please install Poetry first."
    exit 1
fi

# =============================================================================
# Rust Environment Setup
# =============================================================================

log_info "Setting up Rust environment..."

cd "$PROJECT_ROOT/src-tauri"

if command_exists "cargo"; then
    log_info "Installing Rust dependencies..."
    cargo fetch
    log_success "Rust dependencies fetched"

    # Install Tauri CLI if not present
    if ! command_exists "cargo-tauri"; then
        log_info "Installing Tauri CLI..."
        cargo install tauri-cli --version "^2.0"
    fi
else
    log_error "Cargo not found. Please install Rust first."
    exit 1
fi

# =============================================================================
# Node.js Environment Setup
# =============================================================================

log_info "Setting up Node.js environment..."

cd "$PROJECT_ROOT/src"

if command_exists "npm"; then
    log_info "Installing Node.js dependencies..."
    npm ci
    log_success "Node.js dependencies installed"

    # Install Playwright browsers
    log_info "Installing Playwright browsers..."
    npx playwright install chromium firefox webkit
    log_success "Playwright browsers installed"
else
    log_error "npm not found. Please install Node.js first."
    exit 1
fi

# =============================================================================
# Docker Setup
# =============================================================================

log_info "Setting up Docker..."

cd "$PROJECT_ROOT"

if command_exists "docker"; then
    log_info "Building Docker images..."
    docker compose -f docker/docker-compose.yml build
    log_success "Docker images built"
else
    log_warning "Docker not found. Skipping Docker setup."
fi

# =============================================================================
# Database Setup
# =============================================================================

log_info "Setting up database..."

cd "$PROJECT_ROOT/core"

# Start PostgreSQL and Redis via docker-compose if available
if command_exists "docker" && docker compose -f "$PROJECT_ROOT/docker/docker-compose.yml" ps postgres 2>/dev/null | grep -q "Up"; then
    log_info "PostgreSQL already running"
else
    log_info "Starting PostgreSQL and Redis..."
    docker compose -f "$PROJECT_ROOT/docker/docker-compose.yml" up -d postgres redis
    sleep 5
fi

# Run migrations
log_info "Running database migrations..."
poetry run alembic upgrade head
log_success "Database migrations applied"

# =============================================================================
# Configuration Files
# =============================================================================

log_info "Setting up configuration files..."

cd "$PROJECT_ROOT"

# Create config files from examples if they don't exist
if [ ! -f "config/config.local.yaml" ]; then
    if [ -f "config/config.local.yaml.example" ]; then
        cp config/config.local.yaml.example config/config.local.yaml
        log_info "Created config.local.yaml from example"
    else
        log_warning "config.local.yaml.example not found, skipping"
    fi
fi

# Create .env file if it doesn't exist
if [ ! -f "core/.env" ]; then
    cat > core/.env << 'EOF'
# ARISE Core Environment Variables
# Copy this file and fill in your values

# Environment
ENVIRONMENT=development
LOG_LEVEL=DEBUG

# Database
DATABASE_URL=postgresql+asyncpg://arise:arise@localhost:5432/arise
REDIS_URL=redis://localhost:6379/0

# Model Providers (add your API keys)
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=

# Voice
PORCUPINE_ACCESS_KEY=
ELEVENLABS_API_KEY=

# Security
MASTER_ENCRYPTION_KEY=
VAULT_ADDR=
VAULT_TOKEN=

# Telemetry
OTEL_EXPORTER_OTLP_ENDPOINT=
EOF
    log_info "Created core/.env template - please fill in your API keys"
fi

# =============================================================================
# Pre-commit Hooks
# =============================================================================

log_info "Setting up pre-commit hooks..."

cd "$PROJECT_ROOT/core"

if command_exists "pre-commit"; then
    poetry run pre-commit install
    poetry run pre-commit install --hook-type commit-msg
    log_success "Pre-commit hooks installed"
else
    log_warning "pre-commit not found, skipping hook installation"
fi

# =============================================================================
# VS Code Setup
# =============================================================================

log_info "Setting up VS Code configuration..."

cd "$PROJECT_ROOT"

if command_exists "code"; then
    # Install recommended extensions
    EXTENSIONS=(
        "rust-lang.rust-analyzer"
        "ms-python.python"
        "ms-python.black-formatter"
        "charliermarsh.ruff"
        "ms-azuretools.vscode-docker"
        "redhat.vscode-yaml"
        "tamasfe.even-better-toml"
        "esbenp.prettier-vscode"
        "dbaeumer.vscode-eslint"
        "bradlc.vscode-tailwindcss"
        "formulahendry.code-runner"
        "ms-vscode.vscode-typescript-next"
        "vadimcn.vscode-lldb"
    )

    for ext in "${EXTENSIONS[@]}"; do
        code --install-extension "$ext" --force 2>/dev/null || true
    done
    log_success "VS Code extensions installed"
else
    log_info "VS Code CLI not found, skipping extension installation"
fi

# =============================================================================
# Git Hooks
# =============================================================================

log_info "Setting up git configuration..."

cd "$PROJECT_ROOT"

# Set up git hooks directory
git config core.hooksPath .githooks 2>/dev/null || true

# Create commit-msg hook for conventional commits
mkdir -p .githooks
cat > .githooks/commit-msg << 'EOF'
#!/bin/bash
# Conventional commit message validation
commit_msg=$(cat "$1")
pattern='^(feat|fix|docs|style|refactor|perf|test|chore|build|ci|revert)(\(.+\))?: .+'

if ! echo "$commit_msg" | grep -qE "$pattern"; then
    echo "Error: Commit message does not follow conventional commit format"
    echo "Format: <type>(<scope>): <description>"
    echo "Types: feat, fix, docs, style, refactor, perf, test, chore, build, ci, revert"
    exit 1
fi
EOF
chmod +x .githooks/commit-msg

log_success "Git hooks configured"

# =============================================================================
# Verification
# =============================================================================

log_info "Running verification checks..."

cd "$PROJECT_ROOT/core"

# Check Python syntax
log_info "Checking Python syntax..."
poetry run python -m py_compile $(find . -name "*.py" | head -20) 2>/dev/null || true

cd "$PROJECT_ROOT/src-tauri"

# Check Rust compiles
log_info "Checking Rust compilation..."
cargo check --quiet 2>&1 | tail -5

cd "$PROJECT_ROOT/src"

# Check TypeScript compiles
log_info "Checking TypeScript compilation..."
npm run type-check 2>&1 | tail -5

# =============================================================================
# Summary
# =============================================================================

log_success "=========================================="
log_success "ARISE Development Environment Setup Complete!"
log_success "=========================================="
echo ""
log_info "Next steps:"
echo "  1. Fill in your API keys in core/.env"
echo "  2. Run 'make dev' to start all services"
echo "  3. Open http://localhost:8000/docs for API documentation"
echo "  4. Open http://localhost:5173 for the frontend"
echo ""
log_info "Useful commands:"
echo "  make dev              - Start all services"
echo "  make test             - Run all tests"
echo "  make lint             - Run all linters"
echo "  make format           - Format all code"
echo "  make build            - Build all artifacts"
echo ""
log_info "Documentation:"
echo "  - Architecture: docs/"
echo "  - API Spec: http://localhost:8000/openapi.json"
echo "  - Design Docs: PREWORK/*.md"
echo ""
log_success "Happy coding! 🚀"