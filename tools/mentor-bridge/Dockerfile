# AIden's mentor bridge: the Claude Code CLI plus a small stdlib HTTP service.
# Authenticates with a long-lived subscription token (CLAUDE_CODE_OAUTH_TOKEN, created
# with `claude setup-token` on the host); the host's ~/.claude is never mounted.
FROM node:22.20.0-slim

ARG CLAUDE_CODE_VERSION=2.1.296

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && npm install -g --no-fund --no-audit "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
 && npm cache clean --force \
 && useradd --create-home --uid 10010 mentor

# Pinned version: no self-updates; no telemetry or error reporting
ENV DISABLE_AUTOUPDATER=1 \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
    MENTOR_BIND=0.0.0.0

COPY mentor_bridge.py /app/mentor_bridge.py
USER mentor
WORKDIR /home/mentor
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python3 -c "import os, urllib.request; urllib.request.urlopen(urllib.request.Request('http://localhost:8765/health', headers={'X-Mentor-Token': os.environ['MENTOR_TOKEN']}), timeout=3)"

CMD ["python3", "-I", "/app/mentor_bridge.py"]
