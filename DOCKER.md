# Docker Deployment Guide

This guide explains how to run the Hugging Face Model Downloader using Docker.

## Quick Start

### Option 1: Docker Compose (Recommended)

1. **Clone or create the project structure:**
```bash
mkdir hf-model-downloader
cd hf-model-downloader
# Copy all the files here
```

2. **Create models directory:**
```bash
mkdir models
```

3. **Build and run with Docker Compose:**
```bash
docker-compose up --build
```

4. **Access the applications:**
   - Download Interface: http://localhost:5000
   - Model Manager: http://localhost:5001

### Option 2: Docker Build & Run

1. **Build the image:**
```bash
docker build -t hf-downloader .
```

2. **Run the container:**
```bash
docker run -d \
  --name hf-model-downloader \
  -p 5000:5000 \
  -p 5001:5001 \
  -v $(pwd)/models:/models \
  -v hf-cache:/home/appuser/.cache/huggingface \
  hf-downloader
```

## Configuration

### Environment Variables

You can set these environment variables in the `docker-compose.yml`:

```yaml
environment:
  - HF_HUB_ENABLE_HF_TRANSFER=1      # Enable fast transfers (default)
  - HF_TOKEN=your_hf_token_here      # Optional: for private models
  - FLASK_ENV=production             # Optional: set Flask environment
```

### Volumes

The setup uses two volumes:

1. **Models Volume**: `./models:/models`
   - Stores downloaded models on your host system
   - Persists even when container is removed

2. **Cache Volume**: `hf-cache:/home/appuser/.cache/huggingface`
   - Caches HuggingFace metadata and temporary files
   - Improves performance on subsequent downloads

### Custom Models Directory

To use a different models directory:

```yaml
volumes:
  - /your/custom/path:/models:rw
```

## Resource Management

### Resource Limits

The `docker-compose.yml` includes resource limits:

```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'      # Max 2 CPU cores
      memory: 4G       # Max 4GB RAM
    reservations:
      cpus: '0.5'      # Min 0.5 CPU cores
      memory: 512M     # Min 512MB RAM
```

Adjust these based on your system and download needs.

### Disk Space

- Large language models can be 10-100+ GB
- Ensure your host has sufficient disk space
- Monitor the `./models` directory size

## Production Deployment

### Security Considerations

1. **Change default ports** (optional):
```yaml
ports:
  - "8080:5000"  # Download interface
  - "8081:5001"  # Model manager
```

2. **Add authentication** (not included):
   - Consider adding nginx reverse proxy with auth
   - Or modify the Flask apps to include authentication

3. **Firewall rules**:
   - Only expose ports to trusted networks
   - Consider VPN access for remote usage

### Monitoring

1. **Health checks** are included:
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:5000/"]
  interval: 30s
  timeout: 10s
  retries: 3
```

2. **View logs**:
```bash
# All logs
docker-compose logs -f

# Specific service logs
docker-compose logs -f hf-downloader
```

3. **Container stats**:
```bash
docker stats hf-model-downloader
```

## Troubleshooting

### Common Issues

1. **Port already in use**:
```bash
# Check what's using the ports
sudo lsof -i :5000
sudo lsof -i :5001

# Kill processes or change ports in docker-compose.yml
```

2. **Permission denied on models directory**:
```bash
# Fix permissions
sudo chown -R 1000:1000 ./models
chmod 755 ./models
```

3. **Out of disk space**:
```bash
# Check disk usage
df -h
du -sh ./models

# Clean up old models if needed
```

4. **Container won't start**:
```bash
# Check logs
docker-compose logs hf-downloader

# Rebuild without cache
docker-compose build --no-cache
docker-compose up
```

### Development Mode

For development with hot reload:

1. **Create development docker-compose override**:
```yaml
# docker-compose.dev.yml
version: '3.8'
services:
  hf-downloader:
    volumes:
      - .:/app
    environment:
      - FLASK_ENV=development
    command: sh -c "python app.py & python model_manager.py & wait"
```

2. **Run in development mode**:
```bash
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up
```

## Backup and Recovery

### Backup Models

```bash
# Create backup
tar -czf models-backup-$(date +%Y%m%d).tar.gz ./models

# Or use rsync
rsync -av ./models/ /backup/location/models/
```

### Restore Models

```bash
# Extract backup
tar -xzf models-backup-20231201.tar.gz

# Or restore from rsync backup
rsync -av /backup/location/models/ ./models/
```

## Advanced Configuration

### Custom Dockerfile

If you need to modify the Dockerfile:

```dockerfile
# Add custom packages
RUN apt-get update && apt-get install -y \
    your-package \
    && rm -rf /var/lib/apt/lists/*

# Add custom Python packages
RUN pip install your-custom-package
```

### Multiple Environments

Use different compose files for different environments:

```bash
# Production
docker-compose -f docker-compose.prod.yml up

# Staging
docker-compose -f docker-compose.staging.yml up

# Development
docker-compose -f docker-compose.dev.yml up
```

## Scaling

### Multiple Instances

To run multiple instances (e.g., for load balancing):

```yaml
# docker-compose.scale.yml
version: '3.8'
services:
  hf-downloader:
    # ... existing config
    deploy:
      replicas: 3
```

Then:
```bash
docker-compose -f docker-compose.yml -f docker-compose.scale.yml up
```

Note: You'll need a load balancer (nginx, traefik) to distribute requests.

## Updates

### Update the Application

```bash
# Pull latest changes
git pull

# Rebuild and restart
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Update Dependencies

Modify `requirements.txt` and rebuild:

```bash
docker-compose build --no-cache
docker-compose up -d
```
