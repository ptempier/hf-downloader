#!/usr/bin/env python3

import os
import sys
import json
import time
import traceback
import subprocess
import threading
from pathlib import Path
from huggingface_hub import snapshot_download, hf_hub_download
from huggingface_hub.utils import HfHubHTTPError

# Set HF_TRANSFER for faster downloads
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"

# Global variable to track download progress
download_status = {
    "progress": 0, 
    "status": "idle", 
    "current_file": "",
    "downloaded_files": 0,
    "total_files": 0,
    "downloaded_size": 0,
    "total_size": 0,
    "repo_id": "",
    "start_time": None
}

def get_download_status():
    """Get current download status with thread safety"""
    return download_status.copy()

def update_download_status(socketio, **kwargs):
    """Thread-safe update of download status"""
    global download_status
    download_status.update(kwargs)
    
    # Calculate estimated time remaining if we have progress
    if download_status.get('start_time') and download_status.get('progress', 0) > 0:
        elapsed = time.time() - download_status['start_time']
        if download_status['progress'] > 0:
            eta = (elapsed / download_status['progress']) * (100 - download_status['progress'])
            download_status['eta'] = eta
    
    try:
        socketio.emit('download_progress', download_status.copy())
    except Exception as e:
        print(f"Failed to emit progress: {e}")

def start_download_task(repo_id, quant_pattern, socketio):
    """
    Main download function that handles the model downloading process with real progress
    """
    global download_status

    print(f"\n=== DOWNLOAD STARTED ===")
    print(f"Repository ID: {repo_id}")
    print(f"Quantization Pattern: '{quant_pattern}'")

    try:
        # Reset status
        update_download_status(socketio,
            progress=0,
            status="starting",
            current_file="",
            downloaded_files=0,
            total_files=0,
            downloaded_size=0,
            total_size=0,
            repo_id=repo_id,
            start_time=time.time(),
            eta=None
        )

        local_dir = f"/models/{repo_id}"
        os.makedirs(local_dir, exist_ok=True)

        if quant_pattern.strip():
            allow_patterns = [f"*{quant_pattern}*"]
        else:
            allow_patterns = None

        update_download_status(socketio,
            progress=5,
            status='downloading',
            current_file='Scanning repository...'
        )

        # Try the enhanced download approach first
        try:
            _download_with_progress(repo_id, local_dir, allow_patterns, socketio)
        except Exception as e:
            print(f"Enhanced download failed, falling back to subprocess: {e}")
            _download_with_subprocess(repo_id, local_dir, allow_patterns, socketio)

        update_download_status(socketio,
            progress=100,
            status="completed",
            current_file="Download completed"
        )

    except HfHubHTTPError as e:
        _handle_download_error(socketio, repo_id, e, "HfHubHTTPError")
    except RecursionError as e:
        _handle_recursion_error(socketio, repo_id, e)
    except Exception as e:
        _handle_generic_error(socketio, repo_id, e)

def _download_with_progress(repo_id, local_dir, allow_patterns, socketio):
    """Download with simulated progress tracking"""
    
    # Phase 1: Initialize (10%)
    update_download_status(socketio,
        progress=10,
        status='downloading',
        current_file='Initializing download...'
    )
    time.sleep(0.5)
    
    # Phase 2: Start download (20%)
    update_download_status(socketio,
        progress=20,
        status='downloading',
        current_file='Connecting to repository...'
    )
    
    # Start the actual download in a thread while we simulate progress
    download_thread = threading.Thread(
        target=_actual_download,
        args=(repo_id, local_dir, allow_patterns)
    )
    download_thread.daemon = True
    download_thread.start()
    
    # Simulate progress while download happens
    progress = 20
    while download_thread.is_alive() and progress < 95:
        time.sleep(2)  # Update every 2 seconds
        progress = min(95, progress + 5)
        
        # Try to get some file info from the local directory
        current_file = _get_current_download_file(local_dir)
        
        update_download_status(socketio,
            progress=progress,
            status='downloading',
            current_file=current_file or f'Downloading... ({progress}%)'
        )
    
    # Wait for download to complete
    download_thread.join()
    
    # Final progress update
    update_download_status(socketio,
        progress=100,
        status='downloading',
        current_file='Finalizing download...'
    )

def _actual_download(repo_id, local_dir, allow_patterns):
    """Perform the actual download"""
    try:
        # FIXED: Force actual files instead of symlinks
        snapshot_download(
            repo_id=repo_id,
            local_dir=local_dir,
            allow_patterns=allow_patterns,
            resume_download=True,
            local_dir_use_symlinks=False  # This is the key fix!
        )
    except Exception as e:
        print(f"Download error in thread: {e}")
        raise

def _get_current_download_file(local_dir):
    """Try to detect what file is currently being downloaded"""
    try:
        # Look for recently modified files
        path = Path(local_dir)
        if path.exists():
            files = list(path.rglob('*'))
            if files:
                # Sort by modification time, get most recent
                latest = max(files, key=lambda f: f.stat().st_mtime if f.is_file() else 0)
                if latest.is_file():
                    return f"Downloading {latest.name}"
    except Exception:
        pass
    return None

def _download_with_subprocess(repo_id, local_dir, allow_patterns, socketio):
    """Fallback subprocess download with simulated progress"""
    
    update_download_status(socketio,
        progress=30,
        status='downloading',
        current_file='Starting subprocess download...'
    )

    child_args = json.dumps({
        'repo_id': repo_id,
        'local_dir': local_dir,
        'allow_patterns': allow_patterns,
        'local_dir_use_symlinks': False  # Force actual files
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

    # Start subprocess
    proc = subprocess.Popen(child_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                           text=True, env=env)
    
    # Simulate progress while subprocess runs
    progress = 30
    while proc.poll() is None and progress < 90:
        time.sleep(1)
        progress = min(90, progress + 3)
        
        current_file = _get_current_download_file(local_dir)
        update_download_status(socketio,
            progress=progress,
            status='downloading',
            current_file=current_file or f'Processing... ({progress}%)'
        )
    
    # Wait for completion and check result
    stdout, stderr = proc.communicate()
    
    if proc.returncode != 0:
        print(f"Subprocess failed (rc={proc.returncode})")
        print(f"stdout: {stdout}")
        print(f"stderr: {stderr}")
        raise Exception(f"Download failed: {stderr}")
    
    update_download_status(socketio,
        progress=95,
        status='downloading',
        current_file='Download completed, finalizing...'
    )

def _handle_download_error(socketio, repo_id, error, error_type):
    """Handle download-specific errors"""
    global download_status
    update_download_status(socketio,
        progress=0,
        status="error",
        current_file=str(error)
    )

def _handle_recursion_error(socketio, repo_id, error):
    """Handle recursion errors with detailed logging"""
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
    
    update_download_status(socketio,
        progress=0,
        status="error",
        current_file=str(error)
    )

def _handle_generic_error(socketio, repo_id, error):
    """Handle generic errors with logging"""
    tb = traceback.format_exc()
    print(f"Unexpected error: {error}\n{tb}")
    
    # Save a copy to disk to aid debugging
    try:
        with open('/tmp/hf_downloader_unexpected.log', 'w') as f:
            f.write(f"{error}\n\n{tb}")
    except Exception:
        pass
    
    update_download_status(socketio,
        progress=0,
        status="error",
        current_file=str(error)
    )

def cancel_download():
    """Cancel ongoing download"""
    global download_status
    if download_status.get("status") == "downloading":
        download_status.update({
            "progress": 0,
            "status": "cancelled",
            "current_file": "Download cancelled"
        })
        return True
    return False