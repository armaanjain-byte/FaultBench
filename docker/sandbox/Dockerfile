# FaultBench sandbox image
#
# A minimal Python 3.11 environment used to run benchmark tasks in
# isolation.  The agent (OpenHands) runs separately and communicates
# with this container via the Docker SDK.
#
# Build:
#   docker build -t faultbench-sandbox:latest -f docker/sandbox/Dockerfile .

FROM python:3.11-slim

# System dependencies needed by benchmark tasks
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create workspace directory
WORKDIR /workspace

# Default command — keeps the container alive for exec_run calls
CMD ["sleep", "infinity"]
