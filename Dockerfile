FROM python:3.11-slim

WORKDIR /app

# Install git, curl (health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Docker CLI (for sandbox verifier — Docker-in-Docker via socket mount)
COPY --from=docker:27-cli /usr/local/bin/docker /usr/local/bin/docker

# Copy requirements first for Docker layer caching
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application code
COPY . .

# Create workspace directories
RUN mkdir -p /tmp/neverdown-clones \
    /tmp/neverdown-sanitized \
    /tmp/neverdown-results \
    /tmp/neverdown-workspaces

# NOTE: Running as root for Docker socket access (hackathon dev mode).
# In production, use an entrypoint script to fix socket group ownership.

# Expose port
EXPOSE 8000

# Pull sandbox image at build time (optional, speeds up first run)
# RUN docker pull python:3.11-slim || true

# Start the application
RUN pip install gunicorn uvicorn
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port 8000"]
