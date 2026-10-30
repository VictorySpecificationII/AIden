# model-steward: the OVMS image (for `ovms --pull`, which downloads a model and writes its
# serving graph) plus Python for the steward's small HTTP API.
FROM openvino/model_server:2026.4.1-gpu
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 \
 && apt-get clean && rm -rf /var/lib/apt/lists/*
COPY steward.py /app/steward.py
USER ovms
ENTRYPOINT ["python3", "/app/steward.py"]
