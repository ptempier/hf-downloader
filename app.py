#!/usr/bin/env python3

# eventlet must monkey-patch the stdlib before other libraries (Flask/werkzeug)
import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
import os
import traceback
import sys
import json
import subprocess
import threading
from huggingface_hub import snapshot_download
from huggingface_hub.utils import HfHubHTTPError

# Import model management functions
from model_manager import (
    scan_models,
    update_model_func,
    delete_model_func
)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'

# CONFIGURATION: Set your base URL here
# For root hosting: base_url = ""
# For subfolder hosting: base_url = "/myapp" (no trailing slash, no domain)
base_url = "/hf-downloader"   # Set this to your actual base URL path (e.g., "/myapp")

# Use eventlet async mode so the server fully supports websocket transport and background tasks
# Configure Socket.IO with proper path handling for subdirectory deployments
socketio_path = f"{base_url}/socket.io" if base_url else "/socket.io"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', path=socketio_path)

# Set HF_TRANSFER for faster downloads
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"

# Global variable to track download progress
download_status = {"progress": 0, "status": "idle", "current_file": ""}

# Basic request logging
@app.before_request
def log_request():
    print(f"\n📨 {request.method} {request.path}")
    if request.method == 'POST' and request.content_type == 'application/json':
        print(f"📋 Request data: {request.get_json()}")

@app.after_request
def log_response(response):
    print(f"📤 Response: {response.status_code} {response.status}")
    return response

@app.context_processor
def inject_base_url():
    return dict(base_url=base_url)

def download_model(repo_id, quant_pattern):
    global download_status

    print(f"\n=== DOWNLOAD STARTED ===")
    print(f"Repository ID: {repo_id}")
    print(f"Quantization Pattern: '{quant_pattern}'")

    try:
        download_status = {"progress": 0, "status": "starting", "current_file": ""}
        try:
            socketio.emit('download_progress', download_status)
        except Exception:
            # If emit fails (no clients), continue the download and emit when possible
            pass

        local_dir = f"/models/{repo_id}"
        os.makedirs(local_dir, exist_ok=True)

        if quant_pattern.strip():
            allow_patterns = [f"*{quant_pattern}*"]
        else:
            allow_patterns = None

        socketio.emit('download_progress', {
            'progress': 0,
            'status': 'downloading',
            'message': f'Starting download of {repo_id}'
        })

        # FIXED: Force actual files instead of symlinks by setting local_dir_use_symlinks=False
        child_args = json.dumps({
            'repo_id': repo_id,
            'local_dir': local_dir,
            'allow_patterns': allow_patterns,
            'local_dir_use_symlinks': False  # This is the key fix!
        })

        child_cmd = [sys.executable, '-u', '-c',
            'import sys, json; from huggingface_hub import snapshot_download;\n'
            'args = json.loads(sys.argv[1]);\n'
            'snapshot_download(repo_id=args["repo_id"], local_dir=args["local_dir"], '
            'allow_patterns=args.get("allow_patterns"), resume_download=True, '
            'local_dir_use_symlinks=args.get("local_dir_use_symlinks", True))\n',
            child_args
        ]

        env = os.environ.copy()
        env.setdefault('HF_HUB_ENABLE_HF_TRANSFER', '1')

        proc = subprocess.run(child_cmd, capture_output=True, text=True, env=env)
        if proc.returncode != 0:
            # Log child stdout/stderr for diagnosis
            print(f"Snapshot download subprocess failed (rc={proc.returncode})")
            print(proc.stdout)
            print(proc.stderr)
            raise Exception(f"Child download failed: rc={proc.returncode} stderr={proc.stderr}")

        download_status = {"progress": 100, "status": "completed", "current_file": ""}
        try:
            socketio.emit('download_progress', {
                'progress': 100,
                'status': 'completed',
                'message': f'Successfully downloaded {repo_id}'
            })
        except Exception:
            pass

    except HfHubHTTPError as e:
        download_status = {"progress": 0, "status": "error", "current_file": str(e)}
        socketio.emit('download_progress', {
            'progress': 0,
            'status': 'error',
            'message': f'Error downloading {repo_id}: {str(e)}'
        })
    except RecursionError as e:
        # Capture detailed recursion information for diagnosis
        tb = traceback.format_exc()
        info = (
            f"RecursionError while downloading {repo_id}: {e}\n"
            f"Recursion limit: {sys.getrecursionlimit()}\n"
            f"Traceback:\n{tb}"
        )
        print(info)
        # Persist to a file for post-mortem inspection
        try:
            with open('/tmp/hf_downloader_recursion.log', 'w') as f:
                f.write(info)
        except Exception:
            pass
        download_status = {"progress": 0, "status": "error", "current_file": str(e)}
        try:
            socketio.emit('download_progress', {
                'progress': 0,
                'status': 'error',
                'message': f'RecursionError during download: {str(e)} (see server logs)'
            })
        except Exception:
            pass
    except Exception as e:
        tb = traceback.format_exc()
        print(f"Unexpected error: {e}\n{tb}")
        # Save a copy to disk to aid debugging
        try:
            with open('/tmp/hf_downloader_unexpected.log', 'w') as f:
                f.write(f"{e}\n\n{tb}")
        except Exception:
            pass
        download_status = {"progress": 0, "status": "error", "current_file": str(e)}
        try:
            socketio.emit('download_progress', {
                'progress': 0,
                'status': 'error',
                'message': f'Unexpected error: {str(e)}'
            })
        except Exception:
            pass

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    # Return no content to avoid 404 noise when favicon is not provided
    return ('', 204)

