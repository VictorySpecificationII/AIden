Run docker run \
    -p 4317:4317 \
    -v $(pwd)/otel-collector-config.yaml:/etc/otelcol-contrib/config.yaml \
    otel/opentelemetry-collector-contrib:latest

Run python3 otel-telemetry-test.py

The resulting logs will appear in the container output from the collector