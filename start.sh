#!/bin/bash

# Start the Gunicorn web server in the background.
# Increased timeout to handle long-running video processing tasks
gunicorn --bind 0.0.0.0:8080 --timeout 1800 --workers 2 --worker-class sync src.main:app &

# Start the background worker.
python -m src.tasks
