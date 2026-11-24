# ARISE — System Integration & Deployment Guide

## Overview

Complete deployment and integration guide for ARISE across development, staging, and production environments. Covers Docker containers, systemd services, Windows installation, Kubernetes orchestration, and cross-component integration patterns.

---

## 1. Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DEPLOYMENT TOPOLOGY                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐               │
│  │   CLIENT     │     │   TAURI APP  │     │  WEB UI      │               │
│  │  (React)     │────▶│  (Rust)      │◀───▶│  (Optional)  │               │
│  │  Port: 5173  │     │  Native      │     │  Port: 3000  │               │
│  └──────────────┘     └──────┬───────┘     └──────────────┘               │
│                             │                                             │
│                    ┌────────┴────────┐                                    │
│                    │  TAURI COMMANDS │                                    │
│                    │  (IPC/RPC)      │                                    │
│                    └────────┬────────┘                                    │
│                             │                                             │
│  ┌──────────────────────────┼──────────────────────────────────────┐     │
│  │                    PYTHON CORE SERVICE (FastAPI)                │     │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │     │
│  │  │ Task    │ │ Model   │ │ Policy  │ │ Memory  │ │ Voice   │   │     │
│  │  │ Engine  │ │ Router  │ │ Engine  │ │ System  │ │ Pipeline│   │     │
│  │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘   │     │
│  │       │           │           │           │           │         │     │
│  │       └───────────┼───────────┼───────────┼───────────┘         │     │
│  │                   ▼           ▼           ▼                     │     │
│  │            ┌─────────────────────────────────┐                 │     │
│  │            │      EVENT BUS (Redis Streams)  │                 │     │
│  │            └─────────────────────────────────┘                 │     │
│  │                   │           │           │                     │     │
│  │       ┌───────────┘           │           └───────────┐       │     │
│  │       ▼                       ▼                       ▼       │     │
│  │  ┌─────────┐           ┌─────────┐            ┌─────────┐   │     │
│  │  │PostgreSQL│          │  Redis  │            │ SQLite  │   │     │
│  │  │(Primary) │          │(Cache/  │            │(Events/ │   │     │
│  │  │          │          │ Streams)│            │ Config) │   │     │
│  │  └─────────┘           └─────────┘            └─────────┘   │     │
│  └────────────────────────────────────────────────────────────────┘     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Docker Deployment

### 2.1 Dockerfile for Python Core

```dockerfile
# docker/Dockerfile.core
FROM python:3.11-slim-bookworm AS base

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY core/pyproject.toml core/poetry.lock ./
RUN pip install --no-cache-dir poetry==1.8.0 \
    && poetry config virtualenvs.create false \
    && poetry install --no-dev --no-interaction --no-ansi

# Copy application code
COPY core/ ./core/
COPY scripts/ ./scripts/

# Create non-root user
RUN useradd --create-home --shell /bin/bash arise \
    && chown -R arise:arise /app
USER arise

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose ports
EXPOSE 8000

# Default command
CMD ["uvicorn", "core.runtime.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 2.2 Dockerfile for Tauri (Multi-stage)

```dockerfile
# docker/Dockerfile.tauri
# Stage 1: Build Rust
FROM rust:1.78-bookworm AS rust-builder

WORKDIR /app
COPY src-tauri/Cargo.toml src-tauri/Cargo.lock ./
COPY src-tauri/src ./src

# Build release
RUN cargo build --release --bin arise

# Stage 2: Build Frontend
FROM node:20-bookworm-slim AS frontend-builder

WORKDIR /app
COPY src/package.json src/pnpm-lock.yaml ./
RUN npm install -g pnpm && pnpm install --frozen-lockfile
COPY src/ ./
RUN pnpm build

# Stage 3: Runtime
FROM debian:bookworm-slim AS runtime

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libwebkit2gtk-4.1-0 \
    libayatana-appindicator3-1 \
    librsvg2-common \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy binaries
COPY --from=rust-builder /app/target/release/arise /usr/local/bin/arise
COPY --from=frontend-builder /app/dist /app/webview

# Create user
RUN useradd --create-home --shell /bin/bash arise \
    && chown -R arise:arise /app
USER arise

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

EXPOSE 8080

ENTRYPOINT ["arise"]
```

### 2.3 Docker Compose for Local Development

```yaml
# docker/docker-compose.yml
version: '3.9'

services:
  # Primary database
  postgres:
    image: postgres:16-alpine
    container_name: arise-postgres
    environment:
      POSTGRES_DB: arise
      POSTGRES_USER: arise
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-arise_dev}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init-sql:/docker-entrypoint-initdb.d
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U arise -d arise"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - arise-network

  # Redis for caching, sessions, event bus
  redis:
    image: redis:7-alpine
    container_name: arise-redis
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - arise-network

  # Python Core API
  core:
    build:
      context: ..
      dockerfile: docker/Dockerfile.core
    container_name: arise-core
    environment:
      - ARISE_ENV=development
      - DATABASE_URL=postgresql+asyncpg://arise:${POSTGRES_PASSWORD:-arise_dev}@postgres:5432/arise
      - REDIS_URL=redis://redis:6379/0
      - ARISE_LOG_LEVEL=DEBUG
      - PYTHONPATH=/app
    volumes:
      - ../core:/app/core:ro
      - ../scripts:/app/scripts:ro
      - arise_data:/app/data
      - arise_logs:/app/logs
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - arise-network
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '2'
        reservations:
          memory: 512M
          cpus: '0.5'

  # Tauri App (development mode - not containerized usually)
  # Included for reference
  # tauri:
  #   build:
  #     context: ..
  #     dockerfile: docker/Dockerfile.tauri
  #   container_name: arise-tauri
  #   environment:
  #     - ARISE_ENV=development
  #     - WEBVIEW_URL=http://core:8000
  #   volumes:
  #     - ../src-tauri:/app/src-tauri:ro
  #     - ../src/dist:/app/webview:ro
  #     - arise_data:/app/data
  #   ports:
  #     - "8080:8080"
  #   depends_on:
  #     - core
  #   networks:
  #     - arise-network

  # Frontend dev server
  frontend:
    build:
      context: ..
      dockerfile: docker/Dockerfile.frontend
    container_name: arise-frontend
    environment:
      - VITE_API_URL=http://localhost:8000
      - VITE_WS_URL=ws://localhost:8000/ws
    volumes:
      - ../src:/app/src:ro
      - /app/src/node_modules
    ports:
      - "5173:5173"
    depends_on:
      - core
    networks:
      - arise-network

  # Monitoring (optional)
  prometheus:
    image: prom/prometheus:v2.52.0
    container_name: arise-prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    networks:
      - arise-network

  grafana:
    image: grafana/grafana:10.4.0
    container_name: arise-grafana
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD:-admin}
    volumes:
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./grafana/datasources:/etc/grafana/provisioning/datasources
      - grafana_data:/var/lib/grafana
    ports:
      - "3000:3000"
    depends_on:
      - prometheus
    networks:
      - arise-network

