# HF Downloader - Gunicorn Setup

## Quick Start

### Option 1: Using the startup script (Recommended)
```bash
./start_gunicorn.sh
```

### Option 2: Direct Gunicorn command
```bash
gunicorn app:app --config gunicorn.conf.py
```

### Option 3: Simple Gunicorn command
```bash
gunicorn app:app \
    --bind 0.0.0.0:5000 \
    --workers 1 \
    --threads 8 \
    --timeout 300 \
    --worker-class gthread \
    --access-logfile - \
    --error-logfile -
```

## Why Gunicorn?

Gunicorn solves the threading issues with Flask's development server:

- **Better thread management**: Proper isolation between request threads
- **GIL handling**: More efficient Python GIL management
- **Production ready**: Designed for concurrent workloads
- **Configurable timeouts**: Handle long-running downloads properly
- **Worker management**: Automatic recovery from worker failures

## Configuration

- **Workers**: 1 (single worker to avoid download conflicts)
- **Threads**: 8 (allows 8 concurrent HTTP requests)
- **Timeout**: 300s (5 minutes for long downloads)
- **Worker class**: gthread (threading worker)

## Development vs Production

- **Development**: `python app.py` (Flask dev server)
- **Production**: `./start_gunicorn.sh` (Gunicorn server)

## Docker

The Docker container now uses Gunicorn by default:
```bash
docker run -p 5000:5000 -v /models:/models hf-downloader
```

## Troubleshooting

If you get import errors:
```bash
pip install gunicorn==21.2.0
```

If port 5000 is busy:
```bash
gunicorn app:app --bind 0.0.0.0:8000
```