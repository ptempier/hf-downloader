#!/usr/bin/env python3
"""
Main Process Orchestrator
Starts and manages all 3 processes:
1. Web Server (Flask)
2. Download Manager 
3. Monitoring Service

Handles all IPC communication setup
"""

import multiprocessing
import time
import signal
import sys
import os
from flask import Flask, render_template, request, jsonify
import uuid
import datetime
import re
from collections import defaultdict
from pathlib import Path

# Import our process modules
from download_manager import download_manager_process
from monitor_service import monitoring_service_process


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


# ============== GLOBAL STATE MANAGER ==============

class AppState:
    """Thread-safe application state using multiprocessing Manager"""
    def __init__(self, manager):
        self.download_status = manager.dict({
            "progress": 0,
            "status": "idle",
            "current_file": "",
            "downloaded_files": 0,
            "downloaded_bytes": 0,
            "total_bytes": 0,
            "repo_id": "",
            "start_time": None
        })
        self.pending_tasks = manager.dict()  # Track pending responses
    
    def update_status(self, **kwargs):
        """Update download status"""
        for key, value in kwargs.items():
            self.download_status[key] = value
        
        # Calculate ETA
        if self.download_status.get('start_time') and self.download_status.get('progress', 0) > 0:
            elapsed = time.time() - self.download_status['start_time']
            if self.download_status['progress'] > 0:
                eta = (elapsed / self.download_status['progress']) * (100 - self.download_status['progress'])
                self.download_status['eta'] = eta


# ============== FLASK WEB SERVER ==============

def create_flask_app(app_state, task_queue, monitor_requests_queue):
    """Create Flask application with IPC communication"""
    
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'your-secret-key'
    
    # CONFIGURATION
    base_url = "/hf-downloader"   # Set this to match your Caddy handle_path
    
    # Route helper function
    def add_url_rule_with_prefix(path, endpoint, view_func, methods=None):
        """Register routes with and without base_url prefix"""
        app.add_url_rule(path, endpoint, view_func, methods=methods)
        if base_url:
            prefixed_path = f"{base_url}{path}"
            app.add_url_rule(prefixed_path, f"{endpoint}_prefixed", view_func, methods=methods)
    
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

        if app_state.download_status["status"] == "downloading":
            return jsonify({'error': 'Download already in progress'}), 400

        # Generate task ID and send to download manager
        task_id = str(uuid.uuid4())
        task = {
            'task_id': task_id,
            'type': 'download',
            'repo_id': repo_id,
            'quant_pattern': quant_pattern
        }
        
        # Add to pending tasks
        app_state.pending_tasks[task_id] = task
        
        # Send task to download manager
        task_queue.put(task)
        
        # Start monitoring
        monitor_requests_queue.put({
            'type': 'start_monitor',
            'repo_id': repo_id,
            'local_dir': f"/models/{repo_id}",
            'total_expected_bytes': 0  # Will be updated by download manager
        })
        
        return jsonify({'message': 'Download started', 'task_id': task_id})

    def get_status():
        return jsonify(dict(app_state.download_status))

    def api_models():
        models = scan_models()
        return jsonify(models)

    def api_update_model():
        data = request.get_json() or {}
        repo_id = data.get('repo_id', '').strip()
        quant_pattern = data.get('quant_pattern', '').strip()

        if not validate_repo_id(repo_id):
            return jsonify({'error': 'Invalid repository ID'}), 400

        # Generate task ID and send to download manager
        task_id = str(uuid.uuid4())
        task = {
            'task_id': task_id,
            'type': 'download',  # Update is same as download
            'repo_id': repo_id,
            'quant_pattern': quant_pattern
        }
        
        app_state.pending_tasks[task_id] = task
        task_queue.put(task)
        
        # Start monitoring
        monitor_requests_queue.put({
            'type': 'start_monitor',
            'repo_id': repo_id,
            'local_dir': f"/models/{repo_id}",
            'total_expected_bytes': 0
        })
        
        return jsonify({'message': f'Update started for {repo_id}', 'task_id': task_id})

    def api_delete_model():
        data = request.get_json() or {}
        model_path = data.get('path', '').strip()

        if not validate_model_path(model_path):
            return jsonify({'error': 'Invalid model path'}), 400

        # Generate task ID and send to download manager
        task_id = str(uuid.uuid4())
        task = {
            'task_id': task_id,
            'type': 'delete',
            'model_path': model_path
        }
        
        app_state.pending_tasks[task_id] = task
        task_queue.put(task)
        
        return jsonify({'message': f'Delete started for {model_path}', 'task_id': task_id})

    # Register all routes
    add_url_rule_with_prefix('/', 'index', index)
    add_url_rule_with_prefix('/api/download', 'start_download', start_download, methods=['POST'])
    add_url_rule_with_prefix('/api/status', 'get_status', get_status)
    add_url_rule_with_prefix('/api/list', 'api_models', api_models)
    add_url_rule_with_prefix('/api/update', 'api_update_model', api_update_model, methods=['POST'])
    add_url_rule_with_prefix('/api/delete', 'api_delete_model', api_delete_model, methods=['POST'])
    
    return app


