# Gunicorn configuration file
import multiprocessing

# Bind to 0.0.0.0:5000
bind = "0.0.0.0:5000"

# Use 2 worker processes
workers = 2

# Set timeout to 5 minutes (300 seconds) to handle large files and OpenAI requests
timeout = 300  

# Reload code when changed
reload = True

# Enable reuse port for faster reload
reuse_port = True

# Log level
loglevel = "info"

# Maximum request size (30MB)
limit_request_line = 8190
limit_request_field_size = 0