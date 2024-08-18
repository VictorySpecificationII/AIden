# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /api

# Copy the current directory contents into the container at /api
COPY . /api

# Install any dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the FastAPI port
EXPOSE 8000

# Run FastAPI application
CMD ["uvicorn", "aiden:api", "--host", "0.0.0.0", "--port", "8000"]
