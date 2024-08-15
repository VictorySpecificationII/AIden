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

**Summary:** This update not only improves the identification of metrics in Prometheus by adding the `aiden_` prefix but also refactors the code to remove duplicate telemetry configurations. The refactoring ensures that all metrics, logs, and traces share a consistent configuration, reducing potential errors and making the code easier to maintain. The middleware for handling telemetry data has also been consolidated to simplify request processing.
