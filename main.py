import os
import multiprocessing
import sys

# Set environment variables for Gunicorn
os.environ.setdefault("GUNICORN_TIMEOUT", "600")  # 10 minutes timeout
os.environ.setdefault("GUNICORN_WORKERS", "2")    # Use 2 workers for stability

# Add script to modify Gunicorn worker timeout from command line
if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "run_with_timeout":
    import gunicorn.app.base
    
    class CustomGunicornApp(gunicorn.app.base.BaseApplication):
        def __init__(self, app, options=None):
            self.options = options or {}
            self.application = app
            super().__init__()
            
        def load_config(self):
            config = {key: value for key, value in self.options.items()
                      if key in self.cfg.settings and value is not None}
            for key, value in config.items():
                self.cfg.set(key.lower(), value)
                
        def load(self):
            return self.application
    
    # Import app after env vars are set
    from app import app
    
    # Define Gunicorn options with extended timeout
    options = {
        'bind': '0.0.0.0:5000',
        'workers': 2,
        'timeout': 300,  # 5 minute timeout
        'reload': True,
        'reuse_port': True,
    }
    
    # Run with custom settings
    CustomGunicornApp(app, options).run()
else:
    # Standard import for regular Gunicorn use
    from app import app  # noqa: F401