@app.route('/download', methods=['POST'])
def start_download():
    data = request.get_json() or {}
    repo_id = data.get('repo_id', '').strip()
    quant_pattern = data.get('quant_pattern', '').strip()

    if not repo_id:
        return jsonify({'error': 'Repository ID is required'}), 400

    if download_status["status"] == "downloading":
        return jsonify({'error': 'Download already in progress'}), 400

    # Use Socket.IO's background task helper so emits work reliably with the selected async mode
    socketio.start_background_task(download_model, repo_id, quant_pattern)

    return jsonify({'message': 'Download started'})

@app.route('/status')
def get_status():
    return jsonify(download_status)

# MODEL MANAGER ROUTES
# Removed /manage route as we now have a unified interface

@app.route('/api/models')
def api_models():
    models = scan_models()
    return jsonify(models)

@app.route('/api/models/update', methods=['POST'])
def api_update_model():
    data = request.get_json() or {}
    repo_id = data.get('repo_id', '').strip()
    quant_pattern = data.get('quant_pattern', '').strip()

    if not repo_id:
        return jsonify({'error': 'Repository ID is required'}), 400

    def update_thread():
        update_model_func(repo_id, quant_pattern)

    thread = threading.Thread(target=update_thread, daemon=True)
    thread.start()

    return jsonify({'message': f'Update started for {repo_id}'})

@app.route('/api/models/delete', methods=['POST'])
def api_delete_model():
    data = request.get_json() or {}
    model_path = data.get('path', '').strip()

    if not model_path or not model_path.startswith('/models/'):
        return jsonify({'error': 'Invalid model path'}), 400

    try:
        success, message = delete_model_func(model_path)
        if success:
            return jsonify({'message': message})
        else:
            return jsonify({'error': message}), 500
    except Exception as e:
        return jsonify({'error': f'Error deleting model: {str(e)}'}), 500

if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 STARTING HUGGINGFACE MODEL DOWNLOADER")
    print("="*50)
    print(f"🔥 Unified Interface: http://localhost:5000{base_url}/")
    print(f"💾 Models Directory: /models/")
    if base_url:
        print(f"🌍 Configured Base URL Path: {base_url}")
        print(f"🔌 Socket.IO Path: {socketio_path}")
    print("="*50)

    os.makedirs("/models", exist_ok=True)

    socketio.run(app, debug=True, host='0.0.0.0', port=5000)