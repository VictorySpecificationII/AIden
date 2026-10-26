"""Prometheus exporter for the Intel NPU (intel_vpu driver), read from sysfs.

The driver exposes its counters under /sys/class/accel/accelN/device/. The host's
/sys is mounted read-only at SYSFS_ROOT. Values are read on every scrape, so there
is no polling loop and no state. Standard library only.
"""
import glob
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

SYSFS_ROOT = os.environ.get("SYSFS_ROOT", "/host/sys")
PORT = int(os.environ.get("NPU_EXPORTER_PORT", "9101"))

# sysfs file -> (metric name, type, help, scale)
METRICS = {
    "npu_busy_time_us": ("npu_busy_time_seconds_total", "counter", "Total time the NPU has been busy", 1e-6),
    "npu_current_frequency_mhz": ("npu_frequency_mhz", "gauge", "Current NPU frequency in MHz", 1),
    "npu_max_frequency_mhz": ("npu_max_frequency_mhz", "gauge", "Maximum NPU frequency in MHz", 1),
    "npu_memory_utilization": ("npu_memory_used_bytes", "gauge", "Memory allocated by the NPU in bytes", 1),
}


def read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def collect():
    lines = []
    devices = sorted(glob.glob(os.path.join(SYSFS_ROOT, "class/accel/accel*/device")))
    lines += ["# HELP npu_up Whether an NPU device was found", "# TYPE npu_up gauge", f"npu_up {1 if devices else 0}"]

    for sysfs_file, (name, kind, help_text, scale) in METRICS.items():
        lines += [f"# HELP {name} {help_text}", f"# TYPE {name} {kind}"]
        for dev in devices:
            value = read(os.path.join(dev, sysfs_file))
            if value is not None:
                lines.append(f'{name}{{device="{dev.split("/")[-2]}"}} {int(value) * scale}')

    lines += ["# HELP npu_runtime_active Whether the NPU is powered up (1) or runtime-suspended (0)",
              "# TYPE npu_runtime_active gauge"]
    for dev in devices:
        status = read(os.path.join(dev, "power/runtime_status"))
        if status is not None:
            lines.append(f'npu_runtime_active{{device="{dev.split("/")[-2]}"}} {1 if status == "active" else 0}')

    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/metrics":
            self.send_error(404)
            return
        body = collect().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
