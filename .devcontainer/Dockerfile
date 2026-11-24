# ARISE Development Container Dockerfile
# Based on Python 3.11 with Node.js, Rust, and all development tools

ARG VARIANT=3.11
ARG NODE_VERSION=20
ARG RUST_VERSION=stable

FROM mcr.microsoft.com/devcontainers/python:${VARIANT}

# Install system dependencies
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y --no-install-recommends \
    # Build tools
    build-essential \
    cmake \
    pkg-config \
    # Libraries for Python packages
    libpq-dev \
    libssl-dev \
    libffi-dev \
    libsqlite3-dev \
    # Audio libraries for voice pipeline
    libasound2-dev \
    libportaudio2 \
    portaudio19-dev \
    # Computer vision libraries for automation
    libopencv-dev \
    libglib2.0-dev \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgl1-mesa-glx \
    # Tesseract OCR
    tesseract-ocr \
    tesseract-ocr-eng \
    # Utilities
    curl \
    wget \
    git \
    jq \
    unzip \
    # Cleanup
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js
ARG NODE_VERSION
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g pnpm @vitejs/plugin-react

# Install Rust
ARG RUST_VERSION
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain ${RUST_VERSION} \
    && . "$HOME/.cargo/env" \
    && rustup component add clippy rustfmt rust-analyzer \
    && cargo install tauri-cli --version "^2.0" \
    && cargo install cargo-audit cargo-tarpaulin cargo-watch

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 - \
    && ln -s /root/.local/bin/poetry /usr/local/bin/poetry

# Configure Poetry
ENV POETRY_VIRTUALENVS_IN_PROJECT=true
ENV POETRY_NO_INTERACTION=1

# Install Playwright browsers
RUN npx playwright install-deps chromium firefox webkit \
    && npx playwright install chromium firefox webkit

# Install Python development tools
RUN pip install --no-cache-dir \
    pre-commit \
    bandit \
    safety \
    pytest-xdist \
    pytest-benchmark \
    locust

# Set up working directory
WORKDIR /workspace

# Copy project files for dependency caching
COPY core/pyproject.toml core/poetry.lock* ./core/
COPY src/package.json src/package-lock.json* ./src/
COPY src-tauri/Cargo.toml src-tauri/Cargo.lock* ./src-tauri/

# Pre-install dependencies (will be updated in post-create)
RUN cd /workspace/core && poetry install --no-interaction --with voice,automation,memory,dev 2>/dev/null || true
RUN cd /workspace/src && npm ci 2>/dev/null || true
RUN cd /workspace/src-tauri && cargo fetch 2>/dev/null || true

# Set up non-root user
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=1000
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    && chown -R $USERNAME:$USERNAME /workspace

USER $USERNAME

# Add cargo to PATH
ENV PATH="/home/$USERNAME/.cargo/bin:${PATH}"

# Add poetry to PATH
ENV PATH="/home/$USERNAME/.local/bin:${PATH}"

# Default command
CMD ["sleep", "infinity"]