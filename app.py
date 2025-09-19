#!/usr/bin/env python3

# eventlet must monkey-patch the stdlib before other libraries (Flask/werkzeug)
import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
import os
import traceback
import sys
import threading
import time
import shutil
import datetime
import re
from collections import defaultdict
from pathlib import Path
from huggingface_hub import snapshot_download
from huggingface_hub.utils import HfHubHTTPError

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'

# CONFIGURATION
base_url = "/hf-downloader"   # Set this to your actual base URL path

# Configure Socket.IO - use base_url for custom path
socketio_path = f"{base_url}/socket.io" if base_url else "/socket.io"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', path=socketio_path)

# Set HF_TRANSFER for faster downloads
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"

# ============== SHARED UTILITIES ==============

def get_file_size_from_bytes(size_bytes):
    """Convert bytes to human readable format"""
    if size_bytes == 0:
        return '0 B'
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

def validate_repo_id(repo_id):
    """Validate repository ID format"""
    if not repo_id or not isinstance(repo_id, str):
        return False
    if '/' not in repo_id or ' ' in repo_id:
        return False
    parts = repo_id.split('/')
    if len(parts) != 2 or not all(parts):
        return False
    return True

def validate_model_path(model_path):
    """Validate that the model path is safe to delete"""
    if not model_path or not isinstance(model_path, str):
        return False
    if not model_path.startswith('/models/'):
        return False
    normalized_path = os.path.normpath(model_path)
    if not normalized_path.startswith('/models/') or normalized_path in ['/models', '/models/']:
        return False
    return True

# ============== DOWNLOAD MANAGEMENT ==============

# Global download status
download_status = {
    "progress": 0, 
    "status": "idle", 
    "current_file": "",
    "downloaded_files": 0,
    "repo_id": "",
    "start_time": None
}

def update_download_status(**kwargs):
    """Thread-safe update of download status with auto-emit"""
    global download_status
    download_status.update(kwargs)
    
    # Calculate ETA
    if download_status.get('start_time') and download_status.get('progress', 0) > 0:
        elapsed = time.time() - download_status['start_time']
        if download_status['progress'] > 0:
            eta = (elapsed / download_status['progress']) * (100 - download_status['progress'])
            download_status['eta'] = eta
    
    try:
        socketio.emit('download_progress', download_status.copy())
        print(f"✅ Emitted download_progress: {download_status.get('progress', 0):.1f}% - {download_status.get('current_file', '')}")
    except Exception as e:
        print(f"❌ Failed to emit progress: {e}")

def download_with_progress(repo_id, local_dir, allow_patterns):
    """Download with real-time progress monitoring"""
    
    download_exception = [None]
    
    def download_thread():
        try:
            snapshot_download(
                repo_id=repo_id,
                local_dir=local_dir,
                allow_patterns=allow_patterns,
                resume_download=True,
                local_dir_use_symlinks=False
            )
        except Exception as e:
            download_exception[0] = e
    
    # Start download in background
    thread = threading.Thread(target=download_thread, daemon=True)
    thread.start()
    
    # Monitor progress
    progress = 10
    last_file_count = 0
    
    while thread.is_alive():
        time.sleep(1)
        
        try:
            # Check directory for new files
            current_files = list(Path(local_dir).rglob('*'))
            file_count = len([f for f in current_files if f.is_file()])
            
            if file_count > last_file_count:
                progress = min(95, progress + 3)
                last_file_count = file_count
                
                # Find most recent file
                latest_file = None
                try:
                    files = [f for f in current_files if f.is_file()]
                    if files:
                        latest_file = max(files, key=lambda f: f.stat().st_mtime)
                except:
                    pass
                
                current_file_name = latest_file.name if latest_file else "Processing files..."
                
                update_download_status(
                    progress=progress,
                    status='downloading',
                    current_file=f"Processing: {current_file_name}",
                    downloaded_files=file_count
                )
            elif progress < 90:
                progress = min(90, progress + 1)
                update_download_status(
                    progress=progress,
                    status='downloading',
                    current_file='Downloading files...'
                )
                
        except Exception as e:
            print(f"Error monitoring progress: {e}")
    
    # Wait for completion and check for errors
    thread.join()
    if download_exception[0]:
        raise download_exception[0]

