#!/usr/bin/env python3

import os
from huggingface_hub import snapshot_download
from huggingface_hub.utils import HfHubHTTPError

# Set HF_TRANSFER for faster downloads
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"

def update_model_task(repo_id, quant_pattern=""):
    """
    Update/re-download a model
    
    Args:
        repo_id (str): Repository ID in format 'username/model-name'
        quant_pattern (str): Pattern for quantization files (optional)
    
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        print(f"\n=== MODEL UPDATE STARTED ===")
        print(f"Repository ID: {repo_id}")
        print(f"Quantization Pattern: '{quant_pattern}'")
        
        if not repo_id or '/' not in repo_id:
            return False, 'Invalid repository id'

        local_dir = f"/models/{repo_id}"
        
        # Create directory if it doesn't exist
        os.makedirs(local_dir, exist_ok=True)
        
        # Convert user pattern to allow_patterns list
        if quant_pattern.strip():
            allow_patterns = [f"*{quant_pattern}*"]
            print(f"Using allow patterns: {allow_patterns}")
        else:
            allow_patterns = None
            print("No quantization pattern specified, downloading all files")
        
        print(f"Updating model to: {local_dir}")
        
        snapshot_download(
            repo_id=repo_id,
            local_dir=local_dir,
            allow_patterns=allow_patterns,
            resume_download=True
        )
        
        print(f"✅ Model {repo_id} updated successfully")
        return True, "Model updated successfully"
        
    except HfHubHTTPError as e:
        error_msg = f"Error updating model: {str(e)}"
        print(f"❌ HfHubHTTPError: {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"❌ Unexpected error: {error_msg}")
        return False, error_msg

def validate_repo_id(repo_id):
    """
    Validate repository ID format
    
    Args:
        repo_id (str): Repository ID to validate
    
    Returns:
        bool: True if valid, False otherwise
    """
    if not repo_id or not isinstance(repo_id, str):
        return False
    
    # Basic validation: should contain at least one '/' and no spaces
    if '/' not in repo_id or ' ' in repo_id:
        return False
    
    # Split and check parts
    parts = repo_id.split('/')
    if len(parts) != 2:
        return False
    
    username, model_name = parts
    if not username or not model_name:
        return False
    
    return True