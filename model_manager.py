#!/usr/bin/env python3

import os
import re
import shutil
import datetime
from collections import defaultdict
from huggingface_hub import snapshot_download
from huggingface_hub.utils import HfHubHTTPError
import shutil

# Set HF_TRANSFER for faster downloads
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"

def get_file_size_from_bytes(size_bytes):
    """Convert bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

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
            # Group all .gguf files together per model
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

def scan_models():
    """Scan /models directory for existing models"""
    models_dir = "/models"
    if not os.path.exists(models_dir):
        return []
    
    models = []
    
    for root, dirs, files in os.walk(models_dir):
        if files:  # Only process directories with files
            # Get model files (common model file extensions)
            model_files = []
            for file in files:
                if any(file.endswith(ext) for ext in ['.safetensors', '.bin', '.gguf', '.pt', '.pth']):
                    full_path = os.path.join(root, file)
                    model_files.append(full_path)
            
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
                    # Convert group files into file objects with metadata (size, mtime, formatted date)
                    file_objs = []
                    for fpath in group_files:
                        try:
                            size_b = os.path.getsize(fpath) if os.path.exists(fpath) else 0
                        except Exception:
                            size_b = 0
                        try:
                            mtime = os.path.getmtime(fpath) if os.path.exists(fpath) else 0
                        except Exception:
                            mtime = 0
                        date_str = ''
                        if mtime:
                            try:
                                date_str = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
                            except Exception:
                                date_str = ''

                        file_objs.append({
                            'name': os.path.basename(fpath),
                            'path': fpath,
                            'size': get_file_size_from_bytes(size_b),
                            'size_bytes': size_b,
                            'mtime': mtime,
                            'date': date_str
                        })

                    total_size = sum(f['size_bytes'] for f in file_objs)
                    human_size = get_file_size_from_bytes(total_size)

                    model_info['groups'].append({
                        'name': group_name,
                        'files': file_objs,
                        'count': len(file_objs),
                        'size': human_size,
                        'size_bytes': total_size
                    })
                
                # Add individual files
                for file_path in ungrouped:
                    try:
                        size_bytes = os.path.getsize(file_path) if os.path.exists(file_path) else 0
                    except Exception:
                        size_bytes = 0
                    try:
                        mtime = os.path.getmtime(file_path) if os.path.exists(file_path) else 0
                    except Exception:
                        mtime = 0
                    date_str = ''
                    if mtime:
                        try:
                            date_str = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
                        except Exception:
                            date_str = ''

                    model_info['individual_files'].append({
                        'name': os.path.basename(file_path),
                        'path': file_path,
                        'size': get_file_size_from_bytes(size_bytes),
                        'size_bytes': size_bytes,
                        'mtime': mtime,
                        'date': date_str
                    })
                
                # Calculate total size
                total_size = sum(os.path.getsize(f) for f in model_files if os.path.exists(f))
                model_info['total_size'] = get_file_size_from_bytes(total_size)
                model_info['total_size_bytes'] = total_size
                
                models.append(model_info)
    
    return sorted(models, key=lambda x: x['name'])

def update_model_func(repo_id, quant_pattern=""):
    """Update/re-download a model"""
    try:
        if not repo_id or '/' not in repo_id:
            return False, 'Invalid repository id'

        local_dir = f"/models/{repo_id}"
        
        # Create directory if it doesn't exist
        os.makedirs(local_dir, exist_ok=True)
        
        # Convert user pattern to allow_patterns list
        if quant_pattern.strip():
            allow_patterns = [f"*{quant_pattern}*"]
        else:
            allow_patterns = None
        
        snapshot_download(
            repo_id=repo_id,
            local_dir=local_dir,
            allow_patterns=allow_patterns,
            resume_download=True
        )
        
        return True, "Model updated successfully"
        
    except HfHubHTTPError as e:
        return False, f"Error updating model: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"

def delete_model_func(model_path):
    """Delete a model directory"""
    try:
        if os.path.exists(model_path):
            shutil.rmtree(model_path)
            return True, 'Model deleted successfully'
        else:
            return False, 'Model path not found'
    except Exception as e:
        return False, f'Error deleting model: {str(e)}'