volumes:
  postgres_data:
  redis_data:
  arise_data:
  arise_logs:
  prometheus_data:
  grafana_data:

networks:
  arise-network:
    driver: bridge
```

### 2.4 Docker Compose for Production

```yaml
# docker/docker-compose.prod.yml
version: '3.9'

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: arise
      POSTGRES_USER: arise
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    secrets:
      - postgres_password
    networks:
      - arise-internal
    deploy:
      resources:
        limits:
          memory: 4G
          cpus: '2'

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    networks:
      - arise-internal
    secrets:
      - redis_password
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '1'

  core:
    image: arise/core:${VERSION:-latest}
    environment:
      - ARISE_ENV=production
      - DATABASE_URL=postgresql+asyncpg://arise:@postgres:5432/arise
      - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
      - ARISE_LOG_LEVEL=INFO
    secrets:
      - postgres_password
      - redis_password
      - openai_api_key
      - anthropic_api_key
    networks:
      - arise-internal
      - arise-external
    deploy:
      replicas: 3
      resources:
        limits:
          memory: 2G
          cpus: '2'
        reservations:
          memory: 1G
          cpus: '1'
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
      update_config:
        parallelism: 1
        delay: 10s
        order: start-first

  nginx:
    image: nginx:alpine
    volumes:
      - ./nginx.prod.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    ports:
      - "80:80"
      - "443:443"
    networks:
      - arise-external
    depends_on:
      - core
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: '0.5'

secrets:
  postgres_password:
    external: true
  redis_password:
    external: true
  openai_api_key:
    external: true
  anthropic_api_key:
    external: true

networks:
  arise-internal:
    driver: overlay
    internal: true
  arise-external:
    driver: overlay

volumes:
  postgres_data:
  redis_data:
```

---

## 3. Kubernetes Deployment

### 3.1 Namespace & ConfigMap

```yaml
# k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: arise
  labels:
    name: arise
    environment: production
```

```yaml
# k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: arise-config
  namespace: arise
data:
  ARISE_ENV: "production"
  ARISE_LOG_LEVEL: "INFO"
  ARISE_LOG_FORMAT: "json"
  DATABASE_HOST: "postgres.arise.svc.cluster.local"
  DATABASE_PORT: "5432"
  REDIS_HOST: "redis.arise.svc.cluster.local"
  REDIS_PORT: "6379"
  MODEL_ROUTER_DEFAULT_PROVIDER: "openai"
  TASK_ENGINE_MAX_CONCURRENT: "20"
  POLICY_ENGINE_AUDIT_ENABLED: "true"
```

### 3.2 Secrets

```yaml
# k8s/secrets.yaml
apiVersion: v1
kind: Secret
metadata:
  name: arise-secrets
  namespace: arise
type: Opaque
stringData:
  DATABASE_PASSWORD: "changeme"
  REDIS_PASSWORD: "changeme"
  OPENAI_API_KEY: "sk-..."
  ANTHROPIC_API_KEY: "sk-..."
  GEMINI_API_KEY: "..."
  VAULT_TOKEN: "hvs...."
```

### 3.3 PostgreSQL StatefulSet

```yaml
# k8s/postgres.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: arise
spec:
  serviceName: postgres
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:16-alpine
        env:
        - name: POSTGRES_DB
          value: arise
        - name: POSTGRES_USER
          value: arise
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: arise-secrets
              key: DATABASE_PASSWORD
        ports:
        - containerPort: 5432
        volumeMounts:
        - name: postgres-data
          mountPath: /var/lib/postgresql/data
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
        livenessProbe:
          exec:
            command: ["pg_isready", "-U", "arise", "-d", "arise"]
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          exec:
            command: ["pg_isready", "-U", "arise", "-d", "arise"]
          initialDelaySeconds: 5
          periodSeconds: 5
  volumeClaimTemplates:
  - metadata:
      name: postgres-data
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: fast-ssd
      resources:
        requests:
          storage: 50Gi
---
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: arise
spec:
  ports:
  - port: 5432
    targetPort: 5432
  selector:
    app: postgres
  clusterIP: None
```

### 3.4 Redis Deployment

```yaml
# k8s/redis.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  namespace: arise
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        command: ["redis-server", "--appendonly", "yes", "--maxmemory", "512mb", "--maxmemory-policy", "allkeys-lru", "--requirepass", "$(REDIS_PASSWORD)"]
        env:
        - name: REDIS_PASSWORD
          valueFrom:
            secretKeyRef:
              name: arise-secrets
              key: REDIS_PASSWORD
        ports:
        - containerPort: 6379
        volumeMounts:
        - name: redis-data
          mountPath: /data
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        livenessProbe:
          exec:
            command: ["redis-cli", "-a", "$(REDIS_PASSWORD)", "ping"]
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          exec:
            command: ["redis-cli", "-a", "$(REDIS_PASSWORD)", "ping"]
          initialDelaySeconds: 5
          periodSeconds: 5
      volumes:
      - name: redis-data
        emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: arise
spec:
  ports:
  - port: 6379
    targetPort: 6379
  selector:
    app: redis
```

### 3.5 Core API Deployment

```yaml
# k8s/core.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: arise-core
  namespace: arise
