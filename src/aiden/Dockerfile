FROM python:3.11-slim AS base

# Use non-root user for security
ENV USER=appuser \
    HOME=/home/appuser \
    APP_HOME=/app

# Create non-root user and set up environment
RUN useradd --create-home --home-dir $HOME $USER

WORKDIR $APP_HOME

# Install dependencies with no cache to keep image lean
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
 && pip install --no-cache-dir -r requirements.txt \
 && apt-get remove -y build-essential gcc \
 && apt-get autoremove -y \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Copy source code
COPY . .

# Set file permissions
RUN chown -R $USER:$USER $APP_HOME
USER $USER

# Run the app
CMD ["uvicorn", "aiden:app", "--host", "0.0.0.0", "--port", "8000"]