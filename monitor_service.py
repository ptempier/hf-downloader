#!/usr/bin/env python3
"""
Monitoring Service Process
Monitors file system and tracks download progress
Communicates via IPC queues only
"""

import os
import time
import traceback
from pathlib import Path


def get_file_size_from_bytes(size_bytes):
    """Convert bytes to human readable format"""
    if size_bytes == 0:
        return '0 B'
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def calculate_downloaded_size(local_dir, cache_dir, repo_id):
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
    
    total_time = time.time() - start_total
    
    print(f"⏱️ Monitor scan: Local={local_time:.3f}s ({local_files_count} files), "
          f"Cache={cache_time:.3f}s ({cache_files_count} files), "
          f"Total={total_time:.3f}s ({get_file_size_from_bytes(total_downloaded)})")
    
    return total_downloaded


def monitoring_service_process(status_queue, monitor_requests_queue):
    """Main monitoring service process loop"""
    print("📊 Monitoring Service Process Started")
    
    # Track current monitoring state
    current_monitor = None
    last_downloaded_bytes = 0
    
    while True:
        try:
            # Check for new monitoring requests (non-blocking)
            try:
                request = monitor_requests_queue.get_nowait()
                print(f"📨 Monitor request: {request}")
                
                if request['type'] == 'start_monitor':
                    current_monitor = {
                        'repo_id': request['repo_id'],
                        'local_dir': request['local_dir'],
                        'total_expected_bytes': request['total_expected_bytes'],
                        'start_time': time.time()
                    }
                    last_downloaded_bytes = 0
                    print(f"📊 Started monitoring {current_monitor['repo_id']}")
                    
                elif request['type'] == 'stop_monitor':
                    if current_monitor:
                        print(f"🛑 Stopped monitoring {current_monitor['repo_id']}")
                    current_monitor = None
                    last_downloaded_bytes = 0
                    
                elif request['type'] == 'shutdown':
                    print("🛑 Monitoring Service shutting down")
                    break
                    
            except:
                # No request waiting, continue monitoring
                pass
            
            # Perform monitoring if active
            if current_monitor:
                loop_start = time.time()
                
                cache_dir = "/models/.cache"
                repo_id = current_monitor['repo_id']
                local_dir = current_monitor['local_dir']
                total_expected_bytes = current_monitor['total_expected_bytes']
                
                # Calculate current downloaded bytes
                downloaded_bytes = calculate_downloaded_size(local_dir, cache_dir, repo_id)
                
                # Calculate progress
                if total_expected_bytes > 0:
                    progress = min(95, (downloaded_bytes / total_expected_bytes) * 100)
                    progress_info = f"{get_file_size_from_bytes(downloaded_bytes)} / {get_file_size_from_bytes(total_expected_bytes)}"
                else:
                    progress = min(95, 10 + (downloaded_bytes / (1024 * 1024 * 100)))
                    progress_info = f"{get_file_size_from_bytes(downloaded_bytes)} downloaded"
                
                # Determine status
                is_progressing = downloaded_bytes > last_downloaded_bytes
                status_msg = "Downloading..." if is_progressing else "Processing..."
                
                # Send updated status
                status_update = {
                    'progress': progress,
                    'status': 'downloading',
                    'current_file': f"{status_msg} ({progress_info})",
                    'downloaded_bytes': downloaded_bytes,
                    'monitor_time': time.time() - loop_start
                }
                
                status_queue.put(status_update)
                last_downloaded_bytes = downloaded_bytes
                
                print(f"📊 Progress: {progress:.1f}% - {progress_info}")
            
            # Sleep for monitoring interval
            time.sleep(2)  # Monitor every 2 seconds
            
        except Exception as e:
            print(f"❌ Error in monitoring service: {e}")
            traceback.print_exc()
            time.sleep(5)  # Wait longer on error


if __name__ == '__main__':
    print("Monitoring Service Process - standalone mode not supported")
    print("This module should be imported and run via multiprocessing")