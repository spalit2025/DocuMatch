FROM python:3.12-slim

WORKDIR /app

# System dependencies for PDF processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p data/contracts data/invoices data/purchase_orders data/chroma_db logs

# Default environment
ENV OLLAMA_HOST=http://ollama:11434
ENV CHROMA_PERSIST_DIR=./data/chroma_db
ENV DB_PATH=./data/documatch.db

EXPOSE 8000 8501
