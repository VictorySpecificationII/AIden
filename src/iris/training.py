import torch
import os
import shutil
import mlflow
import transformers
import boto3
from datasets import load_dataset, load_from_disk
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    Trainer,
    TrainingArguments,
)
from mlflow.tracking import MlflowClient

print("CUDA available:", torch.cuda.is_available())
print("GPU:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "No GPU")
print("Transformers version:", transformers.__version__)

# --- Config ---
MODEL_NAME = "HuggingFaceTB/SmolLM-135M"
EXPERIMENT_NAME = "smollm-finetune"
dataset_name = "Abirate/english_quotes"
S3_ENDPOINT = "http://localhost:9000"
S3_BUCKET = "mlflow"  # <-- Use mlflow bucket here
S3_PREFIX = "english_quotes"
LOCAL_DATA_DIR = "/tmp/ml_data"
RUN_DIR = "/tmp/smollm_run"
ARTIFACTS_DIR = os.path.join(RUN_DIR, "model-artifacts")
RESULTS_DIR = os.path.join(RUN_DIR, "training-results")
LOGS_DIR = os.path.join(RUN_DIR, "training-logs")

os.makedirs(ARTIFACTS_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# --- Download dataset ---
dataset = load_dataset(dataset_name)
dataset.save_to_disk(LOCAL_DATA_DIR)

# --- Upload dataset to MinIO ---
s3 = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id="minioadmin",
    aws_secret_access_key="minioadmin",
)

def upload_dir_to_s3(local_dir, bucket, s3_prefix=""):
    for root, _, files in os.walk(local_dir):
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, local_dir)
            s3_key = os.path.join(s3_prefix, rel_path).replace("\\", "/")
            s3.upload_file(full_path, bucket, s3_key)

try:
    s3.head_bucket(Bucket=S3_BUCKET)
except Exception:
    s3.create_bucket(Bucket=S3_BUCKET)

upload_dir_to_s3(LOCAL_DATA_DIR, S3_BUCKET, s3_prefix=S3_PREFIX)

# --- Re-download dataset from MinIO ---
def download_dataset_from_minio(bucket, prefix, target_dir):
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            local_path = os.path.join(target_dir, os.path.relpath(key, prefix))
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            s3.download_file(bucket, key, local_path)

download_dataset_from_minio(S3_BUCKET, S3_PREFIX, LOCAL_DATA_DIR)
dataset = load_from_disk(LOCAL_DATA_DIR)

# --- Tokenize ---
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
tokenizer.pad_token = tokenizer.eos_token

def tokenize(batch):
    tokens = tokenizer(batch["quote"], padding="max_length", truncation=True, max_length=128)
    tokens["labels"] = tokens["input_ids"].copy()
    return tokens

dataset = dataset.map(tokenize, batched=True)
dataset.set_format(type="torch", columns=["input_ids", "attention_mask", "labels"])

# --- Model & Training ---
model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)

training_args = TrainingArguments(
    output_dir=RESULTS_DIR,
    per_device_train_batch_size=2,
    num_train_epochs=2,
    logging_dir=LOGS_DIR,
    logging_steps=10,
    save_strategy="epoch",
    report_to="tensorboard",
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=dataset["train"].shuffle(seed=42).select(range(100)),
)

# --- Sync TensorBoard logs to flat prefix function ---
def sync_tensorboard_logs_to_flat_prefix(bucket, experiment_id, run_id, s3_client):
    source_prefix = f"{experiment_id}/{run_id}/artifacts/training-logs/"
    dest_prefix = f"tensorboard-logs/{run_id}/"

    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=source_prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            relative_path = key[len(source_prefix):]  # path under training-logs/
            dest_key = dest_prefix + relative_path

            print(f"Copying s3://{bucket}/{key} to s3://{bucket}/{dest_key}")

            copy_source = {'Bucket': bucket, 'Key': key}
            s3_client.copy_object(CopySource=copy_source, Bucket=bucket, Key=dest_key)

# --- MLflow Logging ---
mlflow.set_tracking_uri("http://localhost:5000")
mlflow.set_experiment(EXPERIMENT_NAME)

with mlflow.start_run() as run:
    mlflow.log_param("model_name", MODEL_NAME)
    mlflow.log_param("epochs", training_args.num_train_epochs)

    trainer.train()

    model.save_pretrained(ARTIFACTS_DIR)
    tokenizer.save_pretrained(ARTIFACTS_DIR)

    mlflow.log_artifacts(ARTIFACTS_DIR, artifact_path="model-artifacts")
    mlflow.log_artifacts(RESULTS_DIR, artifact_path="training-results")
    mlflow.log_artifacts(LOGS_DIR, artifact_path="training-logs")

    # Sync TensorBoard logs to flat prefix for easier TensorBoard consumption
    run_id = run.info.run_id
    experiment_id = run.info.experiment_id
    sync_tensorboard_logs_to_flat_prefix(S3_BUCKET, experiment_id, run_id, s3)

    # --- Register the model in MLflow Model Registry ---


    logged_model_uri = f"runs:/{run_id}/model-artifacts"
    model_name = "smollm-english-quotes"
    mlflow.register_model(logged_model_uri, model_name)

    client = MlflowClient()
    latest_version = client.get_latest_versions(model_name, stages=["None"])[0].version
    client.transition_model_version_stage(
        name=model_name,
        version=latest_version,
        stage="Staging",
    )

    print(f"Model registered as '{model_name}' version {latest_version} and moved to 'Staging'")
    
