# Google Cloud Run Deployment Guide

This guide provides instructions for deploying the video processing application to Google Cloud Run, a fully managed compute platform for deploying containerized applications. It covers both manual deployment and automated deployment using Google Cloud Build.

## 1. Prerequisites

Before you begin, ensure you have the following:

- **Google Cloud Project**: A Google Cloud project with billing enabled.
- **Google Cloud SDK**: Installed and configured on your local machine. Ensure you are authenticated (`gcloud auth login`) and have set your project (`gcloud config set project YOUR_PROJECT_ID`).
- **Docker**: Installed on your local machine (optional, for local testing).
- **Supabase Project**: Configured with a `processed-videos` bucket and appropriate RLS policies as described in `UPDATED_CONFIGURATION.md`.
- **Webshare.io Account**: With residential proxy credentials.

## 2. Project Structure for Deployment

Ensure your project directory (`video_processor`) contains the following files:

```
video_processor/
├── src/                  # Your application source code
│   ├── config.py
│   ├── main.py
│   ├── routes/
│   │   └── video.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── factory.py
│   │   └── supabase_storage.py
│   └── video_downloader.py
├── .env.example          # Template for environment variables
├── requirements.txt      # Python dependencies
├── Dockerfile            # Docker image definition
├── cloudbuild.yaml       # Google Cloud Build configuration
├── UPDATED_CONFIGURATION.md # Detailed configuration guide
├── QUICK_START.md        # Quick start guide
├── README.md             # Project README
├── DEPLOYMENT.md         # General deployment guide
└── test_proxy_integration.py # Test script
```

## 3. Dockerfile Explained

The `Dockerfile` defines how your application is packaged into a Docker image. It includes necessary system dependencies (like `ffmpeg` for `yt-dlp`), Python dependencies, and your application code.

```dockerfile
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

# Copy the rest of the application code into the container
COPY src/ ./src/
COPY .env.example ./.env.example
COPY test_proxy_integration.py ./test_proxy_integration.py
COPY UPDATED_CONFIGURATION.md ./UPDATED_CONFIGURATION.md
COPY QUICK_START.md ./QUICK_START.md
COPY README.md ./README.md
COPY DEPLOYMENT.md ./DEPLOYMENT.md

# Create the directory for video downloads
RUN mkdir -p /tmp/video_downloads

# Expose the port the app runs on
EXPOSE 5000

# Run the application
# Cloud Run automatically sets the PORT environment variable.
# We use 0.0.0.0 to listen on all available network interfaces.
# The Flask app is configured to read FLASK_PORT from environment variables.
CMD ["python", "src/main.py"]
```

**Key points:**
- `FROM python:3.11-slim`: Uses a lightweight Python 3.11 image.
- `RUN apt-get install -y ffmpeg`: Installs `ffmpeg`, which `yt-dlp` often relies on for various video processing tasks.
- `COPY requirements.txt .` and `RUN pip install -r requirements.txt`: Installs Python dependencies.
- `COPY src/ ./src/`: Copies your application code.
- `EXPOSE 5000`: Informs Docker that the container listens on port 5000. Cloud Run will automatically map this.
- `CMD ["python", "src/main.py"]`: Specifies the command to run your Flask application when the container starts.

## 4. Manual Deployment to Cloud Run

This method involves building the Docker image locally and then deploying it to Cloud Run.

### 4.1. Build Docker Image Locally

Navigate to your `video_processor` directory and build the Docker image:

```bash
cd video_processor
docker build -t gcr.io/YOUR_PROJECT_ID/video-processor:latest .
```

Replace `YOUR_PROJECT_ID` with your actual Google Cloud Project ID.

### 4.2. Push Docker Image to Google Container Registry (GCR)

Before pushing, ensure Docker is configured to authenticate with GCR:

```bash
gcloud auth configure-docker
```

Then, push the image:

```bash
docker push gcr.io/YOUR_PROJECT_ID/video-processor:latest
```

### 4.3. Deploy to Cloud Run

```bash
gcloud run deploy video-processor \
  --image gcr.io/YOUR_PROJECT_ID/video-processor:latest \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --port 5000 \
  --set-env-vars \
  FLASK_SECRET_KEY="YOUR_FLASK_SECRET_KEY" \
  SUPABASE_URL="YOUR_SUPABASE_URL" \
  SUPABASE_SERVICE_ROLE_KEY="YOUR_SUPABASE_SERVICE_ROLE_KEY" \
  SUPABASE_BUCKET_NAME="processed-videos" \
  WEBSHARE_USERNAME="YOUR_WEBSHARE_USERNAME" \
  WEBSHARE_PASSWORD="YOUR_WEBSHARE_PASSWORD" \
  WEBSHARE_ENDPOINT="rotating-residential.webshare.io:9000" \
  USE_PROXY_FOR_INFO_EXTRACTION="true" \
  VIDEO_DOWNLOAD_DIR="/tmp/video_downloads" \
  MAX_FILE_SIZE="1073741824" \
  ALLOWED_FORMATS="mp4,avi,mov,wmv,flv,webm,mkv" \
  VIDEO_QUALITY="best[height<=720]/best" \
  LOG_LEVEL="INFO" \
  LOG_FILE="/dev/stderr"
```

