#!/usr/bin/env python3
"""
Shared utilities for HF Downloader
Common functions used across multiple modules
"""

import os
import re
import datetime
from collections import defaultdict
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


def calculate_downloaded_size(local_dir, cache_dir, repo_id):
    """Calculate total bytes downloaded by checking both final and cache directories"""
    total_downloaded = 0
    
    # Check final destination files
    if os.path.exists(local_dir):
        local_path = Path(local_dir)
        for file_path in local_path.rglob('*'):
            if file_path.is_file():
                try:
                    total_downloaded += file_path.stat().st_size
                except (OSError, IOError):
                    continue
    
    # Check cache for incomplete files and blobs
    cache_repo_dir = Path(cache_dir) / f"models--{repo_id.replace('/', '--')}"
    if cache_repo_dir.exists():
        for file_path in cache_repo_dir.rglob('*'):
            if file_path.is_file():
                try:
                    total_downloaded += file_path.stat().st_size
                except (OSError, IOError):
                    continue
    
    return total_downloaded


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