#!/bin/bash
# Detect this machine's accelerators and configure AIden's compose profiles in .env.
#
# AIden decides by default and explains why: COMPOSE_PROFILES, the OpenWebUI
# backend URLs and the machine-specific group IDs are written to .env together
# with a comment saying what was detected. To keep your own choice, set
# AIDEN_PROFILES_MODE=manual in .env: the script then only reports.
#
# Usage: bootstrap/detect-profiles.sh [--dry-run]
set -euo pipefail

ENV_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.env"
DRY_RUN=false
[ "${1:-}" = "--dry-run" ] && DRY_RUN=true

# --- Detection -------------------------------------------------------------
found=()
nvidia=false; amd=false; intel_gpu=false; npu=false

if [ -e /dev/nvidia0 ] || nvidia-smi -L >/dev/null 2>&1; then
    nvidia=true; found+=("NVIDIA GPU")
fi

# Render nodes by PCI vendor: 0x8086 Intel, 0x1002 AMD
for node in /sys/class/drm/renderD*; do
    [ -e "$node/device/vendor" ] || continue
    case "$(cat "$node/device/vendor")" in
        0x8086) intel_gpu=true ;;
        0x1002) [ -e /dev/kfd ] && amd=true ;;
    esac
done
$intel_gpu && found+=("Intel GPU")
$amd && found+=("AMD GPU (no amd profile yet, using cpu)")

for accel in /sys/class/accel/accel*; do
    [ "$(basename "$(readlink -f "$accel/device/driver" 2>/dev/null)")" = "intel_vpu" ] && npu=true
done
$npu && found+=("Intel NPU")

# One Ollama backend (nvidia or cpu), plus the additive Intel profiles
profiles=()
if $nvidia; then profiles+=(nvidia); else profiles+=(cpu); fi
$npu && profiles+=(npu)
$intel_gpu && profiles+=(intel-gpu)

urls=(); keys=()
$npu && { urls+=("http://ovms-npu:8001/v3"); keys+=(unused); }
$intel_gpu && { urls+=("http://ovms-gpu:8002/v3"); keys+=(unused); }

render_gid=""
for dev in /dev/dri/renderD* /dev/accel/accel*; do
    [ -e "$dev" ] && { render_gid=$(stat -c %g "$dev"); break; }
done
docker_gid=$(getent group docker | cut -d: -f3 || true)

join() { local IFS="$1"; shift; echo "$*"; }
PROFILES=$(join , "${profiles[@]}")
URLS=$(join ";" "${urls[@]+"${urls[@]}"}")
KEYS=$(join ";" "${keys[@]+"${keys[@]}"}")
FOUND=$(join , "${found[@]+"${found[@]}"}")
FOUND=${FOUND:-no accelerators}

echo "Detected:         ${FOUND//,/, }"
echo "COMPOSE_PROFILES: $PROFILES"
echo "OpenWebUI URLs:   ${URLS:-(none)}"
echo "RENDER_GID:       ${render_gid:-(no render device)}"
echo "DOCKER_GID:       ${docker_gid:-(no docker group)}"

# --- Apply -----------------------------------------------------------------
if [ ! -f "$ENV_FILE" ]; then
    echo "No .env yet: create it first with  cp .env.example .env && chmod 600 .env" >&2
    exit 1
fi
if grep -q '^AIDEN_PROFILES_MODE=manual' "$ENV_FILE"; then
    echo "AIDEN_PROFILES_MODE=manual in .env: leaving your settings unchanged."
    exit 0
fi
if $DRY_RUN; then
    echo "--dry-run: .env not changed."
    exit 0
fi

# Replace KEY=... in place (or append), keeping the rest of .env untouched
set_var() {
    local key="$1" value="$2"
    if grep -q "^${key}=" "$ENV_FILE"; then
        python3 -I - "$ENV_FILE" "$key" "$value" <<'EOF'
import sys
path, key, value = sys.argv[1:]
lines = open(path).read().splitlines(keepends=True)
with open(path, "w") as f:
    for line in lines:
        f.write(f"{key}={value}\n" if line.startswith(f"{key}=") else line)
EOF
    else
        echo "${key}=${value}" >> "$ENV_FILE"
    fi
}

stamp="# detect-profiles.sh $(date -I): ${FOUND//,/, }"
python3 -I - "$ENV_FILE" "$stamp" <<'EOF'
import sys
path, stamp = sys.argv[1:]
lines = [l for l in open(path).read().splitlines(keepends=True) if not l.startswith("# detect-profiles.sh ")]
out = []
for line in lines:
    if line.startswith("COMPOSE_PROFILES="):
        out.append(stamp + "\n")
    out.append(line)
open(path, "w").writelines(out)
EOF
set_var COMPOSE_PROFILES "$PROFILES"
set_var OPENWEBUI_OPENAI_API_BASE_URLS "$URLS"
set_var OPENWEBUI_OPENAI_API_KEYS "$KEYS"
[ -n "$render_gid" ] && set_var RENDER_GID "$render_gid"
[ -n "$docker_gid" ] && set_var DOCKER_GID "$docker_gid"

echo "Updated $ENV_FILE. Apply with: docker compose up -d --remove-orphans"
