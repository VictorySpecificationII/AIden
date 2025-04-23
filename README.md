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
## Usage

### Docker Compose

```bash
docker-compose up -d
```
## Integrating your implementation with monitoring

The OTel collector is primed to accept metrics, logs and traces on http://localhost:4317. Any code should use that as a target to send to.

## Extras

The deployment includes Heimdall, an application dashboard. To make use of it:

 - Navigate to
```bash
http://localhost:8091
```
 - Click Settings > Import > Browse
 - Select heimdall.json from the project directory and hit "Import"

 Now you have an application dashboard you can use for quick access.
