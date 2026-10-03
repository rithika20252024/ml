FROM python:3.11-slim

LABEL maintainer="Business Entity Resolution Team"
LABEL description="Business Entity Resolution Pipeline - SageMaker Processing Job Container"

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create working directory
WORKDIR /opt/ml/code

# Install Python dependencies
COPY code/business_entity_resolution/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY code/business_entity_resolution/src/ ./src/

# SageMaker Processing expects entrypoint at /opt/ml/code/
ENV PYTHONPATH=/opt/ml/code

# Default entrypoint (overridden by SageMaker Processing job config)
ENTRYPOINT ["python", "src/run_pipeline.py"]
