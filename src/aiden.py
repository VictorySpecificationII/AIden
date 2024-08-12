from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from prometheus_client import CollectorRegistry, generate_latest, Counter, Histogram, Gauge
from api_copilot_llm import router as llm_router
from lib_copilot_telemetry import OpenTelemetryInstrumentor
import time
import psutil

app = FastAPI()

# Include the API routers
app.include_router(llm_router, prefix="/llm-text")

# Initialize the OpenTelemetryInstrumentor
instrumentor = OpenTelemetryInstrumentor(svc_name="main", instance_id="instance-00")

# Get logger and tracer from the instrumentor
logger = instrumentor.get_logger(logging_area="app_main")
tracer = instrumentor.get_tracer()

# Initialize metrics
registry = CollectorRegistry()
request_counter = Counter('http_requests_total', 'Total number of HTTP requests', registry=registry)
error_counter = Counter('http_error_total', 'Total number of HTTP errors', registry=registry)
latency_histogram = Histogram('http_request_latency_seconds', 'Request latency in seconds', registry=registry)

# Gauges for resource saturation
cpu_usage_gauge = Gauge('cpu_usage_percent', 'CPU usage percentage', registry=registry)
memory_usage_gauge = Gauge('memory_usage_percent', 'Memory usage percentage', registry=registry)
disk_usage_gauge = Gauge('disk_usage_percent', 'Disk usage percentage', registry=registry)
network_usage_gauge = Gauge('network_usage_bytes', 'Network I/O in bytes', registry=registry)


@app.middleware("http")
async def track_request_rate(request: Request, call_next):
    with tracer.start_as_current_span("request_tracking"):
        request_counter.inc()
        start_time = time.time()
        response = await call_next(request)
        request_latency = time.time() - start_time
        
        latency_histogram.observe(request_latency)  # Record latency
        if response.status_code >= 400:  # Check if the status code indicates an error
            error_counter.inc()  # Increment the error counter
        return response
    
@app.on_event("startup")
async def update_saturation_metrics():
    """
    Periodically update the saturation metrics.
    """
    import asyncio

    async def update_metrics():
        while True:
            # Update CPU usage
            cpu_usage_gauge.set(psutil.cpu_percent(interval=1))

            # Update memory usage
            memory_info = psutil.virtual_memory()
            memory_usage_gauge.set(memory_info.percent)

            # Update disk usage
            disk_info = psutil.disk_usage('/')
            disk_usage_gauge.set(disk_info.percent)

            # Update network I/O (total bytes sent/received)
            net_io = psutil.net_io_counters()
            network_usage_gauge.set(net_io.bytes_sent + net_io.bytes_recv)

            # Sleep for a few seconds before the next update
            await asyncio.sleep(5)

    # Run the metric updates in the background
    asyncio.create_task(update_metrics())

@app.get("/", tags=["Application Root"])
async def root(request: Request):
    with tracer.start_as_current_span("root-endpoint"):
        logger.info("Root endpoint accessed.")
        return {"message": "Welcome to AIden's FastAPI server."}

@app.get("/metrics", tags=["Metrics"], response_class=PlainTextResponse)
async def metrics():
    """
    Endpoint to expose metrics in Prometheus format.
    """
    return generate_latest(registry).decode("utf-8")

if __name__ == "__main__":
    import uvicorn
    from lib_copilot_startup_functions import print_banner

    print_banner()
    print("Starting AIden's FastAPI server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
