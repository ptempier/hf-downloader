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
def add_url_rule_with_prefix(path, endpoint, view_func, methods=None):
    """Register routes with and without base_url prefix"""
    # Register base route
    app.add_url_rule(path, endpoint, view_func, methods=methods)
    
    # Register base_url route if configured
    if base_url:
        prefixed_path = f"{base_url}{path}"
        app.add_url_rule(prefixed_path, f"{endpoint}_prefixed", view_func, methods=methods)

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
print(f"DEBUG I")
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
    print(f"DEBUG Start a simple progress monitoring")
    global _monitoring_active, _monitoring_thread
    
    if _monitoring_active:
        return  # Already monitoring
    
    _monitoring_active = True
    
    def monitor():
        cache_dir = "/models/.cache"
        last_downloaded_bytes = 0
        
        while _monitoring_active:
            loop_start = time.time()
            print(f"🔄 Monitor loop starting at {time.strftime('%H:%M:%S')}")
            
            time.sleep(1)  # Check every 1 second
            sleep_end = time.time()
            print(f"😴 Sleep completed in {sleep_end - loop_start:.3f}s")
            
            print(f"DEBUG Check every 1 second _monitoring_active")
            try:
                if not _monitoring_active:
                    print("🛑 Monitoring inactive, breaking")
                    break
                    
                # Simple byte calculation
                start_time = time.time()
                downloaded_bytes = calculate_downloaded_size(local_dir, cache_dir, repo_id)
                calculation_time = time.time() - start_time
                print(f"⏱️ File size calculation took: {calculation_time:.3f} seconds")
                
                # Basic progress calculation
                progress_start = time.time()
                if total_expected_bytes > 0:
                    progress = min(95, (downloaded_bytes / total_expected_bytes) * 100)
                    progress_info = f"{get_file_size_from_bytes(downloaded_bytes)} / {get_file_size_from_bytes(total_expected_bytes)}"
                else:
                    progress = min(95, 10 + (downloaded_bytes / (1024 * 1024 * 100)))
                    progress_info = f"{get_file_size_from_bytes(downloaded_bytes)} downloaded"
                
                # Simple status update
                is_progressing = downloaded_bytes > last_downloaded_bytes
                status_msg = "Downloading..." if is_progressing else "Processing..."
                progress_calc_time = time.time() - progress_start
                print(f"📊 Progress calculation took: {progress_calc_time:.3f}s")
                
                # Update status directly - monitoring thread controls this flow
                print(f"DEBUG B")
                status_update_start = time.time()                
                update_download_status(
                    progress=progress,
                    status='downloading',
                    current_file=f"{status_msg} ({progress_info})",
                    downloaded_bytes=downloaded_bytes
                )
                status_update_time = time.time() - status_update_start
                print(f"📤 Status update took: {status_update_time:.3f}s")
                
                last_downloaded_bytes = downloaded_bytes
                
                total_loop_time = time.time() - loop_start
                print(f"🔄 Complete loop took: {total_loop_time:.3f}s")
                    
            except Exception as e:
                print(f"❌ Monitor error: {e}")
                traceback.print_exc()
                # Don't break on errors, just continue
        
        print("📊 Progress monitoring stopped")
    
    _monitoring_thread = threading.Thread(target=monitor, daemon=True)
    _monitoring_thread.start()
    print("📊 Progress monitoring started")

def stop_progress_monitoring():
    print(f"DEBUG K")
    """Stop progress monitoring"""
    global _monitoring_active
    _monitoring_active = False
    print("📊 Stopping progress monitoring")

def get_repo_info_with_patterns(repo_id, allow_patterns=None):
    """Get repository info and calculate total expected download size"""
    print(f"DEBUG C")
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
    print(f"DEBUG D")
    """Calculate total bytes downloaded by checking both final and cache directories"""
    start_total = time.time()
    total_downloaded = 0
    local_files_count = 0
    cache_files_count = 0
    
    # Check final destination files
    start_local = time.time()
    if os.path.exists(local_dir):
        local_path = Path(local_dir)
        for file_path in local_path.rglob('*'):
            if file_path.is_file():
                try:
                    total_downloaded += file_path.stat().st_size
                    local_files_count += 1
                except (OSError, IOError):
                    continue
    local_time = time.time() - start_local
    print(f"⏱️ Local dir scan: {local_time:.3f}s ({local_files_count} files)")
    
    # Check cache for incomplete files and blobs
    start_cache = time.time()
    cache_repo_dir = Path(cache_dir) / f"models--{repo_id.replace('/', '--')}"
    if cache_repo_dir.exists():
        for file_path in cache_repo_dir.rglob('*'):
            if file_path.is_file():
                try:
                    total_downloaded += file_path.stat().st_size
                    cache_files_count += 1
                except (OSError, IOError):
                    continue
    cache_time = time.time() - start_cache
    print(f"⏱️ Cache dir scan: {cache_time:.3f}s ({cache_files_count} files)")
    
    total_time = time.time() - start_total
    print(f"⏱️ TIMING BREAKDOWN: Local={local_time:.3f}s, Cache={cache_time:.3f}s, Total={total_time:.3f}s ({get_file_size_from_bytes(total_downloaded)})")
    
    return total_downloaded

def update_download_status(**kwargs):
    print(f"DEBUG E")
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
    print(f"DEBUG F")    
    """Download with progress monitoring"""
    
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
    print(f"DEBUG G")
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