# ============== STATUS UPDATE PROCESSOR ==============

def status_update_processor(status_queue, response_queue, app_state, monitor_requests_queue):
    """Process status updates from download manager and monitoring service"""
    print("📡 Status Update Processor Started")
    
    while True:
        try:
            # Check for status updates (blocking with timeout)
            try:
                status_update = status_queue.get(timeout=1)
                print(f"📊 Status update: {status_update}")
                app_state.update_status(**status_update)
            except:
                pass  # Timeout, continue
            
            # Check for task responses (non-blocking)
            try:
                response = response_queue.get_nowait()
                print(f"📨 Task response: {response}")
                
                task_id = response.get('task_id')
                if task_id and task_id in app_state.pending_tasks:
                    # Task completed, handle cleanup
                    task = app_state.pending_tasks[task_id]
                    del app_state.pending_tasks[task_id]
                    
                    if task['type'] == 'download' and response['success']:
                        # Download completed, stop monitoring after a delay
                        monitor_requests_queue.put({'type': 'stop_monitor'})
                    
                    print(f"✅ Task {task_id} completed: {response['message']}")
                    
            except:
                pass  # No response waiting
                
        except Exception as e:
            print(f"❌ Error in status processor: {e}")
            time.sleep(1)


# ============== MAIN ORCHESTRATOR ==============

def main():
    """Main function to orchestrate all processes"""
    print("\n" + "="*60)
    print("🚀 STARTING HUGGINGFACE MODEL DOWNLOADER - MULTI-PROCESS")
    print("="*60)
    
    # Ensure directories exist
    os.makedirs("/models", exist_ok=True)
    os.makedirs("/models/.cache", exist_ok=True)
    
    # Set up multiprocessing
    multiprocessing.set_start_method('spawn', force=True)
    manager = multiprocessing.Manager()
    
    # Create IPC queues
    task_queue = manager.Queue()           # Web -> Download Manager
    status_queue = manager.Queue()         # Download Manager/Monitor -> Status Processor
    response_queue = manager.Queue()       # Download Manager -> Status Processor
    monitor_requests_queue = manager.Queue()  # Status Processor -> Monitor Service
    
    # Create shared state
    app_state = AppState(manager)
    
    # Start processes
    processes = []
    
    # 1. Download Manager Process
    download_process = multiprocessing.Process(
        target=download_manager_process,
        args=(task_queue, status_queue, response_queue),
        name="DownloadManager"
    )
    download_process.start()
    processes.append(download_process)
    print("✅ Download Manager Process started")
    
    # 2. Monitoring Service Process  
    monitor_process = multiprocessing.Process(
        target=monitoring_service_process,
        args=(status_queue, monitor_requests_queue),
        name="MonitorService"
    )
    monitor_process.start()
    processes.append(monitor_process)
    print("✅ Monitoring Service Process started")
    
    # 3. Status Update Processor (runs in main process)
    status_processor = multiprocessing.Process(
        target=status_update_processor,
        args=(status_queue, response_queue, app_state, monitor_requests_queue),
        name="StatusProcessor"
    )
    status_processor.start()
    processes.append(status_processor)
    print("✅ Status Update Processor started")
    
    # 4. Flask Web Server (runs in main process)
    flask_app = create_flask_app(app_state, task_queue, monitor_requests_queue)
    
    print(f"💾 Models Directory: /models/")
    print(f"🗂️ Cache Directory: /models/.cache/")
    print(f"🔥 Access URL: http://localhost:5000/hf-downloader/")
    print("="*60)
    
    # Set up signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        print("\n🛑 Shutting down processes...")
        
        # Send shutdown signals
        task_queue.put({'type': 'shutdown'})
        monitor_requests_queue.put({'type': 'shutdown'})
        
        # Wait for processes to finish
        for process in processes:
            process.join(timeout=5)
            if process.is_alive():
                process.terminate()
        
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Start Flask app (this blocks)
        flask_app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)
    except KeyboardInterrupt:
        signal_handler(None, None)


if __name__ == '__main__':
    main()