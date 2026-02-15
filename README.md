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
