#!/usr/bin/env python3
"""
Legacy Single-Process Version (Kept for Reference)
Note: This version has threading issues. Use app_multiprocess.py instead.
"""

from flask import Flask, render_template, request, jsonify
import os
import threading
import time
import shutil
from huggingface_hub import snapshot_download, HfApi
from huggingface_hub.utils import HfHubHTTPError

# Import shared utilities
from utils import (
    get_file_size_from_bytes, validate_repo_id, validate_model_path,
    group_model_files, create_file_metadata, scan_models, calculate_downloaded_size
)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'

# CONFIGURATION
base_url = "/hf-downloader"   # Set this to match your Caddy handle_path

# Set HF_TRANSFER for faster downloads
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"

# Route helper function to register routes with and without base_url
def add_url_rule_with_prefix(path, endpoint, view_func, methods=None):
    """Register routes with and without base_url prefix"""
    # Register base route
    app.add_url_rule(path, endpoint, view_func, methods=methods)
    
    # Register base_url route if configured
    if base_url:
        prefixed_path = f"{base_url}{path}"
        app.add_url_rule(prefixed_path, f"{endpoint}_prefixed", view_func, methods=methods)

# ============== SHARED UTILITIES ==============

# All utilities now imported from utils.py

# ============== DOWNLOAD MANAGEMENT ==============

# Global download status with monitoring
download_status = {
    "progress": 0, 
    "status": "idle", 
    "current_file": "",
    "downloaded_files": 0,
    "downloaded_bytes": 0,
    "total_bytes": 0,
    "repo_id": "",
    "start_time": None
}

# Simple monitoring state
_monitoring_active = False
_monitoring_thread = None

def start_progress_monitoring(repo_id, local_dir, total_expected_bytes):
    """Start a simple progress monitoring thread"""
    global _monitoring_active, _monitoring_thread
    
    if _monitoring_active:
        return  # Already monitoring
    
    _monitoring_active = True
    
    def monitor():
        cache_dir = "/models/.cache"
        last_downloaded_bytes = 0
        
        while _monitoring_active:
            time.sleep(1)  # Check every 1s
            
            try:
                if not _monitoring_active:
                    break
                    
                # Simple byte calculation
                downloaded_bytes = calculate_downloaded_size(local_dir, cache_dir, repo_id)
                
                # Basic progress calculation
                if total_expected_bytes > 0:
                    progress = min(95, (downloaded_bytes / total_expected_bytes) * 100)
                    progress_info = f"{get_file_size_from_bytes(downloaded_bytes)} / {get_file_size_from_bytes(total_expected_bytes)}"
                else:
                    progress = min(95, 10 + (downloaded_bytes / (1024 * 1024 * 100)))
                    progress_info = f"{get_file_size_from_bytes(downloaded_bytes)} downloaded"
                
                # Simple status update
                is_progressing = downloaded_bytes > last_downloaded_bytes
                status_msg = "Downloading..." if is_progressing else "Processing..."
                
                # Update status directly - monitoring thread controls this flow
                update_download_status(
                    progress=progress,
                    status='downloading',
                    current_file=f"{status_msg} ({progress_info})",
                    downloaded_bytes=downloaded_bytes
                )
                
                last_downloaded_bytes = downloaded_bytes
                    
            except Exception as e:
                print(f"❌ Monitor error: {e}")
                # Don't break on errors, just continue
        
        print("📊 Progress monitoring stopped")
    
    _monitoring_thread = threading.Thread(target=monitor, daemon=True)
    _monitoring_thread.start()
    print("📊 Progress monitoring started")

def stop_progress_monitoring():
    """Stop progress monitoring"""
    global _monitoring_active
    _monitoring_active = False
    print("📊 Stopping progress monitoring")

def get_repo_info_with_patterns(repo_id, allow_patterns=None):
    """Get repository info and calculate total expected download size"""
    try:
        print(f"🔍 Fetching repository info for {repo_id}...")
        api = HfApi()
        repo_info = api.repo_info(repo_id, files_metadata=True)
        
        total_size = 0
        file_count = 0
        
        for sibling in repo_info.siblings:
            # Check if file matches patterns (if specified)
            if allow_patterns:
                matches_pattern = any(
                    pattern.replace('*', '') in sibling.rfilename 
                    for pattern in allow_patterns
                )
                if not matches_pattern:
                    continue
            
            if hasattr(sibling, 'size') and sibling.size:
                total_size += sibling.size
                file_count += 1
        
        print(f"✅ Total expected: {get_file_size_from_bytes(total_size)} ({file_count} files)")
        return total_size, file_count, repo_info
    except Exception as e:
        print(f"❌ Failed to get repo info: {e}")
        return 0, 0, None

def update_download_status(**kwargs):
    """Update download status"""
    global download_status
    
    # Direct update - Python dict operations are atomic enough for our use case
    download_status.update(kwargs)
    
    # Calculate ETA
    if download_status.get('start_time') and download_status.get('progress', 0) > 0:
        elapsed = time.time() - download_status['start_time']
        if download_status['progress'] > 0:
            eta = (elapsed / download_status['progress']) * (100 - download_status['progress'])
            download_status['eta'] = eta