**Important Considerations:**
- **`--region`**: Choose a region close to your users or other Google Cloud resources.
- **`--allow-unauthenticated`**: Allows public access to your service. For private services, use `--no-allow-unauthenticated` and configure IAM permissions.
- **`--port 5000`**: Matches the `EXPOSE` port in your `Dockerfile` and the `FLASK_PORT` in your application configuration.
- **`--set-env-vars`**: This is where you pass your environment variables. **For sensitive data like API keys and passwords, it is highly recommended to use Google Cloud Secret Manager instead of setting them directly here.** See Section 6 for more details.

## 5. Automated Deployment with Google Cloud Build

Google Cloud Build allows you to automate the build and deployment process whenever you push changes to your Git repository (e.g., GitHub, GitLab, Bitbucket).

### 5.1. `cloudbuild.yaml` Explained

The `cloudbuild.yaml` file defines the steps Cloud Build will execute. It builds the Docker image, pushes it to GCR, and then deploys it to Cloud Run.

```yaml
# Google Cloud Build configuration for deploying to Cloud Run

steps:
# Step 1: Build the Docker image
# This step uses the 'cloud-build-local' builder to build the Docker image
# from the Dockerfile in the current directory.
# The image is tagged with the commit SHA and pushed to Google Container Registry (GCR).
- name: 'gcr.io/cloud-builders/docker'
  args: ['build', '-t', 'gcr.io/$PROJECT_ID/video-processor:$COMMIT_SHA', '.']

# Step 2: Push the Docker image to Google Container Registry
# This step pushes the built Docker image to GCR, making it available for Cloud Run.
- name: 'gcr.io/cloud-builders/docker'
  args: ['push', 'gcr.io/$PROJECT_ID/video-processor:$COMMIT_SHA']

# Step 3: Deploy the image to Cloud Run
# This step deploys the Docker image to Cloud Run. 
# It specifies the service name, region, and sets environment variables.
# IMPORTANT: Environment variables should be managed securely in Cloud Run secrets or directly in the Cloud Run service settings.
# For demonstration, we are listing them here. In a real production scenario, consider Cloud Secret Manager.
- name: 'gcr.io/google.com/cloudsdk/cloud-sdk'
  args: [
      'gcloud',
      'run',
      'deploy',
      'video-processor',
      '--image',
      'gcr.io/$PROJECT_ID/video-processor:$COMMIT_SHA',
      '--region',
      'us-central1', # Specify your desired region here
      '--platform',
      'managed',
      '--allow-unauthenticated', # Change to '--no-allow-unauthenticated' for private service
      '--port',
      '5000',
      '--set-env-vars',
      'FLASK_SECRET_KEY=${_FLASK_SECRET_KEY}',
      'SUPABASE_URL=${_SUPABASE_URL}',
      'SUPABASE_SERVICE_ROLE_KEY=${_SUPABASE_SERVICE_ROLE_KEY}',
      'SUPABASE_BUCKET_NAME=${_SUPABASE_BUCKET_NAME}',
      'WEBSHARE_USERNAME=${_WEBSHARE_USERNAME}',
      'WEBSHARE_PASSWORD=${_WEBSHARE_PASSWORD}',
      'WEBSHARE_ENDPOINT=${_WEBSHARE_ENDPOINT}',
      'USE_PROXY_FOR_INFO_EXTRACTION=${_USE_PROXY_FOR_INFO_EXTRACTION}',
      'VIDEO_DOWNLOAD_DIR=/tmp/video_downloads',
      'MAX_FILE_SIZE=1073741824',
      'ALLOWED_FORMATS=mp4,avi,mov,wmv,flv,webm,mkv',
      'VIDEO_QUALITY=best[height<=720]/best',
      'LOG_LEVEL=INFO',
      'LOG_FILE=/dev/stderr' # Log to stderr for Cloud Run logging
  ]

# Define substitutions for sensitive environment variables
# These values should be passed as build arguments or retrieved from Secret Manager
# For Cloud Build, it's recommended to use Secret Manager for sensitive data.
# Example: https://cloud.google.com/build/docs/securing-builds/use-secrets
substitutions:
  _FLASK_SECRET_KEY: "YOUR_FLASK_SECRET_KEY"
  _SUPABASE_URL: "YOUR_SUPABASE_URL"
  _SUPABASE_SERVICE_ROLE_KEY: "YOUR_SUPABASE_SERVICE_ROLE_KEY"
  _SUPABASE_BUCKET_NAME: "processed-videos"
  _WEBSHARE_USERNAME: "YOUR_WEBSHARE_USERNAME"
  _WEBSHARE_PASSWORD: "YOUR_WEBSHARE_PASSWORD"
  _WEBSHARE_ENDPOINT: "rotating-residential.webshare.io:9000"
  _USE_PROXY_FOR_INFO_EXTRACTION: "true"

# Output the image name for traceability
images:
- 'gcr.io/$PROJECT_ID/video-processor:$COMMIT_SHA'

# Note on environment variables:
# For production, it is highly recommended to use Google Cloud Secret Manager
# to store sensitive environment variables (like API keys and passwords).
# You can then grant Cloud Build access to these secrets and reference them in your cloudbuild.yaml.
# Example of using Secret Manager in Cloud Build:
# https://cloud.google.com/build/docs/securing-builds/use-secrets
```

