#!/bin/bash

# Start the Gunicorn web server in the background.
# Increased timeout to handle long-running video processing tasks
gunicorn --bind 0.0.0.0:8080 --timeout 1800 --workers 2 --worker-class sync src.main:app &
WEB_PID=$!

# Start the background worker
python -m src.tasks &
WORKER_PID=$!

# Handle termination signals
function cleanup() {
    echo "Stopping services..."
    kill -TERM $WORKER_PID 2>/dev/null
    kill -TERM $WEB_PID 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

# Wait for both processes
wait
