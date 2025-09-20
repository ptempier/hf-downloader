# Use Python 3.11 slim image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HUB_ENABLE_HF_TRANSFER=1 \
    DEBIAN_FRONTEND=noninteractive

# Set working directory
WORKDIR /app

# Only the essentials — no build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code (multi-process architecture)
COPY *.py ./
COPY *.sh ./
COPY templates/ ./templates/
RUN chmod +x *.sh
#COPY static/ ./static/

# Create models directory
RUN mkdir -p /models && chmod 755 /models

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app /models

USER appuser

# Expose ports
EXPOSE 5000

# Health check - updated for multi-process app
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/hf-downloader/ || exit 1

# Default command runs multi-process architecture (no Gunicorn needed)
# Use start_gunicorn.sh (updated for multi-process) or start_direct.sh
CMD ["./start_gunicorn.sh"]

# Alternative direct startup (uncomment to use):
# CMD ["./start_direct.sh"]
