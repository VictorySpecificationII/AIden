import torch
import os
import mlflow
import transformers
import boto3
from datasets import load_dataset

print("CUDA available:", torch.cuda.is_available())
print("GPU:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "No GPU")
print("Transformers version:",transformers.__version__)


# --- Config ---
dataset_name = "Abirate/english_quotes"
local_path = "/tmp/ml_data"
bucket_name = "huggingface-datasets"

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