spec:
  replicas: 3
  selector:
    matchLabels:
      app: arise-core
  template:
    metadata:
      labels:
        app: arise-core
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8000"
        prometheus.io/path: "/metrics"
    spec:
      containers:
      - name: core
        image: arise/core:v1.0.0
        imagePullPolicy: Always
        envFrom:
        - configMapRef:
            name: arise-config
        - secretRef:
            name: arise-secrets
        ports:
        - containerPort: 8000
          name: http
        - containerPort: 9090
          name: metrics
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
        volumeMounts:
        - name: data
          mountPath: /app/data
        - name: logs
          mountPath: /app/logs
      volumes:
      - name: data
        emptyDir: {}
      - name: logs
        emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: arise-core
  namespace: arise
spec:
  ports:
  - name: http
    port: 8000
    targetPort: 8000
  - name: metrics
    port: 9090
    targetPort: 9090
  selector:
    app: arise-core
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: arise-core-hpa
  namespace: arise
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: arise-core
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 10
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
      - type: Percent
        value: 100
        periodSeconds: 15
      - type: Pods
        value: 4
        periodSeconds: 15
      selectPolicy: Max
```

### 3.6 Ingress

```yaml
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: arise-ingress
  namespace: arise
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/rate-limit: "100"
    nginx.ingress.kubernetes.io/proxy-body-size: "50m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "300"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "300"
    nginx.ingress.kubernetes.io/websocket-services: "arise-core"
spec:
  tls:
  - hosts:
    - api.arise.ai
    - app.arise.ai
    secretName: arise-tls
  rules:
  - host: api.arise.ai
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: arise-core
            port:
              number: 8000
  - host: app.arise.ai
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: arise-frontend
            port:
              number: 80
```

---

## 4. Systemd Service (Linux)

### 4.1 Core Service

```ini
# /etc/systemd/system/arise-core.service
[Unit]
Description=ARISE Core API Service
Documentation=https://github.com/arise/arise
After=network.target postgresql.service redis.service
Wants=postgresql.service redis.service

[Service]
Type=notify
User=arise
Group=arise
WorkingDirectory=/opt/arise
Environment=ARISE_ENV=production
Environment=PYTHONPATH=/opt/arise/core
EnvironmentFile=-/etc/arise/environment
ExecStart=/opt/arise/.venv/bin/uvicorn core.runtime.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4 \
    --loop uvloop \
    --http httptools \
    --log-config /opt/arise/config/logging.json
ExecReload=/bin/kill -HUP $MAINPID
KillMode=mixed
TimeoutStopSec=30
Restart=on-failure
RestartSec=5
StartLimitIntervalSec=60
StartLimitBurst=3

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/arise/data /opt/arise/logs /opt/arise/tmp
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictRealtime=true
RestrictSUIDSGID=true
LockPersonality=true
MemoryDenyWriteExecute=true

# Resource limits
LimitNOFILE=65536
LimitNPROC=4096
MemoryMax=4G
CPUQuota=200%

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=arise-core

[Install]
WantedBy=multi-user.target
```

### 4.2 Environment File

```ini
# /etc/arise/environment
# Database
DATABASE_URL=postgresql+asyncpg://arise:password@localhost:5432/arise

# Redis
REDIS_URL=redis://localhost:6379/0

# Model Providers
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-...
GEMINI_API_KEY=...

# Security
ARISE_SECURITY_VAULT_URL=https://vault.company.com
ARISE_SECURITY_VAULT_TOKEN=hvs....

# Telemetry
ARISE_TELEMETRY_ENABLED=false
```

### 4.3 Log Rotation

```ini
# /etc/logrotate.d/arise
/opt/arise/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 0640 arise arise
    sharedscripts
    postrotate
        systemctl reload arise-core > /dev/null 2>&1 || true
    endscript
}

/var/log/arise/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 0640 arise arise
}
```

---

## 5. Windows Installation

### 5.1 NSIS Installer Script

```nsis
; installer/arise-installer.nsi
!define APP_NAME "ARISE"
!define APP_VERSION "1.0.0"
!define APP_PUBLISHER "ARISE Team"
!define APP_URL "https://arise.ai"
!define APP_EXE "arise.exe"

RequestExecutionLevel admin
InstallDir "$PROGRAMFILES64\${APP_NAME}"
InstallDirRegKey HKLM "Software\${APP_NAME}" "InstallDir"

Page directory
Page instfiles

UninstPage uninstConfirm
UninstPage instfiles

Section "Main Application" SEC_MAIN
    SetOutPath "$INSTDIR"
    File /r "dist\*"
    
    ; Create shortcuts
    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
    CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
    
    ; Register uninstaller
    WriteUninstaller "$INSTDIR\uninstall.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
        "DisplayName" "${APP_NAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
        "UninstallString" "$INSTDIR\uninstall.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
        "DisplayVersion" "${APP_VERSION}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
        "Publisher" "${APP_PUBLISHER}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
        "URLInfoAbout" "${APP_URL}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
        "InstallLocation" "$INSTDIR"
    
    ; Register as default handler for arise:// protocol
    WriteRegStr HKCR "arise" "" "URL:ARISE Protocol"
    WriteRegStr HKCR "arise" "URL Protocol" ""
    WriteRegStr HKCR "arise\shell\open\command" "" '"$INSTDIR\${APP_EXE}" "%1"'
    
    ; Add to PATH
    EnVar::AddToSystemPath "$INSTDIR"
SectionEnd

Section "Python Core" SEC_PYTHON
    SectionIn RO
    ; Python embedded runtime
    File /r "python-embed\*"
    ; Install dependencies
    ExecWait '"$INSTDIR\python\python.exe" -m pip install --no-index -r "$INSTDIR\requirements.txt"'
SectionEnd

Section -Post
    WriteUninstaller "$INSTDIR\uninstall.exe"
    
    ; Configure Windows Firewall
    ExecWait 'netsh advfirewall firewall add rule name="ARISE Core API" dir=in action=allow protocol=TCP localport=8000'
    ExecWait 'netsh advfirewall firewall add rule name="ARISE WebSocket" dir=in action=allow protocol=TCP localport=8001'
    
    ; Start service
    ExecWait 'sc create "ARISE Core" binPath= "$INSTDIR\arise-core.exe --service" start= auto'
    ExecWait 'sc start "ARISE Core"'
SectionEnd

