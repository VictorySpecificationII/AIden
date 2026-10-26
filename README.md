# AIden

Copilot, akin to Jarvis from Iron Man. A project inspired long before the GPT days.

AIden is a self-hosted AI platform composed of multiple containerized services providing model serving, vector storage, experiment tracking, and full-stack observability. The system is designed to run locally using Docker Compose and provides a reproducible environment for developing and operating AI-assisted workflows.

The platform uses OpenTelemetry for vendor-agnostic telemetry, forwarding metrics, logs, traces, and spans to a collector for aggregation, visualization, and analysis.

---

## Architecture Overview

AIden runs as a composed platform of services providing:

- AI model serving (Ollama)
- Vector search and embedding storage (Qdrant)
- Experiment tracking and artifact storage (MLflow + Postgres + MinIO)
- Observability and telemetry (OpenTelemetry Collector, Prometheus, Grafana, Jaeger)
- Log aggregation (Elasticsearch, Logstash, Kibana)
- GPU telemetry (NVIDIA DCGM exporter)
- Web interface for interaction (OpenWebUI)
- Unified service dashboard (Homepage)

Telemetry pipeline:

```bash
Application → OpenTelemetry Collector → Prometheus / Jaeger / Elasticsearch → Grafana / Kibana
```


This enables full visibility into system performance, resource utilization, and service interactions.

---

## Design Intent

AIden exists to provide a reproducible local platform for:

- Developing and testing AI-assisted workflows
- Operating GPU-backed model serving infrastructure
- Experimenting with observability, tracing, and telemetry pipelines
- Evaluating MLOps workflows and artifact tracking
- Understanding system behavior across compute, storage, and inference layers

The platform mirrors patterns commonly used in production AI infrastructure environments.

---

## Platform Components

### AI / Inference
- Ollama (GPU model serving)
- OpenWebUI (chat interface)
- AIden application service

### Storage
- Qdrant (vector database)
- MinIO (S3-compatible artifact storage)
- PostgreSQL (MLflow backend)

### MLOps
- MLflow (experiment tracking and artifact management)

### Observability
- OpenTelemetry Collector
- Prometheus
- Grafana
- Jaeger
- Elasticsearch / Logstash / Kibana (ELK stack)
- NVIDIA DCGM Exporter (GPU telemetry)

### Platform UX
- Homepage dashboard for service discovery and navigation

---

## Software Requirements

- Docker
- Docker Compose
- Python 3.10+
- NVIDIA GPU (optional, for hardware acceleration)
- NVIDIA Container Toolkit (optional, GPU support)

---

## Testing

To run the pytest suite:

```bash
pytest
```

---

## Linting

This project uses pylint:

```bash
pylint <path-to-file.py>
```

---

## Deployment

First Time Setup (GPU support)

Install NVIDIA drivers and container runtime:

```bash
chmod +x ./bootstrap/nvidia-cuda-toolkit.sh
bash ./bootstrap/nvidia-cuda-toolkit.sh

chmod +x ./bootstrap/nvidia-container-runtime.sh
bash ./bootstrap/nvidia-container-runtime.sh

sudo systemctl daemon-reload
sudo systemctl restart docker
```

---

## Starting the platform

Credentials, endpoints and machine-specific paths are read from environment variables. Create your local `.env` (gitignored) from the template first; Docker Compose loads it automatically and refuses to start if a required variable is missing:

```bash
cp .env.example .env
chmod 600 .env
bootstrap/detect-profiles.sh   # detects GPUs/NPU and sets the profiles; --dry-run to only report
# edit .env: set COMPOSE_PROFILES and LLAMACPP_DIR, and replace the default credentials if needed
```

`COMPOSE_PROFILES` selects the hardware profiles for this machine (`bootstrap/detect-profiles.sh` sets it for you). Pick one of `nvidia` / `cpu`, optionally combined with `npu` and/or `intel-gpu` (e.g. `COMPOSE_PROFILES=cpu,npu,intel-gpu`):

| Profile | Adds |
|---|---|
| `nvidia` | Ollama on the NVIDIA GPU, DCGM exporter |
| `cpu` | Ollama on CPU |
| `npu` | OVMS serving a small LLM on the Intel NPU (OpenAI-compatible API on port 8001), Intel exporter, Grafana "AIden's NPU" dashboard |
| `intel-gpu` | OVMS serving a mid-size LLM on an Intel GPU (Arc / iGPU), OpenAI-compatible API on port 8002, Intel exporter, Grafana "AIden's Intel GPU" dashboard |

With `npu` / `intel-gpu`, `OPENWEBUI_OPENAI_API_BASE_URLS` must list `http://ovms-npu:8001/v3` / `http://ovms-gpu:8002/v3` (";"-separated, one non-empty `OPENWEBUI_OPENAI_API_KEYS` entry per URL) so OpenWebUI shows the models; `detect-profiles.sh` sets this. The first start downloads each model and compiles it for its device (several minutes); later starts use the cache.

Measured on a Core Ultra 7 265H: Qwen3-8B on the Arc iGPU ~14 tok/s, Phi-3.5-mini on the NPU ~11 tok/s. The NPU's value is low power and keeping the GPU/CPU free, not speed.

A profile can also be chosen per command, e.g. `docker compose --profile cpu up -d`.

```bash
docker compose up -d
```

This will start all platform services.


## Observability Integration

The OpenTelemetry collector accepts telemetry on:

```bash
grpc://localhost:4317
```

Applications can export:

- metrics
- logs
- traces

to this endpoint.

Telemetry is then forwarded to:

- Prometheus (metrics)
- Jaeger (traces)
- Elasticsearch (logs)
- Grafana / Kibana (visualization)

---

## Accessing Platform Services

Dashboard:

```bash
http://localhost:8092
```

Key Interfaces:
 - Grafana: http://localhost:3000
 - Prometheus: http://localhost:9090
 - Jaeger: http://localhost:16686
 - Kibana: http://localhost:5601
 - OpenWebUI: http://localhost:8080
 - MLFlow: http://localhost:5000
 - MinIO: http://localhost:9001
 - QDrant: http://localhost:6333

---

## Notes

This platform is intended for local development and experimentation. Default credentials and configuration are not production hardened.

---

## Future Improvements

 - [ ] Kubernetes deployment support
 - [ ] Secret management integration
 - [ ] Alerting pipeline via Alertmanager
 - [ ] Multi-node deployment support
 - [ ] Production hardening and access control

---