**Key points:**
- `steps`: Defines the sequence of operations.
- `name: 'gcr.io/cloud-builders/docker'`: Uses the official Docker builder image.
- `gcr.io/$PROJECT_ID/video-processor:$COMMIT_SHA`: Tags the Docker image with your project ID and the commit SHA for versioning.
- `gcr.io/google.com/cloudsdk/cloud-sdk`: Uses the Google Cloud SDK image for `gcloud` commands.
- `substitutions`: Allows you to define variables that can be replaced at build time. **For sensitive information, it is strongly recommended to use Google Cloud Secret Manager instead of hardcoding values here.**

### 5.2. Set up Cloud Build Trigger

1. **Enable Cloud Build API**: Ensure the Cloud Build API is enabled in your Google Cloud project.
2. **Connect Repository**: In the Google Cloud Console, navigate to **Cloud Build > Triggers**. Click **Connect Repository** and follow the instructions to connect your Git repository (e.g., GitHub).
3. **Create Trigger**: Click **Create Trigger** and configure it:
    - **Name**: A descriptive name for your trigger (e.g., `deploy-video-processor`).
    - **Region**: Select the region for your trigger.
    - **Event**: Choose `Push to a branch`.
    - **Source**: Select your connected repository and the target branch (e.g., `main`).
    - **Configuration**: Select `Cloud Build configuration file (yaml or json)` and specify `cloudbuild.yaml`.
    - **Substitutions**: For sensitive variables, you can define them here or, preferably, use Secret Manager (see Section 6).

Once configured, every push to the specified branch will automatically trigger a Cloud Build job, which will build your Docker image and deploy it to Cloud Run.

## 6. Managing Sensitive Environment Variables (Best Practice)

**NEVER hardcode sensitive information (API keys, passwords) directly in your `Dockerfile` or `cloudbuild.yaml` for production environments.** Google Cloud provides **Secret Manager** for securely storing and accessing these values.

### 6.1. Store Secrets in Secret Manager

```bash
gcloud secrets create FLASK_SECRET_KEY --data-file=<(echo 


YOUR_FLASK_SECRET_KEY") --project=YOUR_PROJECT_ID
gcloud secrets create SUPABASE_URL --data-file=<(echo "YOUR_SUPABASE_URL") --project=YOUR_PROJECT_ID
gcloud secrets create SUPABASE_SERVICE_ROLE_KEY --data-file=<(echo "YOUR_SUPABASE_SERVICE_ROLE_KEY") --project=YOUR_PROJECT_ID
gcloud secrets create WEBSHARE_USERNAME --data-file=<(echo "YOUR_WEBSHARE_USERNAME") --project=YOUR_PROJECT_ID
gcloud secrets create WEBSHARE_PASSWORD --data-file=<(echo "YOUR_WEBSHARE_PASSWORD") --project=YOUR_PROJECT_ID

# For other variables that might change, like bucket name, you can also store them as secrets
gcloud secrets create SUPABASE_BUCKET_NAME --data-file=<(echo "processed-videos") --project=YOUR_PROJECT_ID
gcloud secrets create WEBSHARE_ENDPOINT --data-file=<(echo "rotating-residential.webshare.io:9000") --project=YOUR_PROJECT_ID
gcloud secrets create USE_PROXY_FOR_INFO_EXTRACTION --data-file=<(echo "true") --project=YOUR_PROJECT_ID
```