# Optional: remove temporary dirs after logging
shutil.rmtree(RUN_DIR)
shutil.rmtree(LOCAL_DATA_DIR)

import subprocess
from pathlib import Path

# --- Prepare for GGUF conversion ---
LLAMACPP_DIR = "/home/achristofi/Desktop/AIden/tools/mlops/llama.cpp"
LLAMACPP_CONVERTER = "/home/achristofi/Desktop/AIden/tools/mlops/llama.cpp/convert_hf_to_gguf.py"
GGUF_DIR = "/tmp/gguf_convert"
GGUF_OUTPUT = f"{GGUF_DIR}/smollm.gguf"

os.makedirs(GGUF_DIR, exist_ok=True)

# --- Clone llama.cpp if not present ---
if not os.path.exists(LLAMACPP_CONVERTER):
    print("📥 Cloning llama.cpp for GGUF conversion...")
    subprocess.run([
        "git", "clone", "--depth", "1", "https://github.com/ggml-org/llama.cpp.git", LLAMACPP_DIR
    ], check=True)
else:
    print("✔️ llama.cpp already present")

os.makedirs(GGUF_DIR, exist_ok=True)

# Download latest model artifacts from MLflow
client = MlflowClient()
runs = client.search_runs(experiment_ids=[experiment_id], order_by=["start_time DESC"], max_results=1)
latest_run = runs[0]
model_artifact_path = client.download_artifacts(latest_run.info.run_id, "model-artifacts", GGUF_DIR)

# Convert to GGUF format
try:
    subprocess.run([
        "python3",
        LLAMACPP_CONVERTER,
        model_artifact_path,                   # Path to HF model
        "--outfile", GGUF_OUTPUT,
        "--outtype", "q8_0"
    ], check=True)
    print(f"✅ GGUF model written to {GGUF_OUTPUT}")
except subprocess.CalledProcessError as e:
    print(f"❌ GGUF conversion failed: {e}")
finally:
    if os.path.exists(LLAMACPP_DIR):
        print("🧹 Cleaning up llama.cpp repo...")
        shutil.rmtree(LLAMACPP_DIR, ignore_errors=True)


s3.upload_file(GGUF_OUTPUT, S3_BUCKET, f"gguf/smollm.gguf")
print("✅ Uploaded GGUF to MinIO at gguf/smollm.gguf")

import os
import subprocess
from mlflow.tracking import MlflowClient

# --- Config ---
model_name = "smollm-gguf"
experiment_name = "smollm-finetune"
mlflow_uri = "http://localhost:5000"
mlflow.set_tracking_uri(mlflow_uri)
container_name = "ollama"  # Change this to your container name
container_dest_dir = "/root/ollama_build"
local_temp_dir = "/tmp/ollama_build"

os.makedirs(local_temp_dir, exist_ok=True)

import boto3

# --- Setup MinIO client ---
s3 = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id="minioadmin",
    aws_secret_access_key="minioadmin",
)

# --- Config ---
model_name = "smollm-gguf"
experiment_name = "smollm-finetune"
local_temp_dir = "/tmp/ollama_build"
os.makedirs(local_temp_dir, exist_ok=True)

# --- Download GGUF model directly from MinIO ---
gguf_s3_key = "gguf/smollm.gguf"
gguf_local_path = os.path.join(local_temp_dir, "smollm.gguf")

print(f"⬇️ Downloading GGUF model from MinIO s3://{S3_BUCKET}/{gguf_s3_key} to {gguf_local_path}")
s3.download_file(S3_BUCKET, gguf_s3_key, gguf_local_path)

if not os.path.exists(gguf_local_path):
    raise FileNotFoundError("GGUF model file not found after downloading from MinIO.")

# --- Write Modelfile ---
modelfile_path = os.path.join(local_temp_dir, "Modelfile")
with open(modelfile_path, "w") as f:
    f.write(f"""
from smollm.gguf
parameter temperature 0.7
parameter repeat_penalty 1.1
""".strip())

# --- Copy GGUF and Modelfile into the container ---
print("📦 Copying GGUF and Modelfile into container...")
subprocess.run(["docker", "exec", container_name, "mkdir", "-p", container_dest_dir], check=True)
subprocess.run(["docker", "cp", gguf_local_path, f"{container_name}:{container_dest_dir}/smollm.gguf"], check=True)
subprocess.run(["docker", "cp", modelfile_path, f"{container_name}:{container_dest_dir}/Modelfile"], check=True)

# --- Run ollama create inside the container ---
print("🚀 Creating Ollama model inside container...")
subprocess.run([
    "docker", "exec", container_name,
    "ollama", "create", model_name, "-f", f"{container_dest_dir}/Modelfile"
], check=True)

print(f"✅ Ollama model '{model_name}' created and registered.")