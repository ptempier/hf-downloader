#!/usr/bin/env python3

import os
import re
import shutil
import datetime
from collections import defaultdict
from huggingface_hub import snapshot_download
from huggingface_hub.utils import HfHubHTTPError

os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"

def get_file_size_from_bytes(size_bytes):
    """Convert bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

def get_file_info(file_path):
    """Get file metadata safely"""
    try:
        size_bytes = os.path.getsize(file_path)
        mtime = os.path.getmtime(file_path)
        date_str = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
    except Exception:
        size_bytes = mtime = 0
        date_str = ''
    
    return {
        'name': os.path.basename(file_path),
        'path': file_path,
        'size': get_file_size_from_bytes(size_bytes),
        'size_bytes': size_bytes,
        'mtime': mtime,
        'date': date_str
    }

def group_model_files(files):
    """Group model files by common patterns"""
    groups = defaultdict(list)
    ungrouped = []
    
    for file_path in files:
        filename = os.path.basename(file_path)
        
        # Safetensors files: model-00001-of-00003.safetensors
        if match := re.match(r'(.+)-(\d+)-of-(\d+)\.safetensors$', filename):
            base_name, _, total_parts = match.groups()
            groups[f"{base_name}-*-of-{total_parts}.safetensors"].append(file_path)
        # GGUF files
        elif filename.endswith('.gguf'):
            parent_dir = os.path.basename(os.path.dirname(file_path))
            groups[f"{parent_dir}/*.gguf"].append(file_path)
        # PyTorch model files
        elif match := re.match(r'pytorch_model-(\d+)-of-(\d+)\.bin$', filename):
            total_parts = match.group(2)
            groups[f"pytorch_model-*-of-{total_parts}.bin"].append(file_path)
        else:
            ungrouped.append(file_path)
    
    return groups, ungrouped

def scan_models():
    """Scan /models directory for existing models"""
    models_dir = "/models"
    if not os.path.exists(models_dir):
        return []
    
    models = []
    model_extensions = ['.safetensors', '.bin', '.gguf', '.pt', '.pth']
    
    for root, dirs, files in os.walk(models_dir):
        # Get model files
        model_files = [
            os.path.join(root, f) for f in files 
            if any(f.endswith(ext) for ext in model_extensions)
        ]
        
        if not model_files:
            continue
            
        relative_path = os.path.relpath(root, models_dir)
        groups, ungrouped = group_model_files(model_files)
        
        model_info = {
            'name': relative_path,
            'path': root,
            'groups': [],
            'individual_files': [get_file_info(f) for f in ungrouped]
        }
        
        # Add grouped files
        for group_name, group_files in groups.items():
            file_objs = [get_file_info(fpath) for fpath in group_files]
            total_size = sum(f['size_bytes'] for f in file_objs)
            
            model_info['groups'].append({
                'name': group_name,
                'files': file_objs,
                'count': len(file_objs),
                'size': get_file_size_from_bytes(total_size),
                'size_bytes': total_size
            })
        
        # Calculate total size
        total_size = sum(get_file_info(f)['size_bytes'] for f in model_files)
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
        os.makedirs(local_dir, exist_ok=True)
        
        allow_patterns = [f"*{quant_pattern}*"] if quant_pattern.strip() else None
        
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