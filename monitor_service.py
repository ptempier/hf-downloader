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

# Import shared utilities
from utils import get_file_size_from_bytes, calculate_downloaded_size


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
            time.sleep(3)  # Monitor every 3 seconds
            
        except Exception as e:
            print(f"❌ Error in monitoring service: {e}")
            traceback.print_exc()
            time.sleep(5)  # Wait longer on error


if __name__ == '__main__':
    print("Monitoring Service Process - standalone mode not supported")
    print("This module should be imported and run via multiprocessing")