Section "Uninstall"
    ; Remove firewall rules
    ExecWait 'netsh advfirewall firewall delete rule name="ARISE Core API"'
    ExecWait 'netsh advfirewall firewall delete rule name="ARISE WebSocket"'
    
    ; Stop and remove service
    ExecWait 'sc stop "ARISE Core"'
    ExecWait 'sc delete "ARISE Core"'
    
    ; Remove protocol handler
    DeleteRegKey HKCR "arise"
    
    ; Remove from PATH
    EnVar::RemoveFromSystemPath "$INSTDIR"
    
    ; Clean up
    RMDir /r "$INSTDIR"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
    DeleteRegKey HKLM "Software\${APP_NAME}"
SectionEnd
```

### 5.2 Windows Service (Rust)

```rust
// src-tauri/src/windows_service.rs
use windows_service::{
    service::{ServiceControl, ServiceControlAccept, ServiceExitCode, ServiceState, ServiceStatus, ServiceType},
    service_control_handler::{self, ServiceControlHandlerResult},
    service_dispatcher,
    Result,
};
use std::ffi::OsString;
use std::sync::{Arc, Mutex};
use std::time::Duration;

const SERVICE_NAME: &str = "ARISECore";
const SERVICE_DISPLAY_NAME: &str = "ARISE Core Service";

pub fn run_service() -> Result<()> {
    service_dispatcher::start(SERVICE_NAME, ffi_service_main)
}

fn ffi_service_main(arguments: Vec<OsString>) {
    if let Err(e) = run_service_inner(arguments) {
        log::error!("Service error: {}", e);
    }
}

fn run_service_inner(_arguments: Vec<OsString>) -> Result<()> {
    let (shutdown_tx, shutdown_rx) = std::sync::mpsc::channel();
    let shutdown_tx = Arc::new(Mutex::new(Some(shutdown_tx)));
    
    let event_handler = move |control_event| -> ServiceControlHandlerResult {
        match control_event {
            ServiceControl::Stop | ServiceControl::Shutdown => {
                if let Some(tx) = shutdown_tx.lock().unwrap().take() {
                    let _ = tx.send(());
                }
                ServiceControlHandlerResult::NoError
            }
            ServiceControl::Interrogate => ServiceControlHandlerResult::NoError,
            _ => ServiceControlHandlerResult::NotImplemented,
        }
    };
    
    let status_handle = service_control_handler::register(SERVICE_NAME, event_handler)?;
    
    // Update status to running
    status_handle.set_service_status(ServiceStatus {
        service_type: ServiceType::OWN_PROCESS,
        current_state: ServiceState::Running,
        controls_accepted: ServiceControlAccept::STOP | ServiceControlAccept::SHUTDOWN,
        exit_code: ServiceExitCode::Win32(0),
        checkpoint: 0,
        wait_hint: Duration::from_secs(0),
        process_id: None,
    })?;
    
    // Start core runtime in background
    let runtime_handle = std::thread::spawn(|| {
        // Initialize Python runtime
        start_python_core();
    });
    
    // Wait for shutdown signal
    shutdown_rx.recv().unwrap();
    
    // Update status to stopping
    status_handle.set_service_status(ServiceStatus {
        service_type: ServiceType::OWN_PROCESS,
        current_state: ServiceState::StopPending,
        controls_accepted: ServiceControlAccept::empty(),
        exit_code: ServiceExitCode::Win32(0),
        checkpoint: 1,
        wait_hint: Duration::from_secs(30),
        process_id: None,
    })?;
    
    // Shutdown Python runtime
    stop_python_core();
    
    // Wait for runtime thread
    runtime_handle.join().unwrap();
    
    // Update status to stopped
    status_handle.set_service_status(ServiceStatus {
        service_type: ServiceType::OWN_PROCESS,
        current_state: ServiceState::Stopped,
        controls_accepted: ServiceControlAccept::empty(),
        exit_code: ServiceExitCode::Win32(0),
        checkpoint: 0,
        wait_hint: Duration::from_secs(0),
        process_id: None,
    })?;
    
    Ok(())
}

fn start_python_core() {
    // Start embedded Python with FastAPI
    use std::process::Command;
    let mut child = Command::new("python")
        .args(["-m", "uvicorn", "core.runtime.main:app", "--host", "127.0.0.1", "--port", "8000"])
        .current_dir("C:\\Program Files\\ARISE")
        .spawn()
        .expect("Failed to start Python core");
    
    // Store handle for shutdown
    PYTHON_PROCESS.lock().unwrap().replace(child);
}

fn stop_python_core() {
    if let Some(mut child) = PYTHON_PROCESS.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}

lazy_static::lazy_static! {
    static ref PYTHON_PROCESS: Mutex<Option<std::process::Child>> = Mutex::new(None);
}
```

---

## 6. Cross-Component Integration

### 6.1 Service Discovery

```python
# core/integration/service_discovery.py
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
import socket
import asyncio
import logging

logger = logging.getLogger(__name__)

class ServiceType(Enum):
    CORE_API = "core_api"
    REDIS = "redis"
    POSTGRES = "postgres"
    TAURI = "tauri"
    FRONTEND = "frontend"

@dataclass
class ServiceEndpoint:
    service_type: ServiceType
    host: str
    port: int
    protocol: str = "http"
    healthy: bool = True
    metadata: Dict = None

class ServiceDiscovery:
    """Service discovery for ARISE components"""
    
    def __init__(self):
        self._services: Dict[ServiceType, List[ServiceEndpoint]] = {}
        self._local_endpoints: Dict[ServiceType, ServiceEndpoint] = {}
    
    def register_local(self, endpoint: ServiceEndpoint):
        """Register locally running service"""
        self._local_endpoints[endpoint.service_type] = endpoint
        if endpoint.service_type not in self._services:
            self._services[endpoint.service_type] = []
        if endpoint not in self._services[endpoint.service_type]:
            self._services[endpoint.service_type].append(endpoint)
        logger.info(f"Registered local service: {endpoint.service_type.value} at {endpoint.host}:{endpoint.port}")
    
    def discover(self, service_type: ServiceType) -> List[ServiceEndpoint]:
        """Discover available endpoints for service type"""
        return self._services.get(service_type, [])
    
    def get_endpoint(self, service_type: ServiceType, prefer_local: bool = True) -> Optional[ServiceEndpoint]:
        """Get single endpoint for service type"""
        endpoints = self.discover(service_type)
        if not endpoints:
            return None
        
        # Prefer local
        if prefer_local and service_type in self._local_endpoints:
            return self._local_endpoints[service_type]
        
        # Return first healthy
        for ep in endpoints:
            if ep.healthy:
                return ep
        
        return endpoints[0] if endpoints else None
    
    def get_url(self, service_type: ServiceType, path: str = "", prefer_local: bool = True) -> Optional[str]:
        """Get full URL for service"""
        endpoint = self.get_endpoint(service_type, prefer_local)
        if not endpoint:
            return None
        return f"{endpoint.protocol}://{endpoint.host}:{endpoint.port}{path}"

