#!/usr/bin/env python3

import os
import shutil

def delete_model_task(model_path):
    """
    Delete a model directory
    
    Args:
        model_path (str): Path to the model directory to delete
    
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        print(f"\n=== MODEL DELETE STARTED ===")
        print(f"Model path: {model_path}")
        
        # Validate path
        if not _validate_model_path(model_path):
            error_msg = "Invalid model path: must be within /models/ directory"
            print(f"❌ {error_msg}")
            return False, error_msg
        
        if os.path.exists(model_path):
            # Get some info about what we're deleting
            size_info = _get_directory_info(model_path)
            print(f"Deleting directory: {model_path}")
            print(f"Directory info: {size_info}")
            
            # Perform the deletion
            shutil.rmtree(model_path)
            
            success_msg = f'Model deleted successfully ({size_info})'
            print(f"✅ {success_msg}")
            return True, success_msg
        else:
            error_msg = 'Model path not found'
            print(f"❌ {error_msg}: {model_path}")
            return False, error_msg
            
    except PermissionError as e:
        error_msg = f'Permission denied: {str(e)}'
        print(f"❌ Permission error: {error_msg}")
        return False, error_msg
    except OSError as e:
        error_msg = f'OS error deleting model: {str(e)}'
        print(f"❌ OS error: {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = f'Unexpected error deleting model: {str(e)}'
        print(f"❌ Unexpected error: {error_msg}")
        return False, error_msg

def _validate_model_path(model_path):
    """
    Validate that the model path is safe to delete
    
    Args:
        model_path (str): Path to validate
    
    Returns:
        bool: True if path is valid and safe to delete
    """
    if not model_path or not isinstance(model_path, str):
        return False
    
    # Must be within /models/ directory
    if not model_path.startswith('/models/'):
        return False
    
    # Normalize path to prevent directory traversal
    normalized_path = os.path.normpath(model_path)
    if not normalized_path.startswith('/models/'):
        return False
    
    # Should not be the root models directory itself
    if normalized_path == '/models' or normalized_path == '/models/':
        return False
    
    return True

def _get_directory_info(directory_path):
    """
    Get information about a directory (size, file count)
    
    Args:
        directory_path (str): Path to directory
    
    Returns:
        str: Human readable directory information
    """
    try:
        total_size = 0
        file_count = 0
        
        for dirpath, dirnames, filenames in os.walk(directory_path):
            file_count += len(filenames)
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                except (OSError, IOError):
                    # Skip files that can't be accessed
                    pass
        
        # Convert size to human readable format
        size_str = _format_file_size(total_size)
        
        return f"{file_count} files, {size_str}"
        
    except Exception:
        return "unknown size"

def _format_file_size(size_bytes):
    """
    Convert bytes to human readable format
    
    Args:
        size_bytes (int): Size in bytes
    
    Returns:
        str: Human readable size string
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

def delete_specific_files(model_path, file_patterns):
    """
    Delete specific files matching patterns within a model directory
    
    Args:
        model_path (str): Path to the model directory
        file_patterns (list): List of file patterns to match
    
    Returns:
        tuple: (success: bool, message: str, deleted_files: list)
    """
    try:
        if not _validate_model_path(model_path):
            return False, "Invalid model path", []
        
        if not os.path.exists(model_path):
            return False, "Model path not found", []
        
        deleted_files = []
        total_size = 0
        
        for root, dirs, files in os.walk(model_path):
            for file in files:
                file_path = os.path.join(root, file)
                
                # Check if file matches any pattern
                for pattern in file_patterns:
                    if pattern in file or file.endswith(pattern):
                        try:
                            file_size = os.path.getsize(file_path)
                            os.remove(file_path)
                            deleted_files.append(file)
                            total_size += file_size
                        except Exception as e:
                            print(f"Failed to delete {file_path}: {e}")
                        break
        
        if deleted_files:
            size_str = _format_file_size(total_size)
            message = f"Deleted {len(deleted_files)} files ({size_str})"
            return True, message, deleted_files
        else:
            return True, "No files matched the specified patterns", []
            
    except Exception as e:
        return False, f"Error deleting files: {str(e)}", []