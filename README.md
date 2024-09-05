# AIden

Copilot, akin to Jarvis from Iron Man. A project inspired long before the GPT days. Uses OpenTelemetry for vendor-agnostic telemetry, forwarding metrics, logs, traces and spans to a collector.

## Test

To run the pytest suite, navigate to the root directory of the project and run 

```bash
pytest
```

## Linting

The linter used here is pylint, to run just execute

```bash
pylint <path-to-file.py>
```

## Setup

### Create Python Virtual Environment

```bash
cd src/api/v1/aiden
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Register Access Token on HuggingFace

 - Register an access token on HuggingFace hub.
 - Copy access token, create a .env file and add the following inside:
 ```bash
 export HUGGINGFACE_HUB_TOKEN=
 ```
 - Add your key after the = sign, no spaces
 - Run 
 ```bash 
 source .env
 ```

 Should you wish to work with a gated model, now you can.

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
cd src/api/v1/aiden
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
