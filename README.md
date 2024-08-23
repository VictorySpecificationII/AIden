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

### Isolated from the rest of the stack

First, enable the Otel Collector, then run the API.

#### Modify API otel-collector URL's

Modify the code in src/api/v1/aiden.py to point to localhost:4317 instead of otel-collector:4317

#### Enable Otel Collector

```bash
docker-compose up -d otel-collector
docker logs -f otel-collector
```
#### Run API

```bash
cd src/api/v1
uvicorn aiden:api --reload
```

### Docker Compose

#### Modify API otel-collector URL's

If you haven't modified the API observability URL's in the code, no need to do anything.
If you have (i.e ran it with the method above), just replace localhost with otel-collector.

#### Spin up stack

```bash
docker-compose up -d
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