# Auto-discovery from environment
def auto_discover() -> ServiceDiscovery:
    sd = ServiceDiscovery()
    
    # Core API
    core_host = os.getenv("ARISE_CORE_HOST", "localhost")
    core_port = int(os.getenv("ARISE_CORE_PORT", "8000"))
    sd.register_local(ServiceEndpoint(
        service_type=ServiceType.CORE_API,
        host=core_host,
        port=core_port,
    ))
    
    # Redis
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    sd.register_local(ServiceEndpoint(
        service_type=ServiceType.REDIS,
        host=redis_host,
        port=redis_port,
        protocol="redis",
    ))
    
    # Postgres
    pg_host = os.getenv("POSTGRES_HOST", "localhost")
    pg_port = int(os.getenv("POSTGRES_PORT", "5432"))
    sd.register_local(ServiceEndpoint(
        service_type=ServiceType.POSTGRES,
        host=pg_host,
        port=pg_port,
        protocol="postgresql",
    ))
    
    return sd
```

### 6.2 Client SDKs

```python
# core/integration/clients.py
import httpx
import websockets
import asyncio
from typing import Optional, Dict, Any, AsyncGenerator
from dataclasses import dataclass

from core.config import get_config

@dataclass
class CoreAPIClient:
    """Client for ARISE Core API"""
    base_url: str
    timeout: float = 30.0
    _client: Optional[httpx.AsyncClient] = None
    _ws_url: Optional[str] = None
    
    async def __aenter__(self):
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
        self._ws_url = self.base_url.replace("http", "ws") + "/ws"
        return self
    
    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()
    
    # Task operations
    async def create_task(self, kind: str, payload: Dict, priority: int = 5) -> Dict:
        resp = await self._client.post("/api/v1/tasks", json={
            "kind": kind,
            "payload": payload,
            "priority": priority,
        })
        resp.raise_for_status()
        return resp.json()
    
    async def get_task(self, task_id: str) -> Dict:
        resp = await self._client.get(f"/api/v1/tasks/{task_id}")
        resp.raise_for_status()
        return resp.json()
    
    async def cancel_task(self, task_id: str) -> Dict:
        resp = await self._client.post(f"/api/v1/tasks/{task_id}/cancel")
        resp.raise_for_status()
        return resp.json()
    
    async def wait_for_task(self, task_id: str, timeout: float = 300) -> Dict:
        """Wait for task completion via WebSocket"""
        async with websockets.connect(f"{self._ws_url}/tasks/{task_id}") as ws:
            async for message in ws:
                data = json.loads(message)
                if data["status"] in ("completed", "failed", "cancelled"):
                    return data
        raise TimeoutError(f"Task {task_id} did not complete")
    
    # Memory operations
    async def store_memory(self, kind: str, content: str, **kwargs) -> Dict:
        resp = await self._client.post("/api/v1/memory", json={
            "kind": kind,
            "content": content,
            **kwargs,
        })
        resp.raise_for_status()
        return resp.json()
    
    async def query_memory(self, query: str, kind: str = None, limit: int = 10) -> Dict:
        params = {"query": query, "limit": limit}
        if kind:
            params["kind"] = kind
        resp = await self._client.get("/api/v1/memory", params=params)
        resp.raise_for_status()
        return resp.json()
    
    # Voice
    async def start_voice_session(self) -> Dict:
        resp = await self._client.post("/api/v1/voice/session")
        resp.raise_for_status()
        return resp.json()
    
    # Health
    async def health_check(self) -> Dict:
        resp = await self._client.get("/health")
        resp.raise_for_status()
        return resp.json()

# Factory
async def create_core_client() -> CoreAPIClient:
    config = get_config()
    sd = auto_discover()
    base_url = sd.get_url(ServiceType.CORE_API) or config.frontend.api_url
    return CoreAPIClient(base_url=base_url)
```

```typescript
// src/services/api/client.ts
import { EventSource } from 'eventsource';

export class AriseAPIClient {
  private baseUrl: string;
  private wsUrl: string;
  private ws: WebSocket | null = null;
  
  constructor(baseUrl?: string) {
    this.baseUrl = baseUrl || import.meta.env.VITE_API_URL || 'http://localhost:8000';
    this.wsUrl = this.baseUrl.replace('http', 'ws') + '/ws';
  }
  
  // Generic request
  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: 'Unknown error' }));
      throw new AriseAPIError(error);
    }
    
    return response.json();
  }
  
  // Tasks
  async createTask(kind: string, payload: any, priority = 5) {
    return this.request<{ task_id: string }>('/api/v1/tasks', {
      method: 'POST',
      body: JSON.stringify({ kind, payload, priority }),
    });
  }
  
  async getTask(taskId: string) {
    return this.request(`/api/v1/tasks/${taskId}`);
  }
  
  async cancelTask(taskId: string) {
    return this.request(`/api/v1/tasks/${taskId}/cancel`, { method: 'POST' });
  }
  
  async waitForTask(taskId: string): Promise<any> {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(`${this.wsUrl}/tasks/${taskId}`);
      
      this.ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (['completed', 'failed', 'cancelled'].includes(data.status)) {
          this.ws?.close();
          resolve(data);
        }
      };
      
      this.ws.onerror = reject;
      this.ws.onclose = () => reject(new Error('Connection closed'));
    });
  }
  
  // Memory
  async storeMemory(kind: string, content: string, options: any = {}) {
    return this.request('/api/v1/memory', {
      method: 'POST',
      body: JSON.stringify({ kind, content, ...options }),
    });
  }
  
  async queryMemory(query: string, kind?: string, limit = 10) {
    const params = new URLSearchParams({ query, limit: limit.toString() });
    if (kind) params.append('kind', kind);
    return this.request(`/api/v1/memory?${params}`);
  }
  
  // Voice
  async startVoiceSession() {
    return this.request('/api/v1/voice/session', { method: 'POST' });
  }
  
  // Health
  async healthCheck() {
    return this.request('/health');
  }
  
  // Server-Sent Events for real-time updates
  subscribeToEvents(eventTypes: string[], callback: (event: any) => void): () => void {
    const params = new URLSearchParams();
    eventTypes.forEach(t => params.append('events', t));
    
    const es = new EventSource(`${this.baseUrl}/api/v1/events/stream?${params}`);
    
    es.onmessage = (event) => {
      try {
        callback(JSON.parse(event.data));
      } catch (e) {
        console.error('Failed to parse SSE:', e);
      }
    };
    
    es.onerror = () => {
      console.error('SSE connection error');
      es.close();
    };
    
    return () => es.close();
  }
}

