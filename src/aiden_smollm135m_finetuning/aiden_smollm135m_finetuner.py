import torch
import os
import shutil
import mlflow
import transformers
import boto3
from datasets import load_dataset
from datasets import load_from_disk
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
dataset_name = "Abirate/english_quotes"
local_path = "/tmp/ml_data"
bucket_name = "huggingface-datasets"

# --- Configuration ---
MODEL_NAME = "HuggingFaceTB/SmolLM-135M"
EXPERIMENT_NAME = "smollm-finetune"
S3_ENDPOINT = "http://localhost:9000"
S3_BUCKET = "huggingface-datasets"
S3_PREFIX = "english_quotes"
LOCAL_DATA_DIR = "/tmp/ml_data"

minio_endpoint = "http://localhost:9000"
minio_access_key = "minioadmin"
minio_secret_key = "minioadmin"

# --- Step 1: Download HuggingFace Dataset Locally ---
print(f"Downloading dataset {dataset_name}...")
dataset = load_dataset(dataset_name)
dataset.save_to_disk(local_path)
print(f"Saved to: {local_path}")

# --- Step 2: Connect to MinIO ---
s3 = boto3.client(
    "s3",
    endpoint_url=minio_endpoint,
    aws_access_key_id=minio_access_key,
    aws_secret_access_key=minio_secret_key,
)

# --- Step 3: Create bucket if not exists ---
try:
    s3.head_bucket(Bucket=bucket_name)
    print(f"Bucket {bucket_name} already exists.")
except:
    s3.create_bucket(Bucket=bucket_name)
    print(f"Created bucket {bucket_name}.")

# --- Step 4: Upload files to MinIO ---
def upload_dir_to_s3(local_dir, bucket, s3_prefix=""):
    for root, dirs, files in os.walk(local_dir):
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, local_dir)
            s3_key = os.path.join(s3_prefix, rel_path).replace("\\", "/")
            s3.upload_file(full_path, bucket, s3_key)
            print(f"Uploaded: {s3_key}")

upload_dir_to_s3(local_path, bucket_name, s3_prefix="english_quotes")

# --- Connect to MinIO (S3-compatible) ---
s3 = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id="minioadmin",
    aws_secret_access_key="minioadmin",
)

def download_dataset_from_minio(bucket, prefix, target_dir):
    print(f"Downloading dataset from s3://{bucket}/{prefix} to {target_dir}")
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            local_path = os.path.join(target_dir, os.path.relpath(key, prefix))
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            s3.download_file(bucket, key, local_path)
            print(f"✔ Downloaded: {key} → {local_path}")

# --- Download and Load Dataset ---
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

# --- Load Model ---
model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)

# --- Training Args ---
training_args = TrainingArguments(
    output_dir="/tmp/results",
    per_device_train_batch_size=2,
    num_train_epochs=2,
    logging_dir="/tmp/logs",
    logging_steps=10,
    save_strategy="epoch",
    report_to="none",
)

# --- Trainer ---
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=dataset["train"].shuffle(seed=42).select(range(100)),
)

# --- MLflow Setup ---
mlflow.set_tracking_uri("http://localhost:5000")
mlflow.set_experiment(EXPERIMENT_NAME)

with mlflow.start_run():
    mlflow.log_param("model_name", MODEL_NAME)
    mlflow.log_param("epochs", training_args.num_train_epochs)

    trainer.train()

    # Save locally first
    model.save_pretrained("artifacts")
    tokenizer.save_pretrained("artifacts")

    # Upload artifacts and results to MLflow (MinIO)
    mlflow.log_artifacts("artifacts", artifact_path="model-artifacts")
    mlflow.log_artifacts("/tmp/results", artifact_path="training-results")

    # Clean up local directories after upload
    shutil.rmtree("artifacts")
    shutil.rmtree("/tmp/results")