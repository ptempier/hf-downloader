#!/bin/bash

# Direct startup script for multi-process HF Downloader
# Alternative to Gunicorn startup

echo "🚀 Starting HF Downloader - Direct Multi-Process Mode"

# Ensure directories exist
mkdir -p /models
mkdir -p /models/.cache

# Set environment variables
export HF_HUB_ENABLE_HF_TRANSFER=1

# Run the multi-process application directly
python3 app_multiprocess.py