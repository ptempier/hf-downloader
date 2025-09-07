#!/usr/bin/env python3
"""
Migration script to convert existing symlinked models to real files
Run this once to migrate existing downloads.
"""

import os
import shutil
import stat
from pathlib import Path

def is_symlink_or_link(path):
    """Check if path is a symlink or hard link"""
    path_obj = Path(path)
    if path_obj.is_symlink():
        return True, 'symlink'
    
    # Check if it's a hard link (link count > 1)
    try:
        stat_info = path_obj.stat()
        if stat_info.st_nlink > 1:
            return True, 'hardlink'
    except (OSError, FileNotFoundError):
        pass
    
    return False, 'regular'

def copy_and_replace_link(src_path, link_path):
    """Copy the actual file content to replace a link"""
    try:
        # Get the target of the link
        if os.path.islink(link_path):
            target = os.readlink(link_path)
            if not os.path.isabs(target):
                target = os.path.join(os.path.dirname(link_path), target)
        else:
            target = src_path
        
        print(f"  Copying: {target} -> {link_path}")
        
        # Remove the link
        os.unlink(link_path)
        
        # Copy the actual file
        shutil.copy2(target, link_path)
        
        return True
    except Exception as e:
        print(f"  ERROR copying {link_path}: {e}")
        return False

def migrate_model_directory(model_dir):
    """Migrate a single model directory from symlinks to real files"""
    model_path = Path(model_dir)
    if not model_path.exists():
        print(f"Model directory does not exist: {model_dir}")
        return False
    
    print(f"\n🔄 Migrating model: {model_dir}")
    
    total_files = 0
    converted_files = 0
    total_size_before = 0
    total_size_after = 0
    
    # Walk through all files in the model directory
    for root, dirs, files in os.walk(model_dir):
        for file in files:
            file_path = os.path.join(root, file)
            total_files += 1
            
            # Get original size
            try:
                original_size = os.path.getsize(file_path)
                total_size_before += original_size
            except:
                original_size = 0
            
            is_link, link_type = is_symlink_or_link(file_path)
            
            if is_link:
                print(f"  Found {link_type}: {os.path.relpath(file_path, model_dir)}")
                if copy_and_replace_link(file_path, file_path):
                    converted_files += 1
                    
                    # Get new size
                    try:
                        new_size = os.path.getsize(file_path)
                        total_size_after += new_size
                    except:
                        total_size_after += original_size
                else:
                    total_size_after += original_size
            else:
                total_size_after += original_size
    
    print(f"  ✅ Converted {converted_files}/{total_files} files")
    print(f"  📊 Size change: {format_size(total_size_before)} -> {format_size(total_size_after)}")
    
    return converted_files > 0

def format_size(size_bytes):
    """Convert bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

def scan_and_migrate_all_models():
    """Scan /models and migrate all symlinked models"""
    models_dir = "/models"
    
    if not os.path.exists(models_dir):
        print(f"Models directory does not exist: {models_dir}")
        return
    
    print("🚀 Starting migration of all models from symlinks to real files...")
    print("="*60)
    
    migrated_count = 0
    
    # Find all model directories (assume any subdirectory with files is a model)
    for item in os.listdir(models_dir):
        item_path = os.path.join(models_dir, item)
        if os.path.isdir(item_path):
            # Check if this directory contains model files
            has_model_files = False
            for root, dirs, files in os.walk(item_path):
                if any(f.endswith(('.safetensors', '.bin', '.gguf', '.pt', '.pth')) for f in files):
                    has_model_files = True
                    break
            
            if has_model_files:
                if migrate_model_directory(item_path):
                    migrated_count += 1
    
    print("\n" + "="*60)
    print(f"✅ Migration complete! Processed {migrated_count} model directories.")
    print("💡 Your models now use real files instead of symlinks.")
    print("🗑️  You can now safely clear the HuggingFace cache if needed:")
    print("   rm -rf /root/.cache/huggingface/")

def clean_hf_cache():
    """Optional: Clean the HuggingFace cache after migration"""
    cache_dir = "/root/.cache/huggingface"
    
    if not os.path.exists(cache_dir):
        print("No HuggingFace cache found to clean.")
        return
    
    try:
        # Calculate cache size
        total_size = 0
        for root, dirs, files in os.walk(cache_dir):
            for file in files:
                try:
                    total_size += os.path.getsize(os.path.join(root, file))
                except:
                    pass
        
        print(f"\n🗑️  HuggingFace cache size: {format_size(total_size)}")
        
        response = input("Do you want to delete the HuggingFace cache? (y/N): ").strip().lower()
        if response in ['y', 'yes']:
            shutil.rmtree(cache_dir)
            print("✅ HuggingFace cache deleted successfully!")
        else:
            print("Cache kept. You can delete it manually later if needed.")
            
    except Exception as e:
        print(f"Error cleaning cache: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("🔧 HuggingFace Model Migration Tool")
    print("=" * 60)
    print("This script will convert symlinked model files to real files.")
    print("This ensures your models are stored directly in /models/")
    print()
    
    # Scan and migrate
    scan_and_migrate_all_models()
    
    # Offer to clean cache
    print()
    clean_hf_cache()
    
    print("\n🎉 All done! Your models are now stored as real files in /models/")