#!/usr/bin/env python3

from flask import Flask, render_template, request, jsonify
import os
import traceback
import threading
import time
import shutil
import datetime
import re
from collections import defaultdict
from pathlib import Path
from huggingface_hub import snapshot_download, HfApi
from huggingface_hub.utils import HfHubHTTPError

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'

# CONFIGURATION
base_url = "/hf-downloader"   # Set this to match your Caddy handle_path

# Set HF_TRANSFER for faster downloads
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"

# Route helper function to register routes with and without base_url
def register_route(path, methods=None, **kwargs):
    """Register routes with and without base_url prefix"""
    def decorator(func):
        # Register base route
        app.route(path, methods=methods, **kwargs)(func)
        
        # Register base_url route if configured
        if base_url:
            prefixed_path = f"{base_url}{path}"
            app.route(prefixed_path, methods=methods, **kwargs)(func)
        
        return func
    return decorator

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
    "downloaded_bytes": 0,
    "total_bytes": 0,
    "repo_id": "",
    "start_time": None
}

def get_repo_info_with_patterns(repo_id, allow_patterns=None):
    """Get repository info and calculate total expected download size"""
    try:
        print(f"🔍 Fetching repository info for {repo_id}...")
        api = HfApi()
        repo_info = api.repo_info(repo_id, files_metadata=True)
        
        total_size = 0
        file_count = 0
        
        print(f"📂 Repository has {len(repo_info.siblings)} files")
        
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
                print(f"  📄 {sibling.rfilename}: {get_file_size_from_bytes(sibling.size)}")
        
        print(f"✅ Total expected: {get_file_size_from_bytes(total_size)} ({file_count} files)")
        return total_size, file_count, repo_info
    except Exception as e:
        print(f"❌ Failed to get repo info: {e}")
        traceback.print_exc()
        return 0, 0, None

def calculate_downloaded_size(local_dir, cache_dir, repo_id):
    """Calculate total bytes downloaded by checking both final and cache directories"""
    total_downloaded = 0
    
    # Helper function to safely get file size
    def safe_getsize(file_path):
        try:
            return file_path.stat().st_size
        except (OSError, IOError):
            return 0
    
    # Check final destination files
    if os.path.exists(local_dir):
        local_path = Path(local_dir)
        total_downloaded += sum(safe_getsize(f) for f in local_path.rglob('*') if f.is_file())
    
    # Check cache for incomplete files and blobs
    cache_repo_dir = Path(cache_dir) / f"models--{repo_id.replace('/', '--')}"
    if cache_repo_dir.exists():
        total_downloaded += sum(safe_getsize(f) for f in cache_repo_dir.rglob('*') if f.is_file())
    
    return total_downloaded

def update_download_status(**kwargs):
    """Thread-safe update of download status"""
    global download_status
    download_status.update(kwargs)
    
    # Calculate ETA
    if download_status.get('start_time') and download_status.get('progress', 0) > 0:
        elapsed = time.time() - download_status['start_time']
        if download_status['progress'] > 0:
            eta = (elapsed / download_status['progress']) * (100 - download_status['progress'])
            download_status['eta'] = eta
    
    # Simple logging for progress tracking
    print(f"Progress: {download_status.get('progress', 0):.1f}% - {download_status.get('current_file', '')}")

# Add a status endpoint that clients can poll as fallback
@register_route('/api/download/status')
def get_download_status():
    """Get current download status - fallback for when Socket.IO disconnects"""
    return jsonify(download_status)

