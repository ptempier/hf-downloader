# Hugging Face Model Downloader & Manager

A simple Flask web interface for downloading and managing Hugging Face models with real-time progress tracking.

## Features

### Download Interface (Port 5000)
- Download models from Hugging Face Hub
- Regex pattern filtering for quantization types
- Real-time progress bar using WebSockets
- Download logging and status tracking
- Simple, clean interface

### Model Manager Interface (Port 5001)
- Browse existing models in `/models/` directory
- Group similar model files (safetensors, GGUF, etc.)
- Update existing models
- Delete models with confirmation
- Search and filter models
- Show file sizes and total model sizes

## Installation

1. **Install Python dependencies:**
```bash
pip install -r requirements.txt
```

2. **Create the models directory:**
```bash
mkdir -p /models
# Or adjust the path in the code if you prefer a different location
```

3. **Set up the file structure:**
```
project/
├── app.py                          # Main download server
├── model_manager.py                # Model management server
├── requirements.txt
├── templates/
│   ├── index.html                  # Download interface
│   └── model_manager.html          # Model manager interface
└── static/
    ├── style.css                   # Download interface styles
    ├── model_manager.css           # Model manager styles
    ├── script.js                   # Download interface JavaScript
    └── model_manager.js            # Model manager JavaScript
```

## Usage

### Starting the Server

**Single Server:**
```bash
python app.py
```
Access at: http://localhost:5000

- **Download Interface**: http://localhost:5000/
- **Model Manager**: http://localhost:5000/manage

### Downloading Models

1. Go to http://localhost:5000
2. Enter a repository ID (e.g., `microsoft/DialoGPT-medium`)
3. Optionally add a quantization pattern (e.g., `F16`, `Q4_K_M`, `.gguf`)
4. Click "Start Download"
5. Watch the real-time progress bar

### Managing Models

1. Go to http://localhost:5000/manage
2. Browse your downloaded models
3. Click file groups to expand and see individual files
4. Use the search box to filter models
5. Update or delete models as needed

## Configuration

### Changing the Models Directory

By default, models are stored in `/models/`. To change this:

1. **In `app.py
