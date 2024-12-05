#!/bin/bash

# Function to check internet connectivity
check_internet() {
    # Try to ping a reliable server (Google DNS in this case) to check internet connectivity
    if ping -c 1 8.8.8.8 &> /dev/null; then
        echo "Internet is available."
        return 0
    else
        echo "No internet connectivity."
        return 1
    fi
}

# Function to generate an answer from the LLM in question
generate_response() {
  local model="$1"
  local prompt="$2"
  local stream="$3"
  local url="http://localhost:11434/api/generate"
  
  curl -X POST "$url" -d "{
    \"model\": \"$model\", 
    \"prompt\": \"$prompt\", 
    \"stream\": $stream
  }"
}

# Check if NVIDIA GPU is available
if command -v nvidia-smi &> /dev/null; then
    echo "NVIDIA GPU detected."
    mode="GPU"

    # Check for internet connectivity
    if check_internet; then
        echo "Downloading Ollama image from Docker registry..."
        docker pull ollama/ollama
        # Launch the container with GPU, mounting only the necessary directories
        docker run -d --gpus=all \
            -v ollama:/root/.ollama \
            -v "$PWD/smollm135/.ollama/models/blobs:/root/.ollama/models/blobs" \
            -v "$PWD/smollm135/.ollama/models/manifests:/root/.ollama/models/manifests" \
            -v "$PWD/smollm135/.ollama/id_ed25519:/root/.ollama/id_ed25519" \
            -v "$PWD/smollm135/.ollama/id_ed25519.pub:/root/.ollama/id_ed25519.pub" \
            -p 11434:11434 --name ollama ollama/ollama
    else
        echo "No internet, loading Ollama image from tar file..."
        if [ -f "ollama_image.tar" ]; then
            docker load -i ollama_image.tar
            # Launch the container with GPU, mounting only the necessary directories
            docker run -d --gpus=all \
                -v ollama:/root/.ollama \
                -v "$PWD/smollm135/.ollama/models/blobs:/root/.ollama/models/blobs" \
                -v "$PWD/smollm135/.ollama/models/manifests:/root/.ollama/models/manifests" \
                -v "$PWD/smollm135/.ollama/id_ed25519:/root/.ollama/id_ed25519" \
                -v "$PWD/smollm135/.ollama/id_ed25519.pub:/root/.ollama/id_ed25519.pub" \
                -p 11434:11434 --name ollama ollama/ollama
        else
            echo "Ollama image tar file (ollama_image.tar) not found in the current directory."
        fi
    fi
else
    echo "No NVIDIA GPU detected, launching Ollama in CPU-only mode..."
    mode="CPU"

    # Check for internet connectivity
    if check_internet; then
        echo "Downloading Ollama image from Docker registry..."
        docker pull ollama/ollama
        # Launch the container with CPU only, mounting only the necessary directories
        docker run -d \
            -v ollama:/root/.ollama \
            -v "$PWD/smollm135/.ollama/models/blobs:/root/.ollama/models/blobs" \
            -v "$PWD/smollm135/.ollama/models/manifests:/root/.ollama/models/manifests" \
            -v "$PWD/smollm135/.ollama/id_ed25519:/root/.ollama/id_ed25519" \
            -v "$PWD/smollm135/.ollama/id_ed25519.pub:/root/.ollama/id_ed25519.pub" \
            -p 11434:11434 --name ollama ollama/ollama
    else
        echo "No internet, loading Ollama image from tar file..."
        if [ -f "ollama_image.tar" ]; then
            docker load -i ollama_image.tar
            # Launch the container with CPU only, mounting only the necessary directories
            docker run -d \
                -v ollama:/root/.ollama \
                -v "$PWD/smollm135/.ollama/models/blobs:/root/.ollama/models/blobs" \
                -v "$PWD/smollm135/.ollama/models/manifests:/root/.ollama/models/manifests" \
                -v "$PWD/smollm135/.ollama/id_ed25519:/root/.ollama/id_ed25519" \
                -v "$PWD/smollm135/.ollama/id_ed25519.pub:/root/.ollama/id_ed25519.pub" \
                -p 11434:11434 --name ollama ollama/ollama
        else
            echo "Ollama image tar file (ollama_image.tar) not found in the current directory."
        fi
    fi
fi

# Report the mode (GPU or CPU)
echo "Ollama is running in $mode mode."

echo "Listing onboard LLM's..."
docker exec -it ollama ollama list

#Query LLM

#generate_response "smollm:135m" "Why is the sky blue?" false   # true for streaming, false to disable
