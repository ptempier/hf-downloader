#!/usr/bin/env python3

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
from huggingface_hub.utils import HfHubHTTPError
from model_manager import scan_models, update_model_func, delete_model_func

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'

# CONFIGURATION
base_url = "/hf-downloader"

# Configure Socket.IO
socketio_path = f"{base_url}/socket.io" if base_url else "/socket.io"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', path=socketio_path)

# Set environment for faster downloads
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"

# Global download status
download_status = {"progress": 0, "status": "idle", "current_file": ""}

@app.context_processor
def inject_base_url():
    return dict(base_url=base_url)

def download_model(repo_id, quant_pattern):
    global download_status
    
    try:
        download_status = {"progress": 0, "status": "starting", "current_file": ""}
        socketio.emit('download_progress', download_status)

        local_dir = f"/models/{repo_id}"
        os.makedirs(local_dir, exist_ok=True)

        # Prepare subprocess arguments
        child_args = json.dumps({
            'repo_id': repo_id,
            'local_dir': local_dir,
            'allow_patterns': [f"*{quant_pattern}*"] if quant_pattern.strip() else None
        })

        socketio.emit('download_progress', {
            'progress': 0,
            'status': 'downloading',
            'message': f'Starting download of {repo_id}'
        })

        # Run download in subprocess
        child_cmd = [sys.executable, '-u', '-c',
            'import sys, json; from huggingface_hub import snapshot_download;\n'
            'args = json.loads(sys.argv[1]);\n'
            'snapshot_download(repo_id=args["repo_id"], local_dir=args["local_dir"], '
            'allow_patterns=args.get("allow_patterns"), resume_download=True)\n',
            child_args
        ]

        env = os.environ.copy()
        env.setdefault('HF_HUB_ENABLE_HF_TRANSFER', '1')

        proc = subprocess.run(child_cmd, capture_output=True, text=True, env=env)
        if proc.returncode != 0:
            raise Exception(f"Download failed: {proc.stderr}")

        download_status = {"progress": 100, "status": "completed", "current_file": ""}
        socketio.emit('download_progress', {
            'progress': 100,
            'status': 'completed',
            'message': f'Successfully downloaded {repo_id}'
        })

    except Exception as e:
        error_msg = str(e)
        download_status = {"progress": 0, "status": "error", "current_file": error_msg}
        socketio.emit('download_progress', {
            'progress': 0,
            'status': 'error',
            'message': f'Error: {error_msg}'
        })
        
        # Log detailed error for debugging
        with open('/tmp/hf_downloader_error.log', 'w') as f:
            f.write(f"{e}\n\n{traceback.format_exc()}")

# Routes
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

    if download_status["status"] == "downloading":
        return jsonify({'error': 'Download already in progress'}), 400

    socketio.start_background_task(download_model, repo_id, quant_pattern)
    return jsonify({'message': 'Download started'})

@app.route('/status')
def get_status():
    return jsonify(download_status)

@app.route('/manage')
def model_manager():
    return render_template('model_manager.html')

@app.route('/api/models')
def api_models():
    return jsonify(scan_models())

@app.route('/api/models/update', methods=['POST'])
def api_update_model():
    data = request.get_json() or {}
    repo_id = data.get('repo_id', '').strip()
    quant_pattern = data.get('quant_pattern', '').strip()

    if not repo_id:
        return jsonify({'error': 'Repository ID is required'}), 400

    threading.Thread(target=update_model_func, args=(repo_id, quant_pattern), daemon=True).start()
    return jsonify({'message': f'Update started for {repo_id}'})

@app.route('/api/models/delete', methods=['POST'])
def api_delete_model():
    data = request.get_json() or {}
    model_path = data.get('path', '').strip()

    if not model_path or not model_path.startswith('/models/'):
        return jsonify({'error': 'Invalid model path'}), 400

    try:
        success, message = delete_model_func(model_path)
        return jsonify({'message': message} if success else {'error': message}), 200 if success else 500
    except Exception as e:
        return jsonify({'error': f'Error deleting model: {str(e)}'}), 500

if __name__ == '__main__':
    print(f"\n{'='*50}")
    print("🚀 STARTING HUGGINGFACE MODEL DOWNLOADER")
    print(f"{'='*50}")
    print(f"🔥 Download Interface: http://localhost:5000{base_url}/")
    print(f"📁 Model Manager: http://localhost:5000{base_url}/manage")
    print(f"💾 Models Directory: /models/")
    if base_url:
        print(f"🌐 Base URL Path: {base_url}")
    print(f"{'='*50}")

    os.makedirs("/models", exist_ok=True)
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)