#!/usr/bin/env python3

import os
import sys
import json
import traceback
import subprocess
from huggingface_hub.utils import HfHubHTTPError

# Set HF_TRANSFER for faster downloads
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"

# Global variable to track download progress
download_status = {"progress": 0, "status": "idle", "current_file": ""}

def start_download_task(repo_id, quant_pattern, socketio):
    """
    Main download function that handles the model downloading process
    """
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

        # Perform the snapshot download; snapshot_download does not provide fine-grained
        # progress callbacks here, so emit coarse updates before and after.
        # Run snapshot_download in an isolated subprocess to avoid recursion or
        # interpreter-level issues (some environments may cause unexpected
        # RecursionError inside the same process). We serialize args via JSON.
        child_args = json.dumps({
            'repo_id': repo_id,
            'local_dir': local_dir,
            'allow_patterns': allow_patterns
        })

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
        _handle_download_error(socketio, repo_id, e, "HfHubHTTPError")
    except RecursionError as e:
        _handle_recursion_error(socketio, repo_id, e)
    except Exception as e:
        _handle_generic_error(socketio, repo_id, e)

def _handle_download_error(socketio, repo_id, error, error_type):
    """Handle download-specific errors"""
    global download_status
    download_status = {"progress": 0, "status": "error", "current_file": str(error)}
    socketio.emit('download_progress', {
        'progress': 0,
        'status': 'error',
        'message': f'Error downloading {repo_id}: {str(error)}'
    })

def _handle_recursion_error(socketio, repo_id, error):
    """Handle recursion errors with detailed logging"""
    global download_status
    # Capture detailed recursion information for diagnosis
    tb = traceback.format_exc()
    info = (
        f"RecursionError while downloading {repo_id}: {error}\n"
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
    
    download_status = {"progress": 0, "status": "error", "current_file": str(error)}
    try:
        socketio.emit('download_progress', {
            'progress': 0,
            'status': 'error',
            'message': f'RecursionError during download: {str(error)} (see server logs)'
        })
    except Exception:
        pass

def _handle_generic_error(socketio, repo_id, error):
    """Handle generic errors with logging"""
    global download_status
    tb = traceback.format_exc()
    print(f"Unexpected error: {error}\n{tb}")
    # Save a copy to disk to aid debugging
    try:
        with open('/tmp/hf_downloader_unexpected.log', 'w') as f:
            f.write(f"{error}\n\n{tb}")
    except Exception:
        pass
    
    download_status = {"progress": 0, "status": "error", "current_file": str(error)}
    try:
        socketio.emit('download_progress', {
            'progress': 0,
            'status': 'error',
            'message': f'Unexpected error: {str(error)}'
        })
    except Exception:
        pass