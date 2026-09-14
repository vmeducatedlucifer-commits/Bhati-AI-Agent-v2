# Execution sandbox image used when SANDBOX_MODE=docker.
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl wget ca-certificates build-essential ripgrep jq unzip zip \
    nodejs npm sqlite3 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip && pip install \
    requests httpx pandas numpy matplotlib beautifulsoup4 lxml pytest rich

RUN useradd -ms /bin/bash agent
WORKDIR /work
USER agent

CMD ["bash"]
