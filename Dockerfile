# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies required by yt-dlp (e.g., ffmpeg, aria2c)
# yt-dlp often needs ffmpeg for post-processing, and aria2c for faster downloads
RUN apt-get update && apt-get install -y \
    ffmpeg \
    aria2 \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Verify the content of requirements.txt
RUN cat requirements.txt

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code into the container
COPY src/ ./src/

# Copy the start script into the container
COPY start.sh .
RUN chmod +x start.sh

# Create the directory for video downloads
RUN mkdir -p /tmp/video_downloads

# Expose the port the app runs on
EXPOSE 8080

# Run the start script
CMD ["./start.sh"]
