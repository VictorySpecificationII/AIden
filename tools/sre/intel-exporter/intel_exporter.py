"""Prometheus exporter for Intel accelerators, read from sysfs.

- NPU (intel_vpu driver): /sys/class/accel/accelN/device/
- GPU (i915 driver):      /sys/class/drm/cardN/ with PCI vendor 0x8086
  Busy time is derived in PromQL from the per-GT idle (RC6) residency counter:
  busy % = 100 * (1 - rate(intel_gpu_rc6_seconds_total[1m])).

The host's /sys is mounted read-only at SYSFS_ROOT. Values are read on every
scrape, so there is no polling loop and no state. Standard library only.
"""
import glob
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

SYSFS_ROOT = os.environ.get("SYSFS_ROOT", "/host/sys")
PORT = int(os.environ.get("INTEL_EXPORTER_PORT", "9101"))

# sysfs file -> (metric name, type, help, scale)
NPU_METRICS = {
    "npu_busy_time_us": ("npu_busy_time_seconds_total", "counter", "Total time the NPU has been busy", 1e-6),
    "npu_current_frequency_mhz": ("npu_frequency_mhz", "gauge", "Current NPU frequency in MHz", 1),
    "npu_max_frequency_mhz": ("npu_max_frequency_mhz", "gauge", "Maximum NPU frequency in MHz", 1),
    "npu_memory_utilization": ("npu_memory_used_bytes", "gauge", "Memory allocated by the NPU in bytes", 1),
}

# per-GT sysfs file (under cardN/gt/gtM/) -> (metric name, type, help, scale)
GPU_GT_METRICS = {
    "rc6_residency_ms": ("intel_gpu_rc6_seconds_total", "counter", "Total time the GT has spent idle (RC6)", 1e-3),
    "rps_act_freq_mhz": ("intel_gpu_frequency_mhz", "gauge", "Actual GT frequency in MHz", 1),
    "rps_max_freq_mhz": ("intel_gpu_max_frequency_mhz", "gauge", "Maximum GT frequency in MHz", 1),
}


def read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def header(lines, name, kind, help_text):
    lines += [f"# HELP {name} {help_text}", f"# TYPE {name} {kind}"]


def collect_npu(lines):
    devices = sorted(glob.glob(os.path.join(SYSFS_ROOT, "class/accel/accel*/device")))
    header(lines, "npu_up", "gauge", "Whether an NPU device was found")
    lines.append(f"npu_up {1 if devices else 0}")

    for sysfs_file, (name, kind, help_text, scale) in NPU_METRICS.items():
        header(lines, name, kind, help_text)
        for dev in devices:
            value = read(os.path.join(dev, sysfs_file))
            if value is not None:
                lines.append(f'{name}{{device="{dev.split("/")[-2]}"}} {round(int(value) * scale, 6)}')

    header(lines, "npu_runtime_active", "gauge", "Whether the NPU is powered up (1) or runtime-suspended (0)")
    for dev in devices:
        status = read(os.path.join(dev, "power/runtime_status"))
        if status is not None:
            lines.append(f'npu_runtime_active{{device="{dev.split("/")[-2]}"}} {1 if status == "active" else 0}')


def collect_gpu(lines):
    cards = [c for c in sorted(glob.glob(os.path.join(SYSFS_ROOT, "class/drm/card[0-9]*")))
             if "-" not in os.path.basename(c) and read(os.path.join(c, "device/vendor")) == "0x8086"
             and os.path.isdir(os.path.join(c, "gt"))]
    header(lines, "intel_gpu_up", "gauge", "Whether an Intel GPU (i915) was found")
    lines.append(f"intel_gpu_up {1 if cards else 0}")

    for sysfs_file, (name, kind, help_text, scale) in GPU_GT_METRICS.items():
        header(lines, name, kind, help_text)
        for card in cards:
            for gt in sorted(glob.glob(os.path.join(card, "gt/gt*"))):
                value = read(os.path.join(gt, sysfs_file))
                if value is not None:
                    labels = f'card="{os.path.basename(card)}",gt="{os.path.basename(gt)}"'
                    lines.append(f"{name}{{{labels}}} {round(int(value) * scale, 6)}")


def collect():
    lines = []
    collect_npu(lines)
    collect_gpu(lines)
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
