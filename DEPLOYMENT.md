# CodeMind Deployment & Operations Manual

This guide describes how to install, configure, deploy, and operate **CodeMind** in local development, containerized, and production environments.

---

## 1. System Requirements

- **Operating System:** Linux (Ubuntu 22.04+ recommended), macOS 13+, or Windows 10/11 (64-bit)
- **Python Version:** Python 3.10, 3.11, or 3.12 (Python 3.12 recommended)
- **Git:** Git 2.30+ installed and available on system `PATH`
- **Memory (RAM):**
  - Minimum: 4 GB RAM (Mock / CPU mode)
  - Recommended: 16 GB RAM (Dense Transformer embeddings & large repository graphs)
- **Disk Storage:** At least 2 GB free disk space for dependencies and vector indexes

---

## 2. Local Installation & Setup

### 2.1 Clone Repository
```bash
git clone https://github.com/organization/codemind.git
cd codemind
```

### 2.2 Create Virtual Environment
```bash
python -m venv .venv

# On Linux / macOS:
source .venv/bin/activate

# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
```

### 2.3 Install Package & Dependencies

#### Production Installation
```bash
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
pip install -e .
```

#### Development & Testing Installation
```bash
pip install -r requirements-dev.txt
pip install -e ".[dev]"
```

Verify the installation and CLI entrypoint:
```bash
codemind --help
```

---

## 3. Configuration & Environment Variables

CodeMind reads configuration from system environment variables or a `.env` file in the project root.

| Environment Variable | Allowed Values | Default | Description |
| :--- | :--- | :--- | :--- |
| `CODEMIND_EMBEDDING_PROVIDER` | `mock`, `sentence-transformers`, `gemini` | `sentence-transformers` | Selects embedding provider. Set to `mock` for deterministic offline testing. |
| `GEMINI_API_KEY` | string | `""` | Google Gemini API key for live LLM reasoning and synthesis. |
| `OPENAI_API_KEY` | string | `""` | Optional OpenAI API key for alternative LLM providers. |
| `ANTHROPIC_API_KEY` | string | `""` | Optional Anthropic API key for alternative LLM providers. |
| `HOST` | string IP address | `0.0.0.0` | Bind IP for the FastAPI web server. |
| `PORT` | integer | `8000` | Port for the FastAPI web server. |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` | Logging verbosity level. |

---

## 4. CLI Usage Examples

CodeMind exposes a unified CLI executable (`codemind`):

### 4.1 Inspect a Repository
```bash
codemind inspect /path/to/repo --detail
```

### 4.2 Ask Grounded Question (Grounded RAG)
```bash
codemind ask /path/to/repo "How does the authentication middleware validate tokens?"
```

### 4.3 Agentic Multi-Step Investigation
```bash
codemind investigate /path/to/repo "Analyze impact of modifying OrderRepository"
```

### 4.4 Git Temporal Intelligence
```bash
# Code churn hotspots
codemind git-churn /path/to/repo --limit 10

# Co-change coupling
codemind git-coupling /path/to/repo --min-support 3 --min-confidence 0.5
```

### 4.5 Start Interactive Web Server
```bash
codemind serve /path/to/repo --host 0.0.0.0 --port 8000
```

---

## 5. Docker Container Deployment

CodeMind includes a lightweight, hardened production `Dockerfile` based on `python:3.12-slim`.

### 5.1 Build Docker Image
```bash
docker build -t codemind:latest .
```

### 5.2 Run Container
```bash
docker run -d \
  --name codemind-app \
  -p 8000:8000 \
  -e CODEMIND_EMBEDDING_PROVIDER=mock \
  -e GEMINI_API_KEY="your-api-key" \
  -v /local/repos:/repos:ro \
  codemind:latest
```

### 5.3 Health Check
Verify container health using the built-in healthcheck:
```bash
docker inspect --format='{{json .State.Health}}' codemind-app
```
Or via HTTP:
```bash
curl -f http://localhost:8000/api/graph
```

---

## 6. Concurrency & Process Model Architecture

> [!CAUTION]
> **Single-Worker Process Contract (`--workers 1`):**
> CodeMind is architected as an **in-memory, graph-centric repository intelligence platform**. The active repository AST symbol hierarchy, NetworkX knowledge graph, quotient graphs, and Sparse BM25 indexes reside in process memory.
> 
> - **Thread-Safety:** Thread concurrency within the single process is fully synchronized via `CodebaseState._lock` (an internal `threading.RLock`) protecting write operations and cache updates.
> - **Multi-Worker Safety:** Multi-worker deployments (e.g. `uvicorn --workers 4` or Gunicorn prefork workers) run isolated operating system processes that **do not share process memory**. Changes scanned by worker process A would be invisible to worker process B.
> - **Rule:** Always run Uvicorn with `--workers 1`. For horizontal scaling across multiple independent repositories, deploy separate container instances per repository behind an API gateway or reverse proxy (e.g. Nginx, Traefik).

---

## 7. Production Deployment (Systemd + Nginx Reverse Proxy)

### 7.1 Systemd Service Unit (`/etc/systemd/system/codemind.service`)
```ini
[Unit]
Description=CodeMind Code Intelligence Platform
After=network.target

[Service]
Type=simple
User=codemind
Group=codemind
WorkingDirectory=/opt/codemind
EnvironmentFile=/opt/codemind/.env
ExecStart=/opt/codemind/.venv/bin/uvicorn codemind.web.app:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable codemind
sudo systemctl start codemind
sudo systemctl status codemind
```

### 7.2 Nginx Reverse Proxy (`/etc/nginx/sites-available/codemind`)
```nginx
server {
    listen 80;
    server_name codemind.internal;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }
}
```

Enable site and reload Nginx:
```bash
sudo ln -s /etc/nginx/sites-available/codemind /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 8. Verification & Smoke Testing

Run the automated test suite to verify a fresh deployment:
```bash
pytest -v
```

Run the milestone performance acceptance target checks:
```bash
python scripts/benchmark_targets.py
```