def download_with_progress(repo_id, local_dir, allow_patterns):
    """Download with progress monitoring"""
    
    # Get repository info and expected size
    total_expected_bytes, expected_files, repo_info = get_repo_info_with_patterns(repo_id, allow_patterns)
    
    if total_expected_bytes > 0:
        print(f"✅ Expected download size: {get_file_size_from_bytes(total_expected_bytes)} ({expected_files} files)")
        update_download_status(
            total_bytes=total_expected_bytes,
            current_file=f"Expected: {get_file_size_from_bytes(total_expected_bytes)} ({expected_files} files)"
        )
    else:
        print(f"⚠️ Could not determine download size - progress will be estimated")
        update_download_status(current_file="Starting download...")
    
    # Start progress monitoring
    start_progress_monitoring(repo_id, local_dir, total_expected_bytes)
    
    try:
        # Set custom cache directory within models folder
        cache_dir = "/models/.cache"
        os.makedirs(cache_dir, exist_ok=True)
        
        print(f"🚀 Starting download...")
        
        # Update status to downloading before starting the actual download
        update_download_status(status='downloading')
        
        snapshot_download(
            repo_id=repo_id,
            local_dir=local_dir,
            allow_patterns=allow_patterns,
            resume_download=True,
            local_dir_use_symlinks=False,
            cache_dir=cache_dir
        )
        
        # Download completed successfully
        print(f"✅ Download completed successfully")
        stop_progress_monitoring()
        
        final_size = calculate_downloaded_size(local_dir, cache_dir, repo_id)
        update_download_status(
            progress=100,
            status="completed",
            current_file=f"Download completed! Total size: {get_file_size_from_bytes(final_size)}",
            downloaded_bytes=final_size
        )
        
    except Exception as e:
        print(f"❌ Download failed: {e}")
        stop_progress_monitoring()
        update_download_status(progress=0, status="error", current_file=f"Error: {str(e)}")

def download_model_task(repo_id, quant_pattern):
    """Function for downloading or updating models with progress tracking"""
    print(f"\n=== DOWNLOAD STARTED ===")
    print(f"Repository ID: {repo_id}")
    print(f"Quantization Pattern: '{quant_pattern}'")

    try:
        # Reset and initialize status
        update_download_status(
            progress=0,
            status="starting",
            current_file=f"Initializing download...",
            downloaded_files=0,
            downloaded_bytes=0,
            total_bytes=0,
            repo_id=repo_id,
            start_time=time.time()
        )

        local_dir = f"/models/{repo_id}"
        os.makedirs(local_dir, exist_ok=True)

        allow_patterns = [f"*{quant_pattern}*"] if quant_pattern.strip() else None

        update_download_status(
            progress=5,
            status='downloading',
            current_file='Getting repository information...'
        )

        # Execute download with progress monitoring
        download_with_progress(repo_id, local_dir, allow_patterns)

    except HfHubHTTPError as e:
        update_download_status(progress=0, status="error", current_file=f"HuggingFace error: {str(e)}")
    except Exception as e:
        print(f"Download error: {e}")
        update_download_status(progress=0, status="error", current_file=f"Error: {str(e)}")

# ============== MODEL SCANNING ==============

# All model scanning functions now imported from utils.py

# ============== CRUD OPERATIONS ==============

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
    print(f"📨 {request.method} {request.path}")

def index():
    return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    return ('', 204)

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

    # Start download in background thread
    download_thread = threading.Thread(target=download_model_task, args=(repo_id, quant_pattern), daemon=True)
    download_thread.start()
    
    return jsonify({'message': 'Download started'})

def get_status():
    return jsonify(dict(download_status))

def api_models():
    models = scan_models()
    return jsonify(models)

def api_update_model():
    data = request.get_json() or {}
    repo_id = data.get('repo_id', '').strip()
    quant_pattern = data.get('quant_pattern', '').strip()

    if not validate_repo_id(repo_id):
        return jsonify({'error': 'Invalid repository ID'}), 400

    def update_thread():
        download_model_task(repo_id, quant_pattern)

    threading.Thread(target=update_thread, daemon=True).start()
    return jsonify({'message': f'Update started for {repo_id}'})

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

# Register all routes
add_url_rule_with_prefix('/', 'index', index)
add_url_rule_with_prefix('/api/download', 'start_download', start_download, methods=['POST'])
add_url_rule_with_prefix('/api/status', 'get_status', get_status)
add_url_rule_with_prefix('/api/list', 'api_models', api_models)
add_url_rule_with_prefix('/api/update', 'api_update_model', api_update_model, methods=['POST'])
add_url_rule_with_prefix('/api/delete', 'api_delete_model', api_delete_model, methods=['POST'])

if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 STARTING HUGGINGFACE MODEL DOWNLOADER")
    print("="*50)
    print(f"🔥 Access URL: http://localhost:5000{base_url}/")
    print(f"💾 Models Directory: /models/")
    print(f"🗂️ Cache Directory: /models/.cache/")
    if base_url:
        print(f"🌍 Client Base URL: {base_url}")
        print("� Using HTTP polling for progress updates")
    print("="*50)

    os.makedirs("/models", exist_ok=True)
    os.makedirs("/models/.cache", exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)