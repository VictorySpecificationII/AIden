FROM python:3.11-slim

# System dependencies (optional but good to have)
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install TensorFlow + TensorFlow I/O with S3 support + boto3
RUN pip install --no-cache-dir \
    tensorflow==2.15.0 \
    tensorflow-io[s3]==0.35.0 \
    boto3

EXPOSE 6006

# Entry command for TensorBoard (overridden by docker-compose if needed)
CMD ["tensorboard", "--logdir", "s3://mlflow/tensorboard-logs", "--host", "0.0.0.0"]