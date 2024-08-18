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
