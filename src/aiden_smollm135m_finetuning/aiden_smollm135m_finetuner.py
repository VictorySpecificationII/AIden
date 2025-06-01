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

print("CUDA available:", torch.cuda.is_available())
print("GPU:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "No GPU")
print("Transformers version:", transformers.__version__)

# --- Config ---
MODEL_NAME = "HuggingFaceTB/SmolLM-135M"
EXPERIMENT_NAME = "smollm-finetune"
dataset_name = "Abirate/english_quotes"
S3_ENDPOINT = "http://localhost:9000"
S3_BUCKET = "huggingface-datasets"
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

# --- Upload to MinIO ---
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
except:
    s3.create_bucket(Bucket=S3_BUCKET)

upload_dir_to_s3(LOCAL_DATA_DIR, S3_BUCKET, s3_prefix=S3_PREFIX)

# --- Re-download dataset from S3 ---
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
    report_to="tensorboard",  # Enable TensorBoard
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=dataset["train"].shuffle(seed=42).select(range(100)),
)

# --- MLflow Logging ---
mlflow.set_tracking_uri("http://localhost:5000")
mlflow.set_experiment(EXPERIMENT_NAME)

with mlflow.start_run():
    mlflow.log_param("model_name", MODEL_NAME)
    mlflow.log_param("epochs", training_args.num_train_epochs)

    trainer.train()

    model.save_pretrained(ARTIFACTS_DIR)
    tokenizer.save_pretrained(ARTIFACTS_DIR)

    mlflow.log_artifacts(ARTIFACTS_DIR, artifact_path="model-artifacts")
    mlflow.log_artifacts(RESULTS_DIR, artifact_path="training-results")
    mlflow.log_artifacts(LOGS_DIR, artifact_path="training-logs")

# Optional: remove temporary dirs after logging
# shutil.rmtree(RUN_DIR)
