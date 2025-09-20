# Hugging Face Model Downloader & Manager

A Flask web interface for downloading and managing Hugging Face models with real-time progress tracking.

## Overview

- **Purpose**: Simple web interface to download HF models and manage them locally
- **Architecture**: Multi-process application with 4 dedicated processes and IPC communication
- **Deployment**: Supports subdirectory deployment (configurable via `base_url`)
- **Performance**: Solves threading issues through process isolation

## Features

- **Download**: HF models with quantization filters, real-time progress via HTTP polling
- **Management**: Browse, group, update, and delete models
- **Interface**: Two-page application (Download/Manage) with tab navigation
- **Real-time Updates**: HTTP polling for progress tracking (no external dependencies)

## Multi-Process Architecture

The application uses 4 separate processes for optimal performance:

1. **Web Server Process**: Flask server for the web interface
2. **Download Manager Process**: Handles HuggingFace download/delete operations  
3. **Monitor Service Process**: File system monitoring and progress calculation
4. **Status Processor Process**: State coordination and inter-process communication

**Communication**: Pure Python multiprocessing queues for complete isolation.

## Quick Start

### Option 1: Direct Python (Recommended)
```bash
# Install dependencies
pip install -r requirements.txt

# Create models directory
mkdir -p /models

# Run multi-process application
python3 app_multiprocess.py
```

### Option 2: Using startup script
```bash
./start.sh  # Multi-process startup script
# or
./start_direct.sh
```

### Option 3: Docker (Production)
```bash
# Using Docker Compose (recommended)
docker-compose up --build

# Or direct Docker build & run
docker build -t hf-downloader .
docker run -p 5000:5000 -v ./models:/models hf-downloader
```

Access: http://localhost:5000/hf-downloader/

## Project Structure

```
/
├── app_multiprocess.py    # Main orchestrator (multi-process)
├── download_manager.py    # Download operations process
├── monitor_service.py     # File monitoring process
├── utils.py               # Shared utilities and common functions
├── templates/
│   ├── index.html         # Download page (HTTP polling)
│   └── model_manager.html # Management page
├── start.sh               # Multi-process startup script
├── start_direct.sh        # Alternative startup script
├── docker-compose.yml     # Docker deployment config
├── Dockerfile             # Container definition
└── requirements.txt       # Python dependencies
```

## Architecture Migration

### Before (Threading Issues)
```
Single Process → Flask App → Background Threads
❌ time.sleep(1) taking 40+ seconds
❌ Resource conflicts and GIL issues
❌ Unreliable under load
```

### After (Multi-Process Solution)
```
Process 1: Flask Web Server (HTTP only)
Process 2: Download Manager (download/delete ops)  
Process 3: Monitoring Service (file system tracking)
Process 4: Status Processor (IPC coordination)
✅ Process isolation
✅ No external dependencies
✅ Reliable performance
```

## Configuration

### Base URL Configuration
Set in `app_multiprocess.py` for subdirectory deployment:
```python
base_url = "/hf-downloader"  # For https://example.com/hf-downloader/
base_url = ""                # For https://example.com/ (root)
```

### Models Directory
- **Location**: `/models/` (hardcoded)
- **Structure**: Organized by repository ID (e.g., `/models/microsoft/DialoGPT-small/`)
- **Cache**: Uses `/models/.cache` for HuggingFace cache

### Environment Variables
```bash
export HF_HUB_ENABLE_HF_TRANSFER=1  # Enable fast transfers
export HF_TOKEN=your_token_here     # Optional: for private models
```

## Key Files

### Backend (Multi-Process)
- **`app_multiprocess.py`**: Main orchestrator, process management, Flask routes
- **`download_manager.py`**: Download logic isolated in dedicated process
- **`monitor_service.py`**: Real-time file monitoring and progress calculation
- **`utils.py`**: Shared utilities and common functions across all modules

### Frontend  
- **Templates**: Dynamic path configuration based on `base_url`
- **JavaScript**: HTTP polling for real-time updates (replaces Socket.IO)

