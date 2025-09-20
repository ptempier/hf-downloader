# Multi-Process Architecture Migration

## Changes Made

### 1. **New Files Created:**
- `app_multiprocess.py` - Main orchestrator with 4 processes
- `download_manager.py` - Download/delete operations process  
- `monitor_service.py` - File system monitoring process
- `start_direct.sh` - Direct startup script (alternative)

### 2. **Updated Files:**

#### `start_gunicorn.sh`
- **Before**: Started Gunicorn with workers/threads
- **After**: Starts multi-process Python application directly
- **Change**: Now calls `python3 app_multiprocess.py`

#### `requirements.txt` 
- **Before**: Included `gunicorn==21.2.0`
- **After**: Removed Gunicorn dependency
- **Reason**: No longer using Gunicorn, pure Python multiprocessing

#### `docker-compose.yml`
- **Before**: `GUNICORN_CMD_ARGS=--workers 2 --threads 8`
- **After**: Removed Gunicorn environment variables
- **Resources**: Increased CPU (2.0→4.0) and memory (4G→6G) for 4 processes

#### `Dockerfile`
- **Before**: Health check on `http://localhost:5000/`
- **After**: Health check on `http://localhost:5000/hf-downloader/`
- **Comment**: Added multi-process architecture notes

## Architecture Overview

### Old (Threading):
```
Single Process → Flask App → Background Threads
```

### New (Multi-Process):
```
Process 1: Flask Web Server (HTTP only)
Process 2: Download Manager (download/delete ops)  
Process 3: Monitoring Service (file system tracking)
Process 4: Status Processor (IPC coordination)
```

### IPC Communication:
- `task_queue`: Web Server → Download Manager
- `status_queue`: Download/Monitor → Status Processor
- `response_queue`: Download Manager → Status Processor  
- `monitor_requests_queue`: Status Processor → Monitor
- `manager.dict()`: Shared download status

## Benefits

✅ **No external dependencies** (Redis, SQLite, files)  
✅ **Process isolation** - no threading issues  
✅ **Better performance** - multi-core utilization  
✅ **Robust error handling** - process crash isolation  
✅ **Clean separation** - single responsibility per process

## Usage

Both startup methods work:
```bash
# Method 1: Updated startup script
./start_gunicorn.sh

# Method 2: Direct startup  
./start_direct.sh

# Method 3: Direct Python
python3 app_multiprocess.py
```

All methods start the same 4-process architecture with pure IPC communication.