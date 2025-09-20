#!/bin/bash

# HF Downloader - Multi-Process Startup Script

echo "🚀 Starting HF Downloader with Multi-Process Architecture..."
echo "📁 Working directory: $(pwd)"
echo "🐍 Python version: $(python3 --version)"

# Ensure directories exist
mkdir -p /models
mkdir -p /models/.cache

# Set environment variables
export HF_HUB_ENABLE_HF_TRANSFER=1

echo "🔧 Multi-Process Configuration:"
echo "   - Process 1: Flask Web Server (main)"
echo "   - Process 2: Download Manager"  
echo "   - Process 3: Monitoring Service"
echo "   - Process 4: Status Update Processor"
echo "   - Communication: IPC Queues (no files, no external services)"
echo ""

# Start the multi-process application
exec python3 app_multiprocess.py