export class AriseAPIError extends Error {
  constructor(public error: any) {
    super(error.message || 'API Error');
    this.name = 'AriseAPIError';
  }
}

// Singleton instance
export const api = new AriseAPIClient();
```

---

## 7. Health Checks & Monitoring

### 7.1 Health Endpoint

```python
# core/runtime/health.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
import asyncio
import time
import psutil
import logging

from core.database import get_database
from core.config import get_config

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger(__name__)

class HealthStatus(BaseModel):
    status: str  # healthy, degraded, unhealthy
    version: str
    uptime_seconds: float
    checks: Dict[str, "HealthCheck"]
    system: "SystemInfo"

class HealthCheck(BaseModel):
    status: str  # pass, warn, fail
    component: str
    message: str
    latency_ms: Optional[float] = None
    details: Dict[str, Any] = {}

class SystemInfo(BaseModel):
    cpu_percent: float
    memory_percent: float
    memory_available_mb: float
    disk_percent: float
    disk_free_gb: float
    open_files: int
    connections: int

_start_time = time.time()

@router.get("", response_model=HealthStatus)
async def health_check():
    """Comprehensive health check"""
    checks = {}
    overall_status = "healthy"
    
    # Database check
    checks["database"] = await _check_database()
    if checks["database"].status == "fail":
        overall_status = "unhealthy"
    elif checks["database"].status == "warn":
        overall_status = "degraded"
    
    # Redis check
    checks["redis"] = await _check_redis()
    if checks["redis"].status == "fail":
        overall_status = "unhealthy"
    elif checks["redis"].status == "warn":
        overall_status = "degraded"
    
    # Model providers
    checks["models"] = await _check_model_providers()
    if checks["models"].status == "fail":
        overall_status = "degraded"  # Not fatal
    
    # Disk space
    checks["disk"] = _check_disk()
    if checks["disk"].status == "fail":
        overall_status = "unhealthy"
    
    # Memory
    checks["memory"] = _check_memory()
    if checks["memory"].status == "fail":
        overall_status = "degraded"
    
    # Event bus
    checks["event_bus"] = await _check_event_bus()
    
    return HealthStatus(
        status=overall_status,
        version=get_config().version,
        uptime_seconds=time.time() - _start_time,
        checks=checks,
        system=_get_system_info(),
    )

@router.get("/ready")
async def readiness_check():
    """Kubernetes readiness probe"""
    # Quick checks only
    db_ok = await _check_database(quick=True)
    redis_ok = await _check_redis(quick=True)
    
    if db_ok.status == "pass" and redis_ok.status == "pass":
        return {"status": "ready"}
    
    raise HTTPException(503, "Not ready")

@router.get("/live")
async def liveness_check():
    """Kubernetes liveness probe"""
    return {"status": "alive"}

async def _check_database(quick: bool = False) -> HealthCheck:
    start = time.time()
    try:
        db = get_database()
        async with db.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        latency = (time.time() - start) * 1000
        
        if quick:
            return HealthCheck(status="pass", component="database", message="OK", latency_ms=latency)
        
        # Check pool status
        pool = db.engine.pool
        return HealthCheck(
            status="pass" if pool.checkedout() < pool.size() * 0.9 else "warn",
            component="database",
            message="OK",
            latency_ms=latency,
            details={
                "pool_size": pool.size(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
            }
        )
    except Exception as e:
        return HealthCheck(
            status="fail",
            component="database",
            message=str(e),
            latency_ms=(time.time() - start) * 1000,
        )

async def _check_redis(quick: bool = False) -> HealthCheck:
    start = time.time()
    try:
        import redis.asyncio as redis
        config = get_config()
        client = redis.from_url(config.redis.url)
        await client.ping()
        await client.close()
        latency = (time.time() - start) * 1000
        
        return HealthCheck(
            status="pass",
            component="redis",
            message="OK",
            latency_ms=latency,
        )
    except Exception as e:
        return HealthCheck(
            status="fail",
            component="redis",
            message=str(e),
            latency_ms=(time.time() - start) * 1000,
        )

async def _check_model_providers() -> HealthCheck:
    """Check model provider availability"""
    config = get_config()
    results = {}
    
    for name, provider in config.model_router.providers.items():
        if not provider.api_key:
            results[name] = "no_key"
            continue
        
        try:
            # Quick health check
            from core.model_router import ModelRouter
            router = ModelRouter()
            await router.initialize()
            await router.health_check_provider(name)
            results[name] = "ok"
        except Exception as e:
            results[name] = f"error: {e}"
    
    failed = [k for k, v in results.items() if v != "ok" and v != "no_key"]
    
    return HealthCheck(
        status="fail" if failed else "pass",
        component="models",
        message="All providers healthy" if not failed else f"Failed: {', '.join(failed)}",
        details=results,
    )

def _check_disk() -> HealthCheck:
    usage = psutil.disk_usage("/")
    percent = usage.percent
    
    return HealthCheck(
        status="fail" if percent > 95 else "warn" if percent > 85 else "pass",
        component="disk",
        message=f"Disk usage: {percent:.1f}%",
        details={
            "total_gb": usage.total / (1024**3),
            "used_gb": usage.used / (1024**3),
            "free_gb": usage.free / (1024**3),
            "percent": percent,
        }
    )

def _check_memory() -> HealthCheck:
    mem = psutil.virtual_memory()
    percent = mem.percent
    
    return HealthCheck(
        status="fail" if percent > 95 else "warn" if percent > 85 else "pass",
        component="memory",
        message=f"Memory usage: {percent:.1f}%",
        details={
            "total_mb": mem.total / (1024**2),
            "available_mb": mem.available / (1024**2),
            "percent": percent,
        }
    )

async def _check_event_bus() -> HealthCheck:
    from core.events.bus import get_event_bus
    bus = get_event_bus()
    stats = bus.get_stats()
    
    return HealthCheck(
        status="pass" if stats["running"] else "fail",
        component="event_bus",
        message="Event bus running" if stats["running"] else "Event bus stopped",
        details=stats,
    )

def _get_system_info() -> SystemInfo:
    process = psutil.Process()
    return SystemInfo(
        cpu_percent=psutil.cpu_percent(interval=0.1),
        memory_percent=psutil.virtual_memory().percent,
        memory_available_mb=psutil.virtual_memory().available / (1024**2),
        disk_percent=psutil.disk_usage("/").percent,
        disk_free_gb=psutil.disk_usage("/").free / (1024**3),
        open_files=len(process.open_files()),
        connections=len(process.connections()),
    )
```

### 7.2 Prometheus Metrics

```python
# core/runtime/metrics.py
from prometheus_client import Counter, Histogram, Gauge, Summary, CollectorRegistry
from functools import wraps
import time

registry = CollectorRegistry()

# HTTP metrics
http_requests_total = Counter(
    "arise_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
    registry=registry
)

http_request_duration = Histogram(
    "arise_http_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint"],
    registry=registry
)