Replace `YOUR_PROJECT_ID`, `YOUR_FLASK_SECRET_KEY`, `YOUR_SUPABASE_URL`, `YOUR_SUPABASE_SERVICE_ROLE_KEY`, `YOUR_WEBSHARE_USERNAME`, and `YOUR_WEBSHARE_PASSWORD` with your actual values.

### 6.2. Grant Cloud Build Access to Secrets

Grant the Cloud Build service account permission to access your secrets:

```bash
PROJECT_NUMBER=$(gcloud projects describe YOUR_PROJECT_ID --format=\


value(projectNumber))

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member=serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com \
    --role=roles/secretmanager.secretAccessor
```

### 6.3. Reference Secrets in `cloudbuild.yaml`

Modify your `cloudbuild.yaml` to fetch secrets from Secret Manager. This involves two main changes:

1.  **Add `availableSecrets`**: Define the secrets that Cloud Build should make available.
2.  **Update `deploy` step**: Reference the secrets using `secretEnv` and `entrypoint`.

Here's how the relevant part of your `cloudbuild.yaml` would look:

```yaml
# ... (previous steps)

# Step 3: Deploy the image to Cloud Run
- name: 'gcr.io/google.com/cloudsdk/cloud-sdk'
  entrypoint: gcloud
  args: [
      'run',
      'deploy',
      'video-processor',
      '--image',
      'gcr.io/$PROJECT_ID/video-processor:$COMMIT_SHA',
      '--region',
      'us-central1', # Specify your desired region here
      '--platform',
      'managed',
      '--allow-unauthenticated', # Change to '--no-allow-unauthenticated' for private service
      '--port',
      '5000',
      '--set-env-vars',
      'VIDEO_DOWNLOAD_DIR=/tmp/video_downloads',
      'MAX_FILE_SIZE=1073741824',
      'ALLOWED_FORMATS=mp4,avi,mov,wmv,flv,webm,mkv',
      'VIDEO_QUALITY=best[height<=720]/best',
      'LOG_LEVEL=INFO',
      'LOG_FILE=/dev/stderr' # Log to stderr for Cloud Run logging
  ]
  secretEnv: ["FLASK_SECRET_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_BUCKET_NAME", "WEBSHARE_USERNAME", "WEBSHARE_PASSWORD", "WEBSHARE_ENDPOINT", "USE_PROXY_FOR_INFO_EXTRACTION"]

availableSecrets:
- secretManager: {
    env: 'FLASK_SECRET_KEY',
    version: 'projects/YOUR_PROJECT_ID/secrets/FLASK_SECRET_KEY/versions/latest'
  }
- secretManager: {
    env: 'SUPABASE_URL',
    version: 'projects/YOUR_PROJECT_ID/secrets/SUPABASE_URL/versions/latest'
  }
- secretManager: {
    env: 'SUPABASE_SERVICE_ROLE_KEY',
    version: 'projects/YOUR_PROJECT_ID/secrets/SUPABASE_SERVICE_ROLE_KEY/versions/latest'
  }
- secretManager: {
    env: 'SUPABASE_BUCKET_NAME',
    version: 'projects/YOUR_PROJECT_ID/secrets/SUPABASE_BUCKET_NAME/versions/latest'
  }
- secretManager: {
    env: 'WEBSHARE_USERNAME',
    version: 'projects/YOUR_PROJECT_ID/secrets/WEBSHARE_USERNAME/versions/latest'
  }
- secretManager: {
    env: 'WEBSHARE_PASSWORD',
    version: 'projects/YOUR_PROJECT_ID/secrets/WEBSHARE_PASSWORD/versions/latest'
  }
- secretManager: {
    env: 'WEBSHARE_ENDPOINT',
    version: 'projects/YOUR_PROJECT_ID/secrets/WEBSHARE_ENDPOINT/versions/latest'
  }
- secretManager: {
    env: 'USE_PROXY_FOR_INFO_EXTRACTION',
    version: 'projects/YOUR_PROJECT_ID/secrets/USE_PROXY_FOR_INFO_EXTRACTION/versions/latest'
  }

# ... (images section)

# Note: The substitutions section is no longer needed for these variables if using Secret Manager.
# You can remove it or keep it for other non-sensitive build-time variables.
```

**Important:** Replace `YOUR_PROJECT_ID` with your actual Google Cloud Project ID in the `version` paths.

By following these steps, you can securely deploy your video processing application to Google Cloud Run, leveraging Docker for containerization and Google Cloud Build for automated CI/CD, while keeping your sensitive credentials safe with Secret Manager.

