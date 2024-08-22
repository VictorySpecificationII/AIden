# CHANGELOG

## Version: 0.0.1
**Date:** 2024-08-16

### Changes:
1. **Metric Name Prefixing:**
   - Added prefix `aiden_` to custom metric names for better identification in Prometheus.
   - Updated metric names:
     - `service_latency` → `aiden_service_latency`
     - `service_requests` → `aiden_service_requests`
     - `service_errors` → `aiden_service_errors`
     - `cpu_percent` → `aiden_cpu_percent`
     - `ram_percent` → `aiden_ram_percent`

2. **Refactoring for Deduplication:**
   - **Consolidated Configuration:**
     - Merged metrics, logs, and traces into a single `configure_opentelemetry()` function for improved maintainability.
     - Unified resource creation for logs, metrics, and traces with a single `Resource` object.
   - **Removed Redundant Middleware:**
     - Combined tracing and metrics middleware into `telemetry_middleware()` to reduce duplication.
   - **Logging Configuration Simplification:**
     - Moved all logging configuration into `configure_opentelemetry()` for a unified setup.

3. **Code Cleanup:**
   - **Simplified Imports:**
     - Removed unnecessary imports for better clarity and maintainability.

4. **Port Configuration Update:**
   - Changed OTLP exporter port from `8888` to `8889` to avoid conflict with port `8888`.

### TODO:
- **Metrics Visibility:** Metrics may not appear in Prometheus until API endpoints are invoked. Execute API requests to see metrics data.

---

## Version: 0.0.2
**Date:** 2024-08-18

### Changes:
1. **Build Process Update:**
   - Added image name to the build process for better deployment management.

2. **Service Renaming:**
   - Renamed tracing service from `tracing-service` to `aiden-api` for consistency.

3. **Jaeger Integration and Configuration:**
   - Enabled OTLP collector on Jaeger with gRPC on port `4320` and HTTP on port `4321`.
   - Modified OTel configuration to include Jaeger.

4. **Grafana Addition:**
   - Added Grafana to Docker Compose for enhanced monitoring.

5. **Removal of Tempo and MinIO:**
   - **Tempo:** Removed due to unresolved issues, simplifying the tracing setup.
   - **MinIO:** Removed to streamline services managed.

6. **Jaeger Setup Adjustments:**
   - Removed, then re-added Jaeger to Docker Compose with OTLP exporter configuration.
   - Removed duplicate Jaeger entry and documented OTLP exporter configuration.

7. **Prometheus and Networking Configuration:**
   - Added Prometheus server to Jaeger configuration.
   - Modified Prometheus configuration and adjusted Docker network mode to `host`.

### Summary:
Refined tracing and monitoring setup with Jaeger and Grafana, removed Tempo and MinIO to reduce complexity. Adjusted configurations for consistency and improved network handling.

---

## Version: 0.0.3
**Date:** 2024-08-21

### Changes:
1. **Logstash Integration:**
   - **Added OTLP HTTP Exporter:**
     - Configured OpenTelemetry Collector to export logs via OTLP over HTTP to Logstash.
     - Updated Logstash endpoint configuration to `http://logstash:5045`.

2. **Configuration Fixes:**
   - **Updated OTLP Exporter Configuration:**
     - Corrected OTLP exporter configuration for HTTP in OpenTelemetry Collector.
   - **Resolved Endpoint Issues:**
     - Simplified endpoint path to `http://logstash:5045` to address protocol and connection issues.
   - **Adjusted Logstash Input Configuration:**
     - Updated Logstash HTTP input plugin configuration for proper data format and port.

3. **Debugging and Validation:**
   - **Verified Connectivity:**
     - Confirmed successful data transmission from OpenTelemetry Collector to Logstash.
   - **Resolved `Connection Reset by Peer` Error:**
     - Addressed network and configuration issues causing connection resets.