# Task metrics
tasks_submitted = Counter(
    "arise_tasks_submitted_total",
    "Tasks submitted",
    ["kind", "priority"],
    registry=registry
)

tasks_completed = Counter(
    "arise_tasks_completed_total",
    "Tasks completed",
    ["kind", "status"],
    registry=registry
)

task_duration = Histogram(
    "arise_task_duration_seconds",
    "Task execution duration",
    ["kind"],
    registry=registry
)

task_queue_size = Gauge(
    "arise_task_queue_size",
    "Current task queue size",
    ["priority"],
    registry=registry
)

# Model metrics
model_requests = Counter(
    "arise_model_requests_total",
    "Model requests",
    ["provider", "model", "task_type", "status"],
    registry=registry
)

model_latency = Histogram(
    "arise_model_latency_seconds",
    "Model request latency",
    ["provider", "model"],
    registry=registry
)

model_tokens = Counter(
    "arise_model_tokens_total",
    "Model tokens used",
    ["provider", "model", "type"],  # input, output
    registry=registry
)

model_cost = Counter(
    "arise_model_cost_usd_total",
    "Model cost in USD",
    ["provider", "model"],
    registry=registry
)

# Memory metrics
memory_operations = Counter(
    "arise_memory_operations_total",
    "Memory operations",
    ["kind", "operation", "status"],
    registry=registry
)

memory_store_size = Gauge(
    "arise_memory_store_size",
    "Memory store size",
    ["kind"],
    registry=registry
)

# Voice metrics
voice_sessions = Counter(
    "arise_voice_sessions_total",
    "Voice sessions",
    ["status"],  # started, completed, failed
    registry=registry
)

voice_latency = Histogram(
    "arise_voice_latency_seconds",
    "Voice pipeline latency",
    ["stage"],  # asr, llm, tts
    registry=registry
)

# Agent metrics
agent_tasks = Counter(
    "arise_agent_tasks_total",
    "Agent tasks",
    ["agent_role", "status"],
    registry=registry
)

agent_delegations = Counter(
    "arise_agent_delegations_total",
    "Agent delegations",
    ["from_role", "to_role", "status"],
    registry=registry
)

# System metrics
system_cpu = Gauge(
    "arise_system_cpu_percent",
    "System CPU usage",
    registry=registry
)

system_memory = Gauge(
    "arise_system_memory_percent",
    "System memory usage",
    registry=registry
)

