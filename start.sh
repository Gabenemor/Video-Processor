#!/bin/bash

# Start the Gunicorn web server in the background.
gunicorn --bind 0.0.0.0:8080 --timeout 300 src.main:app &

# Start the background worker.
python -m src.tasks
