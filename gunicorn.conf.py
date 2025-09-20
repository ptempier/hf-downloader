# Gunicorn configuration for HF Downloader
import os

# Server socket
bind = "0.0.0.0:5000"
backlog = 2048

# Worker processes
workers = 1  # Single worker to avoid download conflicts
worker_class = "gthread"  # Use threading worker
threads = 8  # Allow 8 concurrent requests
worker_connections = 1000
max_requests = 0  # No automatic worker restart
max_requests_jitter = 0

# Timeouts (important for long downloads)
timeout = 300  # 5 minutes for long-running requests
keepalive = 5  # Keep connections alive
graceful_timeout = 30

# Logging
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "hf-downloader"

# Server mechanics
preload_app = True  # Load app before forking workers
daemon = False      # Don't daemonize
pidfile = None
user = None
group = None
tmp_upload_dir = None

# SSL (if needed)
keyfile = None
certfile = None

# Environment
raw_env = [
    'HF_HUB_ENABLE_HF_TRANSFER=1',
]

def when_ready(server):
    """Called just after the server is started."""
    server.log.info("🚀 HF Downloader server is ready to accept connections")
    
    # Ensure directories exist
    os.makedirs("/models", exist_ok=True)
    os.makedirs("/models/.cache", exist_ok=True)

def worker_int(worker):
    """Called just after a worker exited on SIGINT or SIGQUIT."""
    worker.log.info("🔄 Worker received INT or QUIT signal")

def on_exit(server):
    """Called just before exiting."""
    server.log.info("🛑 HF Downloader server is shutting down")