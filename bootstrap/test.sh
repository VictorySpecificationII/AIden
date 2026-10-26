#!/bin/bash
# Run AIden's tests inside the aiden image (same Python and pinned dependencies as
# production), with pytest installed into a throwaway container. Nothing is installed
# on the host. Extra arguments go to pytest, e.g. bootstrap/test.sh -k mentor -v
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
docker compose build -q aiden
docker run --rm -v "$PWD":/repo:ro -w /repo --entrypoint sh intellectualplayspace/aiden -c \
  "pip install -q --disable-pip-version-check --user pytest==9.1.1 && python -m pytest $*"