# Decorators
def track_http_metrics(method: str, endpoint: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                status = getattr(result, 'status_code', 200)
                http_requests_total.labels(method=method, endpoint=endpoint, status=status).inc()
                return result
            except Exception as e:
                http_requests_total.labels(method=method, endpoint=endpoint, status=500).inc()
                raise
            finally:
                http_request_duration.labels(method=method, endpoint=endpoint).observe(time.time() - start)
        return wrapper
    return decorator

def track_task_metrics(kind: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            tasks_submitted.labels(kind=kind, priority="normal").inc()
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                tasks_completed.labels(kind=kind, status="success").inc()
                return result
            except Exception as e:
                tasks_completed.labels(kind=kind, status="error").inc()
                raise
            finally:
                task_duration.labels(kind=kind).observe(time.time() - start)
        return wrapper
    return decorator

# Metrics endpoint
from fastapi import Response

async def metrics_endpoint():
    from prometheus_client import generate_latest
    return Response(
        content=generate_latest(registry),
        media_type="text/plain"
    )
```

---

## 8. Backup & Disaster Recovery

### 8.1 Backup Script

```bash
#!/bin/bash
# scripts/backup.sh

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups/arise}"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS="${RETENTION_DAYS:-30}"

mkdir -p "$BACKUP_DIR"

echo "Starting ARISE backup at $DATE"

# Backup PostgreSQL
echo "Backing up PostgreSQL..."
pg_dump -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d arise \
    | gzip > "$BACKUP_DIR/postgres_$DATE.sql.gz"

# Backup Redis
echo "Backing up Redis..."
redis-cli -h "$REDIS_HOST" -a "$REDIS_PASSWORD" --rdb "$BACKUP_DIR/redis_$DATE.rdb"
gzip "$BACKUP_DIR/redis_$DATE.rdb"

# Backup SQLite (events, config)
echo "Backing up SQLite..."
sqlite3 /opt/arise/data/events.db ".backup $BACKUP_DIR/events_$DATE.db"
gzip "$BACKUP_DIR/events_$DATE.db"

# Backup configuration
echo "Backing up configuration..."
tar -czf "$BACKUP_DIR/config_$DATE.tar.gz" /etc/arise /opt/arise/config

# Upload to S3 (optional)
if [ -n "${S3_BUCKET:-}" ]; then
    echo "Uploading to S3..."
    aws s3 sync "$BACKUP_DIR" "s3://$S3_BUCKET/arise/backups/$DATE/" --exclude "*" --include "*_$DATE.*"
fi

# Cleanup old backups
echo "Cleaning up backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "*.gz" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.db" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete

echo "Backup completed at $(date)"
```

### 8.2 Restore Procedure

```bash
#!/bin/bash
# scripts/restore.sh

set -euo pipefail

BACKUP_DATE="${1:-latest}"
BACKUP_DIR="${BACKUP_DIR:-/backups/arise}"

if [ "$BACKUP_DATE" = "latest" ]; then
    BACKUP_DATE=$(ls -1 "$BACKUP_DIR"/postgres_*.sql.gz | tail -1 | sed 's/.*postgres_\(.*\)\.sql\.gz/\1/')
fi

echo "Restoring ARISE from backup: $BACKUP_DATE"

# Stop services
systemctl stop arise-core
systemctl stop arise-tauri

# Restore PostgreSQL
echo "Restoring PostgreSQL..."
gunzip -c "$BACKUP_DIR/postgres_$BACKUP_DATE.sql.gz" | \
    psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d arise

# Restore Redis
echo "Restoring Redis..."
redis-cli -h "$REDIS_HOST" -a "$REDIS_PASSWORD" SHUTDOWN NOSAVE
gunzip -c "$BACKUP_DIR/redis_$BACKUP_DATE.rdb.gz" > /var/lib/redis/dump.rdb
systemctl start redis

# Restore SQLite
echo "Restoring SQLite..."
cp "$BACKUP_DIR/events_$BACKUP_DATE.db.gz" /opt/arise/data/events.db.gz
gunzip -f /opt/arise/data/events.db.gz

# Restore configuration
echo "Restoring configuration..."
tar -xzf "$BACKUP_DIR/config_$BACKUP_DATE.tar.gz" -C /

# Start services
systemctl start arise-core
systemctl start arise-tauri

echo "Restore completed. Verify services are healthy."
```

---

## 9. Rollout Strategy

### 9.1 Blue-Green Deployment

```yaml
# k8s/blue-green.yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: arise-core
  namespace: arise
spec:
  replicas: 6
  strategy:
    blueGreen:
      activeService: arise-core-blue
      previewService: arise-core-green
      autoPromotionEnabled: false
      scaleDownDelaySeconds: 300
  selector:
    matchLabels:
      app: arise-core
  template:
    metadata:
      labels:
        app: arise-core
    spec:
      containers:
      - name: core
        image: arise/core:v1.1.0
        ports:
        - containerPort: 8000
---
apiVersion: v1
kind: Service
metadata:
  name: arise-core-blue
  namespace: arise
spec:
  selector:
    app: arise-core
    rollout: blue
  ports:
  - port: 8000
---
apiVersion: v1
kind: Service
metadata:
  name: arise-core-green
  namespace: arise
spec:
  selector:
    app: arise-core
    rollout: green
  ports:
  - port: 8000
```

### 9.2 Canary Deployment

```yaml
# k8s/canary.yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: arise-core
  namespace: arise
spec:
  replicas: 10
  strategy:
    canary:
      steps:
      - setWeight: 10
      - pause: {duration: 5m}
      - setWeight: 30
      - pause: {duration: 10m}
      - setWeight: 50
      - pause: {duration: 15m}
      - setWeight: 100
      canaryMetadata:
        labels:
          version: canary
      stableMetadata:
        labels:
          version: stable
      trafficRouting:
        nginx:
          stableIngress: arise-ingress
  selector:
    matchLabels:
      app: arise-core
  template:
    metadata:
      labels:
        app: arise-core
    spec:
      containers:
      - name: core
        image: arise/core:v1.1.0
```

---

## 10. Troubleshooting Runbooks

### 10.1 Common Issues

| Symptom | Diagnosis | Resolution |
|---------|-----------|------------|
| Core API 503 | Database connection pool exhausted | Check `max_overflow`, scale DB, check for leaked connections |
| High memory | Memory leak in task engine | Enable `tracemalloc`, check `task_engine.checkpoint_interval` |
| Voice not working | Audio device permissions | `usermod -a -G audio arise`, check PulseAudio/PipeWire |
| UIA automation fails | Target app not accessible | Run as admin, check UIA permissions, try Playwright fallback |
| WebSocket disconnects | Proxy timeout | Increase `proxy_read_timeout` in nginx, enable WebSocket ping |
| Model timeouts | Provider latency | Check circuit breaker, increase timeout, verify API keys |
| Redis OOM | Memory pressure | Increase `maxmemory`, check for key leaks, enable LRU |

### 10.2 Debug Commands

```bash
# Check service status
systemctl status arise-core
journalctl -u arise-core -f

# Check database
psql -h localhost -U arise -d arise -c "SELECT * FROM pg_stat_activity;"

# Check Redis
redis-cli -a $REDIS_PASSWORD INFO memory
redis-cli -a $REDIS_PASSWORD SLOWLOG GET 10

# Check Python process
py-spy top --pid $(pgrep -f uvicorn)
py-spy record --pid $(pgrep -f uvicorn) -o profile.svg

# Check Rust process
perf record -g -p $(pgrep arise)
perf report

# Network debugging
ss -tlnp | grep :8000
curl -v http://localhost:8000/health
wscat -c ws://localhost:8000/ws

# Database debugging
psql -h localhost -U arise -d arise -c "
SELECT pid, state, query_start, query 
FROM pg_stat_activity 
WHERE state != 'idle';"

# Logs
tail -f /opt/arise/logs/arise.log | jq .
journalctl -u arise-core --since "1 hour ago" -o json | jq .
```

---

*This deployment guide covers all deployment scenarios for ARISE from local development to production Kubernetes clusters with proper monitoring, backup, and rollout strategies.*