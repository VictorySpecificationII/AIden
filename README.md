# AIden

Copilot, akin to Jarvis from Iron Man. A project inspired long before the GPT days. Uses OpenTelemetry for vendor-agnostic telemetry, forwarding (at the moment) logs and traces to a collector.

## Setup

### Create Python Virtual Environment

```bash
cd AIden
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

First, enable the Otel Collector, then run the API.

### Enable Otel Collector

```bash
docker-compose up -d
docker logs -f otel-collector
```
### Run API

```bash
uvicorn aiden:api --reload
```

## Extras

The deployment includes Heimdall, an application dashboard. To make use of it:

 - Navigate to
```bash
http://localhost:8091
```
 - Click Settings > Import > Browse
 - Select heimdall.json from the project directory and hit "Import"

 Now you have an application dashboard you can use for quick access.
