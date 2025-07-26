# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies required by yt-dlp (e.g., ffmpeg)
# yt-dlp often needs ffmpeg for post-processing, even if not explicitly used in Python code
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code into the container
COPY src/ ./src/

# Create the directory for video downloads
RUN mkdir -p /tmp/video_downloads

# Expose the port the app runs on
EXPOSE 5000

# Run the application
# Cloud Run automatically sets the PORT environment variable.
# We use 0.0.0.0 to listen on all available network interfaces.
# The Flask app is configured to read FLASK_PORT from environment variables.
CMD ["python", "src/main.py"]