def start_download_task(repo_id, quant_pattern):
    """Main download function"""
    print(f"\n=== DOWNLOAD STARTED ===")
    print(f"Repository ID: {repo_id}")
    print(f"Quantization Pattern: '{quant_pattern}'")

    try:
        # Reset and initialize status
        update_download_status(
            progress=0,
            status="starting",
            current_file="Initializing download...",
            downloaded_files=0,
            repo_id=repo_id,
            start_time=time.time()
        )

        local_dir = f"/models/{repo_id}"
        os.makedirs(local_dir, exist_ok=True)

        allow_patterns = [f"*{quant_pattern}*"] if quant_pattern.strip() else None

        update_download_status(
            progress=5,
            status='downloading',
            current_file='Starting download...'
        )

        # Execute download with progress monitoring
        download_with_progress(repo_id, local_dir, allow_patterns)

        # Complete
        update_download_status(
            progress=100,
            status="completed",
            current_file="Download completed successfully!"
        )

    except HfHubHTTPError as e:
        update_download_status(progress=0, status="error", current_file=f"HuggingFace error: {str(e)}")
    except Exception as e:
        tb = traceback.format_exc()
        print(f"Download error: {e}\n{tb}")
        update_download_status(progress=0, status="error", current_file=f"Error: {str(e)}")

# ============== MODEL SCANNING ==============

def group_model_files(files):
    """Group model files by common patterns"""
    groups = defaultdict(list)
    ungrouped = []
    
    for file_path in files:
        filename = os.path.basename(file_path)
        
        # Pattern for safetensors files like model-00001-of-00003.safetensors
        safetensors_match = re.match(r'(.+)-(\d+)-of-(\d+)\.safetensors$', filename)
        if safetensors_match:
            base_name = safetensors_match.group(1)
            total_parts = safetensors_match.group(3)
            group_key = f"{base_name}-*-of-{total_parts}.safetensors"
            groups[group_key].append(file_path)
            continue
        
        # Pattern for GGUF files
        if filename.endswith('.gguf'):
            parent_dir = os.path.basename(os.path.dirname(file_path))
            group_key = f"{parent_dir}/*.gguf"
            groups[group_key].append(file_path)
            continue
        
        # Pattern for pytorch model files
        if filename.startswith('pytorch_model-') and filename.endswith('.bin'):
            bin_match = re.match(r'pytorch_model-(\d+)-of-(\d+)\.bin$', filename)
            if bin_match:
                total_parts = bin_match.group(2)
                group_key = f"pytorch_model-*-of-{total_parts}.bin"
                groups[group_key].append(file_path)
                continue
        
        ungrouped.append(file_path)
    
    return groups, ungrouped

def create_file_metadata(file_path):
    """Create file metadata object"""
    try:
        size_bytes = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        mtime = os.path.getmtime(file_path) if os.path.exists(file_path) else 0
        date_str = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M') if mtime else ''
    except Exception:
        size_bytes, mtime, date_str = 0, 0, ''
    
    return {
        'name': os.path.basename(file_path),
        'path': file_path,
        'size': get_file_size_from_bytes(size_bytes),
        'size_bytes': size_bytes,
        'mtime': mtime,
        'date': date_str
    }

def scan_models():
    """Scan /models directory for existing models"""
    models_dir = "/models"
    if not os.path.exists(models_dir):
        return []
    
    models = []
    
    for root, dirs, files in os.walk(models_dir):
        if files:
            # Get model files (common extensions)
            model_files = [
                os.path.join(root, file) for file in files
                if any(file.endswith(ext) for ext in ['.safetensors', '.bin', '.gguf', '.pt', '.pth'])
            ]
            
            if model_files:
                relative_path = os.path.relpath(root, models_dir)
                
                # Group files
                groups, ungrouped = group_model_files(model_files)
                
                model_info = {
                    'name': relative_path,
                    'path': root,
                    'groups': [],
                    'individual_files': []
                }
                
                # Add grouped files
                for group_name, group_files in groups.items():
                    file_objs = [create_file_metadata(fpath) for fpath in group_files]
                    total_size = sum(f['size_bytes'] for f in file_objs)
                    
                    model_info['groups'].append({
                        'name': group_name,
                        'files': file_objs,
                        'count': len(file_objs),
                        'size': get_file_size_from_bytes(total_size),
                        'size_bytes': total_size
                    })
                
                # Add individual files
                model_info['individual_files'] = [create_file_metadata(fpath) for fpath in ungrouped]
                
                # Calculate total size
                total_size = sum(os.path.getsize(f) for f in model_files if os.path.exists(f))
                model_info['total_size'] = get_file_size_from_bytes(total_size)
                model_info['total_size_bytes'] = total_size
                
                models.append(model_info)
    
    return sorted(models, key=lambda x: x['name'])