def download_with_progress(repo_id, local_dir, allow_patterns):
    """Download with real-time byte-based progress monitoring"""
    
    download_exception = [None]
    
    # Get repository info and expected size
    print(f"📊 Getting repository information...")
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
    
    def download_thread():
        try:
            # Set custom cache directory within models folder
            cache_dir = "/models/.cache"
            os.makedirs(cache_dir, exist_ok=True)
            
            snapshot_download(
                repo_id=repo_id,
                local_dir=local_dir,
                allow_patterns=allow_patterns,
                resume_download=True,
                local_dir_use_symlinks=False,
                cache_dir=cache_dir
            )
        except Exception as e:
            download_exception[0] = e
    
    def monitor_progress():
        """Separate monitoring thread to avoid blocking the main thread"""
        cache_dir = "/models/.cache"
        last_downloaded_bytes = 0
        
        while thread.is_alive():
            time.sleep(1)  # Check every second
            
            try:
                # Calculate downloaded bytes
                downloaded_bytes = calculate_downloaded_size(local_dir, cache_dir, repo_id)
                
                # Calculate progress
                if total_expected_bytes > 0:
                    progress = min(95, (downloaded_bytes / total_expected_bytes) * 100)
                    progress_info = f"{get_file_size_from_bytes(downloaded_bytes)} / {get_file_size_from_bytes(total_expected_bytes)}"
                else:
                    # Simple estimation without expected size
                    progress = min(95, 10 + (downloaded_bytes / (1024 * 1024 * 100)))  # Rough estimate
                    progress_info = f"{get_file_size_from_bytes(downloaded_bytes)} downloaded"
                
                # Find most recent file for status
                current_file_name = "Processing files..."
                try:
                    current_files = list(Path(local_dir).rglob('*'))
                    files = [f for f in current_files if f.is_file()]
                    if files:
                        latest_file = max(files, key=lambda f: f.stat().st_mtime)
                        current_file_name = latest_file.name
                except:
                    pass
                
                # Determine if making progress
                is_progressing = downloaded_bytes > last_downloaded_bytes
                status_prefix = "Downloading" if is_progressing else "Processing"
                
                update_download_status(
                    progress=progress,
                    status='downloading',
                    current_file=f"{status_prefix}: {current_file_name} ({progress_info})",
                    downloaded_files=len(files) if 'files' in locals() else 0,
                    downloaded_bytes=downloaded_bytes
                )
                
                last_downloaded_bytes = downloaded_bytes
                    
            except Exception as e:
                print(f"❌ Error monitoring progress: {e}")
                traceback.print_exc()
    
    # Start download in background
    thread = threading.Thread(target=download_thread, daemon=True)
    thread.start()
    
    # Start monitoring in separate background thread
    monitor_thread = threading.Thread(target=monitor_progress, daemon=True)
    monitor_thread.start()
    
    # Wait for download completion (non-blocking for other requests)
    thread.join()
    monitor_thread.join(timeout=5)  # Give monitor thread time to finish
    
    print(f"✅ Download thread completed")
    
    # Check for errors
    if download_exception[0]:
        raise download_exception[0]

def download_model_task(repo_id, quant_pattern, operation_type="download"):
    """Unified function for downloading or updating models with progress tracking"""
    print(f"\n=== {operation_type.upper()} STARTED ===")
    print(f"Repository ID: {repo_id}")
    print(f"Quantization Pattern: '{quant_pattern}'")

    try:
        # Reset and initialize status
        update_download_status(
            progress=0,
            status="starting",
            current_file=f"Initializing {operation_type}...",
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

        # Final size calculation
        final_size = calculate_downloaded_size(local_dir, "/models/.cache", repo_id)
        
        # Complete
        completion_msg = "Download completed!" if operation_type == "download" else "Update completed!"
        update_download_status(
            progress=100,
            status="completed",
            current_file=f"{completion_msg} Total size: {get_file_size_from_bytes(final_size)}",
            downloaded_bytes=final_size
        )

    except HfHubHTTPError as e:
        update_download_status(progress=0, status="error", current_file=f"HuggingFace error: {str(e)}")
    except Exception as e:
        tb = traceback.format_exc()
        print(f"{operation_type.capitalize()} error: {e}\n{tb}")
        update_download_status(progress=0, status="error", current_file=f"Error: {str(e)}")

# Convenience wrappers for backward compatibility
def start_download_task(repo_id, quant_pattern):
    """Main download function"""
    return download_model_task(repo_id, quant_pattern, "download")

def update_model_with_progress(repo_id, quant_pattern=""):
    """Update model with progress tracking via Socket.IO"""
    return download_model_task(repo_id, quant_pattern, "update")

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

@register_route('/')
def index():
    return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    return ('', 204)

@register_route('/download', methods=['POST'])
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
    threading.Thread(target=start_download_task, args=(repo_id, quant_pattern), daemon=True).start()
    return jsonify({'message': 'Download started'})

@register_route('/status')
def get_status():
    return jsonify(download_status)

@register_route('/api/models')
def api_models():
    models = scan_models()
    return jsonify(models)

@register_route('/api/models/update', methods=['POST'])
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

@register_route('/api/models/delete', methods=['POST'])
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