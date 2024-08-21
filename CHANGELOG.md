# Changelog

## Version: 0.0.1
**Date:** 2024-08-16

### Changes:

1. **Metric Name Prefixing:**
   - Added the prefix `aiden_` to all custom metric names to make them easily identifiable in Prometheus.
   - Updated the following metric names:
     - `service_latency` → `aiden_service_latency`
     - `service_requests` → `aiden_service_requests`
     - `service_errors` → `aiden_service_errors`
     - `cpu_percent` → `aiden_cpu_percent`
     - `ram_percent` → `aiden_ram_percent`

2. **Refactoring for Deduplication:**
   - **Consolidated Metric, Logging, and Tracing Configuration:**
     - Merged the configuration of metrics, logs, and traces into a single `configure_opentelemetry()` function to avoid duplication and improve maintainability.
     - Unified the resource creation step for logs, metrics, and traces using a single `Resource` object, ensuring consistency across all telemetry data.
   - **Removed Redundant Middleware:**
     - Combined the previously separate middleware functions for tracing and metrics into a single `telemetry_middleware()` function, reducing code duplication and streamlining request handling.
   - **Logging Configuration Simplification:**
     - Moved all logging configuration into the `configure_opentelemetry()` function to ensure a single, unified logging setup, removing the need for multiple handlers or separate logger setups.

3. **Code Cleanup:**
   - **Simplified Imports:**
     - Removed unnecessary imports and streamlined the import section for better clarity and maintainability.

4. **Port Configuration Update:**
   - Changed the OTLP exporter port from `8888` to `8889` due to port `8888` being occupied. This change was necessary to prevent the OTLP collector from shutting down.

### TODO

- **Metrics Visibility:** Noted that metrics (`aiden_service_latency`, `aiden_service_requests`, and `aiden_service_errors`) may not appear in Prometheus until API endpoints are invoked. Ensure to execute API requests to see metrics data.

---

## Version: 0.0.2
**Date:** 2024-08-18

### Changes:

1. **Build Process Update:**
   - Added the image name to the build process for better identification and management during deployment.

2. **Service Renaming:**
   - Renamed the tracing service from `tracing-service` to `aiden-api` for consistency with other service names.

3. **Jaeger Integration and Configuration:**
   - Enabled the OpenTelemetry (OTel) collector on Jaeger with gRPC on port `4320` and HTTP on port `4321`.
   - Modified the OTel configuration to include Jaeger.

4. **Grafana Addition:**
   - Added Grafana to the Docker Compose setup for enhanced monitoring and visualization.

5. **Removal of Tempo and MinIO:**
   - **Tempo:** Removed Tempo from the Docker setup due to unresolved issues and the decision to simplify the tracing setup.
   - **MinIO:** Removed MinIO from the Docker setup, including its associated configuration and access keys, to streamline the services being managed.

6. **Jaeger Setup Adjustments:**
   - Removed Jaeger from the setup, later re-added it to the Docker Compose configuration along with the OTLP exporter in the OTel collector configuration.
   - Removed a duplicate Jaeger entry in the Docker Compose file.
   - Documented the OTLP exporter configuration in the setup.

7. **Prometheus and Networking Configuration:**
   - Added a Prometheus server to the Jaeger configuration.
   - Modified the Prometheus configuration for better integration.
   - Adjusted the Docker network mode to `host` for enhanced network handling.
   - Commented out unnecessary network entries in the Docker Compose file.

### Summary:
This update focuses on refining the tracing and monitoring setup by integrating Jaeger more tightly with the OpenTelemetry collector and adding Grafana for visualization. Tempo and MinIO were removed from the Docker setup to reduce complexity and focus on core services. The tracing service has been renamed for consistency, and several configurations have been fine-tuned to ensure smooth operation across the environment.

---

## Version: 0.0.3
**Date:** 2024-08-21

### Changes:

1. **Logstash Integration:**
   - **Added OTLP HTTP Exporter for Logstash:**
     - Configured the OpenTelemetry Collector to export logs via OTLP over HTTP to Logstash.
     - Updated the Logstash endpoint configuration in the OpenTelemetry Collector to `http://logstash:5045`.

2. **Configuration Fixes:**
   - **Updated OTLP Exporter Configuration:**
     - Corrected the OTLP exporter configuration for HTTP in the OpenTelemetry Collector, ensuring proper communication with Logstash.
   - **Resolved Endpoint Issues:**
     - Adjusted the endpoint path and simplified it to `http://logstash:5045` to resolve errors related to unsupported protocol schemes and connection resets.
   - **Adjusted Logstash Input Configuration:**
     - Verified and updated the Logstash HTTP input plugin configuration to match the expected data format and port.

3. **Debugging and Validation:**
   - **Verified Connectivity:**
     - Confirmed successful data transmission from the OpenTelemetry Collector to Logstash.
   - **Resolved `Connection Reset by Peer` Error:**
     - Addressed network and configuration issues that caused intermittent connection resets, ensuring stable data flow.

4. **ELK Stack Deployment:**
   - **Deployed ELK Stack:**
     - Successfully deployed Elasticsearch, Logstash, and Kibana as part of the observability stack.
   - **Set Memory Limits:**
     - Configured memory limits to `512MB` for each ELK stack service to manage resource usage and improve stability.

5. **Heimdall Application Panel:**
   - **Added Heimdall Panel:**
     - Integrated a Heimdall application panel into the stack for centralized navigation.
     - Added a JSON file for Heimdall configuration, which users can manually import via the Heimdall UI to access a centralized point for navigating the observability stack.

6. **Docker Compose and Configuration Cleanup:**
   - **Removed MinIO and Tempo Entries:**
     - Removed MinIO and Tempo services from the Docker Compose file to simplify the setup.
   - **Cleaned Up Tempo Configuration:**
     - Removed Tempo-related configuration from the `otel-collector-config.yaml` to tidy up and streamline the setup.

7. **Documentation and Summary Updates:**
   - **Updated Summary:**
     - Documented recent fixes, configuration updates, ELK stack deployment, the addition of the Heimdall panel, and the cleanup of unused services and configurations to ensure accurate reflection of the current observability setup.

### TODO

- **Metrics Visibility:** Noted that metrics (`aiden_service_latency`, `aiden_service_requests`, and `aiden_service_errors`) may not appear in Prometheus until API endpoints are invoked. Ensure to execute API requests to see metrics data.
- **Log Formatting:** Logs need to be formatted better through a Logstash pipeline to ensure they are properly structured and easier to analyze.