# ============== CRUD OPERATIONS ==============

def update_model(repo_id, quant_pattern=""):
    """Update/re-download a model"""
    try:
        if not validate_repo_id(repo_id):
            return False, 'Invalid repository id'

        local_dir = f"/models/{repo_id}"
        os.makedirs(local_dir, exist_ok=True)
        
        allow_patterns = [f"*{quant_pattern}*"] if quant_pattern.strip() else None
        
        snapshot_download(
            repo_id=repo_id,
            local_dir=local_dir,
            allow_patterns=allow_patterns,
            resume_download=True,
            local_dir_use_symlinks=False
        )
        
        return True, "Model updated successfully"
        
    except HfHubHTTPError as e:
        return False, f"Error updating model: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"

def delete_model(model_path):
    """Delete a model directory"""
    try:
        if not validate_model_path(model_path):
            return False, "Invalid model path: must be within /models/ directory"
        
        if os.path.exists(model_path):
            # Get info before deletion
            try:
                total_size = 0
                file_count = 0
                for dirpath, dirnames, filenames in os.walk(model_path):
                    file_count += len(filenames)
                    for filename in filenames:
                        filepath = os.path.join(dirpath, filename)
                        try:
                            total_size += os.path.getsize(filepath)
                        except (OSError, IOError):
                            pass
                size_info = f"{file_count} files, {get_file_size_from_bytes(total_size)}"
            except Exception:
                size_info = "unknown size"
            
            shutil.rmtree(model_path)
            return True, f'Model deleted successfully ({size_info})'
        else:
            return False, 'Model path not found'
            
    except Exception as e:
        return False, f'Error deleting model: {str(e)}'

# ============== FLASK ROUTES ==============

@app.context_processor
def inject_base_url():
    return dict(base_url=base_url)

@app.before_request
def log_request():
    print(f"\n📨 {request.method} {request.path}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    return ('', 204)

@app.route('/download', methods=['POST'])
def start_download():
    data = request.get_json() or {}
    repo_id = data.get('repo_id', '').strip()
    quant_pattern = data.get('quant_pattern', '').strip()

    if not repo_id:
        return jsonify({'error': 'Repository ID is required'}), 400
        
    if not validate_repo_id(repo_id):
        return jsonify({'error': 'Repository ID should be in format: username/model-name'}), 400

    if download_status["status"] == "downloading":
        return jsonify({'error': 'Download already in progress'}), 400

    # Start download in background
    socketio.start_background_task(start_download_task, repo_id, quant_pattern)
    return jsonify({'message': 'Download started'})

@app.route('/status')
def get_status():
    return jsonify(download_status)

@app.route('/api/models')
def api_models():
    models = scan_models()
    return jsonify(models)

@app.route('/api/models/update', methods=['POST'])
def api_update_model():
    data = request.get_json() or {}
    repo_id = data.get('repo_id', '').strip()
    quant_pattern = data.get('quant_pattern', '').strip()

    if not validate_repo_id(repo_id):
        return jsonify({'error': 'Invalid repository ID'}), 400

    def update_thread():
        update_model_with_progress(repo_id, quant_pattern)

    threading.Thread(target=update_thread, daemon=True).start()
    return jsonify({'message': f'Update started for {repo_id}'})

@app.route('/api/models/delete', methods=['POST'])
def api_delete_model():
    data = request.get_json() or {}
    model_path = data.get('path', '').strip()

    if not validate_model_path(model_path):
        return jsonify({'error': 'Invalid model path'}), 400

    try:
        success, message = delete_model(model_path)
        if success:
            return jsonify({'message': message})
        else:
            return jsonify({'error': message}), 500
    except Exception as e:
        return jsonify({'error': f'Error deleting model: {str(e)}'}), 500

# ============== MAIN ==============

if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 STARTING HUGGINGFACE MODEL DOWNLOADER")
    print("="*50)
    print(f"🔥 Unified Interface: http://localhost:5000{base_url}/")
    print(f"💾 Models Directory: /models/")
    if base_url:
        print(f"🌍 Base URL Path: {base_url}")
        print(f"🔌 Socket.IO Path: {socketio_path}")
    print("="*50)

    os.makedirs("/models", exist_ok=True)
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)