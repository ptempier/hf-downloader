# Hugging Face Model Downloader & Manager

A Flask web interface for downloading and managing Hugging Face models with real-time progress tracking.

## Features

- **Download**: HF models with quantization filters and real-time progress
- **Management**: Browse, group, update, and delete local models  
- **Architecture**: 4-process isolation for reliable performance
- **Real-time Updates**: HTTP polling (no external dependencies)

## Quick Start

```bash
docker build -t hf-downloader .
docker-compose up
```

Access: http://localhost:5000/hf-downloader/

## Architecture

Multi-process application with 4 dedicated processes:

```
Process 1: Flask Web Server (HTTP API)
Process 2: Download Manager (operations)  
Process 3: Monitoring Service (file tracking)
Process 4: Status Processor (coordination)
```

**Benefits**: Process isolation, no external dependencies, reliable performance

## Configuration

**Base URL**: Set in `app_multiprocess.py` for subdirectory deployment
```python
base_url = "/hf-downloader"  # For subdirectory
base_url = ""                # For root deployment
```

**Models Directory**: `/models/` (organized by repository ID)

**Environment Variables**:
```bash
export HF_HUB_ENABLE_HF_TRANSFER=1  # Fast transfers
export HF_TOKEN=your_token_here     # Private models (optional)
```

## API Endpoints

- `POST /download` - Start model download
- `GET /api/download/status` - Real-time status
- `GET /api/models` - List downloaded models  
- `POST /api/models/update` - Update model
- `POST /api/models/delete` - Delete model

## Testing

```bash
# Check status
curl http://localhost:5000/api/download/status

# Start download
curl -X POST http://localhost:5000/download \
  -H "Content-Type: application/json" \
  -d '{"repo_id":"microsoft/DialoGPT-small","quant_pattern":""}'
```

## Troubleshooting

**Port conflicts**:
```bash
sudo lsof -i :5000  # Check what's using port 5000
```

**Permissions**:
```bash
sudo chown -R 1000:1000 ./models
chmod 755 ./models
```

**Logs**: `docker-compose logs`

## Security Notes

- No built-in authentication (add reverse proxy if needed)
- Runs as non-root user in Docker
- Built-in path validation prevents directory traversal
- Limit port access to trusted networks

