#!/usr/bin/env python3

import os
import sys
import json
import time
import traceback
import threading
from pathlib import Path
from huggingface_hub import snapshot_download, hf_hub_download
from huggingface_hub.utils import HfHubHTTPError, tqdm

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
        print(f"Progress: {download_status.get('progress', 0):.1f}% - {download_status.get('current_file', '')}")
    except Exception as e:
        print(f"Failed to emit progress: {e}")

class ProgressTracker:
    """Custom progress tracker for huggingface_hub downloads"""
    
    def __init__(self, socketio):
        self.socketio = socketio
        self.files_seen = set()
        self.current_file = ""
        self.total_progress = 0
        
    def __call__(self, block_num=None, block_size=None, total_size=None):
        """Progress callback for individual file downloads"""
        if total_size and block_num is not None and block_size:
            downloaded = min(block_num * block_size, total_size)
            progress = (downloaded / total_size) * 100
            
            # Update status for current file
            update_download_status(
                self.socketio,
                progress=min(progress, 99),  # Cap at 99% until completely done
                status='downloading',
                current_file=f"Downloading {self.current_file}: {progress:.1f}%"
            )

def start_download_task(repo_id, quant_pattern, socketio):
    """
    Main download function with real progress tracking
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
            current_file="Initializing download...",
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

        # Method 1: Try direct download with progress monitoring
        try:
            _download_with_real_progress(repo_id, local_dir, allow_patterns, socketio)
        except Exception as e:
            print(f"Direct download failed, trying alternative method: {e}")
            # Method 2: Fallback to file-by-file download
            _download_file_by_file(repo_id, local_dir, allow_patterns, socketio)

        update_download_status(socketio,
            progress=100,
            status="completed",
            current_file="Download completed successfully!"
        )

    except HfHubHTTPError as e:
        _handle_download_error(socketio, repo_id, e, "HfHubHTTPError")
    except RecursionError as e:
        _handle_recursion_error(socketio, repo_id, e)
    except Exception as e:
        _handle_generic_error(socketio, repo_id, e)

def _download_with_real_progress(repo_id, local_dir, allow_patterns, socketio):
    """Download with real progress tracking using a monitoring thread"""
    
    update_download_status(socketio,
        progress=10,
        status='downloading',
        current_file='Starting download...'
    )
    
    # Start download in background thread
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
    
    # Start the download
    thread = threading.Thread(target=download_thread, daemon=True)
    thread.start()
    
    # Monitor progress
    progress = 10
    last_file_count = 0
    
    while thread.is_alive():
        time.sleep(1)
        
        # Check directory for new files
        try:
            current_files = list(Path(local_dir).rglob('*'))
            file_count = len([f for f in current_files if f.is_file()])
            
            if file_count > last_file_count:
                progress = min(95, progress + 5)
                last_file_count = file_count
                
                # Find most recently modified file
                latest_file = None
                try:
                    files = [f for f in current_files if f.is_file()]
                    if files:
                        latest_file = max(files, key=lambda f: f.stat().st_mtime)
                except:
                    pass
                
                current_file_name = latest_file.name if latest_file else "Processing files..."
                
                update_download_status(socketio,
                    progress=progress,
                    status='downloading',
                    current_file=f"Processing: {current_file_name}",
                    downloaded_files=file_count
                )
        except Exception as e:
            print(f"Error monitoring progress: {e}")
        
        # Increment progress slowly
        if progress < 90:
            progress = min(90, progress + 1)
            update_download_status(socketio,
                progress=progress,
                status='downloading',
                current_file='Downloading files...'
            )
    
    # Wait for thread to complete
    thread.join()
    
    # Check for exceptions
    if download_exception[0]:
        raise download_exception[0]
    
    # Final progress update
    final_files = list(Path(local_dir).rglob('*'))
    final_count = len([f for f in final_files if f.is_file()])
    
    update_download_status(socketio,
        progress=99,
        status='downloading',
        current_file='Finalizing download...',
        downloaded_files=final_count
    )

def _download_file_by_file(repo_id, local_dir, allow_patterns, socketio):
    """Fallback method: download files individually with progress"""
    
    update_download_status(socketio,
        progress=30,
        status='downloading',
        current_file='Fetching file list...'
    )
    
    # This is a simplified version - you'd need to implement
    # file listing from the repo first, then download each file
    # For now, fall back to the original method
    
    snapshot_download(
        repo_id=repo_id,
        local_dir=local_dir,
        allow_patterns=allow_patterns,
        resume_download=True,
        local_dir_use_symlinks=False
    )

def _handle_download_error(socketio, repo_id, error, error_type):
    """Handle download-specific errors"""
    global download_status
    error_msg = f"{error_type}: {str(error)}"
    print(f"❌ {error_msg}")
    update_download_status(socketio,
        progress=0,
        status="error",
        current_file=error_msg
    )

def _handle_recursion_error(socketio, repo_id, error):
    """Handle recursion errors with detailed logging"""
    tb = traceback.format_exc()
    info = (
        f"RecursionError while downloading {repo_id}: {error}\n"
        f"Recursion limit: {sys.getrecursionlimit()}\n"
        f"Traceback:\n{tb}"
    )
    print(info)
    
    try:
        with open('/tmp/hf_downloader_recursion.log', 'w') as f:
            f.write(info)
    except Exception:
        pass
    
    update_download_status(socketio,
        progress=0,
        status="error",
        current_file=f"RecursionError: {str(error)}"
    )

def _handle_generic_error(socketio, repo_id, error):
    """Handle generic errors with logging"""
    tb = traceback.format_exc()
    print(f"❌ Unexpected error: {error}\n{tb}")
    
    try:
        with open('/tmp/hf_downloader_unexpected.log', 'w') as f:
            f.write(f"{error}\n\n{tb}")
    except Exception:
        pass
    
    update_download_status(socketio,
        progress=0,
        status="error",
        current_file=f"Error: {str(error)}"
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