4. **ELK Stack Deployment:**
   - **Deployed ELK Stack:**
     - Deployed Elasticsearch, Logstash, and Kibana.
   - **Set Memory Limits:**
     - Configured memory limits to `512MB` for each ELK stack service.

5. **Heimdall Application Panel:**
   - **Added Heimdall Panel:**
     - Integrated Heimdall panel for centralized navigation.
     - Added JSON file for Heimdall configuration.

6. **Docker Compose and Configuration Cleanup:**
   - **Removed MinIO and Tempo Entries:**
     - Removed services from Docker Compose file and cleaned up related configurations.

7. **Documentation and Summary Updates:**
   - **Updated Summary:**
     - Documented recent fixes, ELK stack deployment, Heimdall panel addition, and cleanup of unused services.

### TODO:
- **Metrics Visibility:** Metrics may not appear in Prometheus until API endpoints are invoked.
- **Log Formatting:** Improve log formatting through Logstash pipeline for better analysis.

---

## Version: 0.0.4
**Date:** 2024-08-22

### Changes:

1. **Alertmanager Container Deployment:**
   - **Deployment Configuration:**
     - Deployed the Alertmanager container using Docker Compose.
     - Configured the container with the image `prom/alertmanager:latest` and mapped port `9093` to the host.
     - Mounted the configuration file from the host to the container to manage Alertmanager settings.
   - **Configuration File:**
     - The Alertmanager configuration file was mounted to `/etc/alertmanager/alertmanager.yml` inside the container.
     - Adjusted the Docker Compose configuration to ensure proper mounting and file path alignment.
     - Example configuration file location on the host: `./alertmanager.yml`
     - Ensured the `--config.file=/config/alertmanager.yml` command-line argument in Docker Compose points to the correct configuration file path.

2. **Grafana Alerting Configuration:**
   - **Provisioned Alertmanager Datasource:**
     - Configured Grafana to use Alertmanager as a datasource with URL `http://alertmanager:9093`.
     - Attempted to specify Prometheus as the implementation for Alertmanager using `jsonData` with `implementation: prometheus`.
   - **Enabled “Receive Grafana Alerts” Option:**
     - Enabled the option to receive Grafana alerts in the Alertmanager datasource settings.
     - Investigated configuration for forwarding alerts from Grafana to Alertmanager.

3. **Provisioning Configurations:**
   - **Provisioned Datasources:**
     - Configured Grafana to auto-provision the following datasources:
       - Prometheus
       - Jaeger
       - Elasticsearch
       - Alertmanager
     - Ensured these datasources are properly set up and integrated with Grafana for monitoring and visualization.

### TODO:
- **Alertmanager Integration:** Finalize the integration of Alertmanager with Grafana and ensure proper alert forwarding.
- **Configuration Validation:** Validate and test configurations for Alertmanager, Prometheus, Jaeger, and Elasticsearch to ensure reliable operation.

---

## Version: 0.0.5
**Date:** 2024-08-22

### Changes:

1. **MLflow Integration:**
   - **Added MLflow:**
     - Integrated MLflow for model tracking.
     - Configured MLflow to use PostgreSQL as its database.
     - Set up MLflow to communicate with MinIO as its backing store.
   - **MinIO Configuration:**
     - Deployed MinIO to serve as the storage backend for MLflow.
     - Created an MLflow S3 bucket and configured access keys for communication with MinIO.

2. **Access Key Issue Fix:**
   - **Resolved Access Key Length Issue:**
     - Fixed issue where access key creation failed due to key length exceeding 20 characters.

3. **Configuration Refactoring:**
   - **Organized Configuration Files:**
     - Moved Logstash, Prometheus, Alertmanager, and OpenTelemetry Collector configuration files into their respective folders.
     - Updated Docker Compose configuration to reflect the new file locations and ensure proper setup.

### Validation:
- **MLflow and MinIO:** Verified MLflow’s integration with MinIO and PostgreSQL.
- **Configuration Testing:** Tested new configurations for Logstash, Prometheus, Alertmanager, and OpenTelemetry Collector to ensure proper functionality.
