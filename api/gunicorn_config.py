"""
Alternative API server using Gunicorn with Uvicorn workers.
This provides better performance for production environments.
"""
import os
import multiprocessing

# Gunicorn configuration for production
bind = f"127.0.0.1:{os.environ.get('API_PORT', 8000)}"
workers = min(2, multiprocessing.cpu_count())  # Conservative worker count
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 100

# Logging
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr
loglevel = "warning"
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s "%(a)s" %(D)s'

# Performance
preload_app = True
keepalive = 2
timeout = 30
graceful_timeout = 30

# Security
limit_request_line = 0
limit_request_fields = 100
limit_request_field_size = 8190

# Process naming
proc_name = "rebot-api"

# Application
wsgi_application = "api.external_api:app"