## API Endpoints

- `POST /download` - Start model download
- `GET /api/status` - Real-time status via HTTP polling
- `GET /api/models` - List downloaded models  
- `POST /api/models/update` - Update model
- `POST /api/models/delete` - Delete model

## Docker Deployment

### Docker Compose (Recommended)
```yaml
version: '3.8'
services:
  hf-downloader:
    image: hf-downloader:latest
    ports:
      - "5000:5000"
    volumes:
      - ./models:/models:rw
      - hf-cache:/home/appuser/.cache/huggingface
    environment:
      - HF_HUB_ENABLE_HF_TRANSFER=1
    deploy:
      resources:
        limits:
          cpus: '4.0'    # More CPU for 4 processes
          memory: 6G     # More memory for process isolation
```

### Build & Deploy
```bash
# Build image
docker build -t hf-downloader .

# Deploy with compose
docker-compose up -d

# View logs
docker-compose logs -f

# Scale resources if needed
docker-compose down
# Edit docker-compose.yml resources
docker-compose up -d
```

### Health Monitoring
- Health check: `http://localhost:5000/hf-downloader/`
- Container stats: `docker stats hf-model-downloader`
- Process monitoring: Built-in process health checks

## Development

### Requirements
```
Flask==2.3.3
huggingface_hub==0.17.3
hf_transfer==0.1.4
```

### Development vs Production
- **Development**: `python3 app_multiprocess.py`
- **Production**: Docker with resource limits and health checks

### Testing
Use the included test script:
```bash
python3 test_status.py
```

## Troubleshooting

### Common Issues

1. **Time.sleep() taking too long**
   - **Solution**: Use the multi-process architecture (`app_multiprocess.py`)
   - **Cause**: Resource contention in single-process version

2. **Port already in use**
   ```bash
   sudo lsof -i :5000
   # Kill process or change port in docker-compose.yml
   ```

3. **Permission denied on models directory**
   ```bash
   sudo chown -R 1000:1000 ./models
   chmod 755 ./models
   ```

4. **Process crashes**
   - Check logs: `docker-compose logs`
   - The multi-process architecture includes automatic process recovery

### Performance Optimization

1. **Resource Allocation**
   - Increase Docker CPU limits for better performance
   - Monitor memory usage with multiple processes

2. **Disk Space**
   - Large models can be 10-100+ GB
   - Monitor `/models` directory size
   - Use external storage if needed

3. **Network**
   - `HF_HUB_ENABLE_HF_TRANSFER=1` enables faster downloads
   - Consider bandwidth limits for multiple concurrent downloads

## Migration Notes

### From Single-Process to Multi-Process
- **Before**: Single-threaded Flask app with performance issues
- **Now**: `python3 app_multiprocess.py` (4-process isolation)
- **Benefits**: No more 40+ second delays, better resource utilization
- **Compatibility**: Same API endpoints, same Docker setup

### Removed Dependencies
- **Gunicorn**: No longer needed (pure Python multiprocessing)
- **Socket.IO**: Replaced with HTTP polling
- **External services**: No Redis, SQLite, or file-based communication

## Security Considerations

1. **Authentication**: Not included - add reverse proxy with auth if needed
2. **Network**: Limit port access to trusted networks
3. **File paths**: Built-in validation prevents directory traversal
4. **Docker**: Runs as non-root user (`appuser`)

## Backup & Recovery

### Backup Models
```bash
tar -czf models-backup-$(date +%Y%m%d).tar.gz ./models
```

### Restore Models  
```bash
tar -xzf models-backup-20231201.tar.gz
```

## Support

For issues related to:
- **Architecture**: Check process logs and IPC communication
- **Downloads**: Verify HuggingFace token and repository access
- **Performance**: Monitor resource usage across all 4 processes
- **Docker**: Check container logs and resource limits

The multi-process architecture provides better error isolation and recovery compared to the previous threading-based approach.

