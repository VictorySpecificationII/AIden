# AIden

Copilot, akin to Jarvis from Iron Man. A project inspired long before the GPT days. Uses OpenTelemetry for vendor-agnostic telemetry, forwarding metrics, logs, traces and spans to a collector.

## Software Versions

 - Python3: 3.10.12
 - Venv: python3.10-venv
 
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
## Usage

### Docker Compose

#### First Time Setup
```bash
chmod +x ./bootstrap/nvidia-container-runtime.sh
bash ./bootstrap/nvidia-container-runtime.sh
```

#### Subsequently
```bash
docker-compose up -d
```
## Integrating your implementation with monitoring

The OTel collector is primed to accept metrics, logs and traces on http://localhost:4317. At the minute, it does so over gRPC. You can enable HTTP if you need it. Any code should use that as a target to send to.

## Extras

The deployment includes Homepage, an application dashboard. To make use of it:

 - Navigate to
```bash
http://localhost:8092
```
The dashboard performs service auto-discovery so if you add a service to the stack, and label it the same way the other services are, it will show up in the dashboard automagically.

