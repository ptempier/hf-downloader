#!/usr/bin/env python3
"""
Download Manager Process
Handles all download/delete/update operations
Communicates via IPC queues only
"""

import os
import time
import traceback
import shutil
from pathlib import Path
from huggingface_hub import snapshot_download, HfApi
from huggingface_hub.utils import HfHubHTTPError

# Import shared utilities
from utils import get_file_size_from_bytes, validate_repo_id, validate_model_path


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


def perform_download(repo_id, quant_pattern, status_queue):
    """Perform the actual download operation"""
    try:
        print(f"\n=== DOWNLOAD STARTED ===")
        print(f"Repository ID: {repo_id}")
        print(f"Quantization Pattern: '{quant_pattern}'")

        # Send initial status
        status_queue.put({
            'progress': 0,
            'status': 'starting',
            'current_file': 'Initializing download...',
            'downloaded_files': 0,
            'downloaded_bytes': 0,
            'total_bytes': 0,
            'repo_id': repo_id,
            'start_time': time.time()
        })

        local_dir = f"/models/{repo_id}"
        os.makedirs(local_dir, exist_ok=True)

        allow_patterns = [f"*{quant_pattern}*"] if quant_pattern.strip() else None

        # Get repository info
        status_queue.put({
            'progress': 5,
            'status': 'downloading',
            'current_file': 'Getting repository information...'
        })

        total_expected_bytes, expected_files, repo_info = get_repo_info_with_patterns(repo_id, allow_patterns)
        
        if total_expected_bytes > 0:
            print(f"✅ Expected download size: {get_file_size_from_bytes(total_expected_bytes)} ({expected_files} files)")
            status_queue.put({
                'total_bytes': total_expected_bytes,
                'current_file': f"Expected: {get_file_size_from_bytes(total_expected_bytes)} ({expected_files} files)"
            })
        else:
            print(f"⚠️ Could not determine download size - progress will be estimated")
            status_queue.put({'current_file': 'Starting download...'})

        # Set custom cache directory within models folder
        cache_dir = "/models/.cache"
        os.makedirs(cache_dir, exist_ok=True)
        
        print(f"🚀 Starting download...")
        
        # Update status to downloading
        status_queue.put({'status': 'downloading'})
        
        # Perform the actual download
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
        
        # Calculate final size
        total_downloaded = 0
        if os.path.exists(local_dir):
            local_path = Path(local_dir)
            for file_path in local_path.rglob('*'):
                if file_path.is_file():
                    try:
                        total_downloaded += file_path.stat().st_size
                    except (OSError, IOError):
                        continue
        
        status_queue.put({
            'progress': 100,
            'status': 'completed',
            'current_file': f"Download completed! Total size: {get_file_size_from_bytes(total_downloaded)}",
            'downloaded_bytes': total_downloaded
        })
        
        return True, "Download completed successfully"
        
    except HfHubHTTPError as e:
        error_msg = f"HuggingFace error: {str(e)}"
        status_queue.put({'progress': 0, 'status': 'error', 'current_file': error_msg})
        return False, error_msg
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        tb = traceback.format_exc()
        print(f"Download error: {e}\n{tb}")
        status_queue.put({'progress': 0, 'status': 'error', 'current_file': error_msg})
        return False, error_msg


def perform_delete(model_path):
    """Perform model deletion"""
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


def download_manager_process(task_queue, status_queue, response_queue):
    """Main download manager process loop"""
    print("🚀 Download Manager Process Started")
    
    # Set HF_TRANSFER for faster downloads
    os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
    
    while True:
        try:
            # Wait for tasks from web server
            task = task_queue.get()
            print(f"📨 Received task: {task}")
            
            if task['type'] == 'download':
                repo_id = task['repo_id']
                quant_pattern = task.get('quant_pattern', '')
                
                if not validate_repo_id(repo_id):
                    response_queue.put({
                        'task_id': task.get('task_id'),
                        'success': False,
                        'message': 'Repository ID should be in format: username/model-name'
                    })
                    continue
                
                success, message = perform_download(repo_id, quant_pattern, status_queue)
                response_queue.put({
                    'task_id': task.get('task_id'),
                    'success': success,
                    'message': message
                })
                
            elif task['type'] == 'delete':
                model_path = task['model_path']
                success, message = perform_delete(model_path)
                response_queue.put({
                    'task_id': task.get('task_id'),
                    'success': success,
                    'message': message
                })
                
            elif task['type'] == 'shutdown':
                print("🛑 Download Manager shutting down")
                break
                
        except Exception as e:
            print(f"❌ Error in download manager: {e}")
            traceback.print_exc()
            response_queue.put({
                'task_id': task.get('task_id', None),
                'success': False,
                'message': f'Internal error: {str(e)}'
            })


if __name__ == '__main__':
    print("Download Manager Process - standalone mode not supported")
    print("This module should be imported and run via multiprocessing")