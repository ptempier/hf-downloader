#!/usr/bin/env python3

import requests
import time
import json

def test_status_endpoint():
    """Test the status endpoint while simulating a download"""
    base_url = "http://localhost:5000"
    
    print("🧪 Testing status endpoint...")
    
    # Test 1: Check initial status
    print("\n1. Testing initial status...")
    try:
        response = requests.get(f"{base_url}/api/download/status")
        if response.status_code == 200:
            status = response.json()
            print(f"✅ Initial status: {json.dumps(status, indent=2)}")
        else:
            print(f"❌ Failed to get status: {response.status_code}")
            return
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("Make sure the Flask app is running on localhost:5000")
        return
    
    # Test 2: Start a download and monitor status
    print("\n2. Starting download and monitoring status...")
    try:
        # Start download
        download_data = {
            "repo_id": "microsoft/DialoGPT-small",
            "quant_pattern": ""
        }
        
        response = requests.post(f"{base_url}/download", json=download_data)
        if response.status_code == 200:
            print("✅ Download started successfully")
        else:
            print(f"❌ Failed to start download: {response.status_code} - {response.text}")
            return
        
        # Monitor status for 30 seconds
        print("\n3. Monitoring status updates...")
        for i in range(30):
            try:
                response = requests.get(f"{base_url}/api/download/status")
                if response.status_code == 200:
                    status = response.json()
                    progress = status.get('progress', 0)
                    status_msg = status.get('status', 'unknown')
                    current_file = status.get('current_file', '')
                    
                    print(f"[{i+1:2d}s] Status: {status_msg} | Progress: {progress:5.1f}% | {current_file}")
                    
                    if status_msg in ['completed', 'error']:
                        print(f"✅ Download finished with status: {status_msg}")
                        break
                else:
                    print(f"❌ Status request failed: {response.status_code}")
                
                time.sleep(1)
                
            except Exception as e:
                print(f"❌ Status check failed: {e}")
        
        print("\n✅ Status monitoring test completed")
        
    except Exception as e:
        print(f"❌ Download test failed: {e}")

if __name__ == "__main__":
    test_status_endpoint()