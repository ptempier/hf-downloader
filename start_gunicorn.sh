#!/bin/bash

# HF Downloader - Gunicorn Startup Script

echo "🚀 Starting HF Downloader with Gunicorn..."
echo "📁 Working directory: $(pwd)"
echo "🐍 Python version: $(python3 --version)"

# Check if gunicorn is installed
if ! command -v gunicorn &> /dev/null; then
    echo "❌ Gunicorn not found. Installing..."
    pip3 install gunicorn==21.2.0
fi

# Ensure directories exist
mkdir -p /models
mkdir -p /models/.cache

# Set environment variables
export HF_HUB_ENABLE_HF_TRANSFER=1

echo "🔧 Configuration:"
echo "   - Workers: 1 (single worker to avoid download conflicts)"
echo "   - Threads: 8 (concurrent request handling)"
echo "   - Timeout: 300s (for long downloads)"
echo "   - Bind: 0.0.0.0:5000"
echo ""

# Start Gunicorn
exec gunicorn \
    --config gunicorn.conf.py \
    app:app

# Alternative simple command (if config file has issues):
# exec gunicorn app:app \
#     --bind 0.0.0.0:5000 \
#     --workers 1 \
#     --threads 8 \
#     --timeout 300 \
#     --worker-class gthread \
#     --access-logfile - \
#     --error-logfile - \
#     --log-level info