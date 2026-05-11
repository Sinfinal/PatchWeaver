# syntax=docker/dockerfile:1.7

ARG PYTHON_BASE_IMAGE=python:3.11-slim
FROM ${PYTHON_BASE_IMAGE} AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    PATCHWEAVER_CONTAINER=1 \
    PATCHWEAVER_PROJECT_ROOT=/app \
    PATCHWEAVER_API_HOST=0.0.0.0 \
    PATCHWEAVER_API_PORT=18084

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      ca-certificates \
      binutils \
      bc \
      bison \
      build-essential \
      curl \
      file \
      flex \
      gawk \
      git \
      kmod \
      libelf-dev \
      libssl-dev \
      patch \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY patchweaver ./patchweaver
COPY config ./config
COPY prompts ./prompts
COPY recipes ./recipes
COPY rules ./rules
COPY skills ./skills
COPY evaluations ./evaluations
COPY scripts ./scripts
COPY docs ./docs

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir .

RUN mkdir -p /app/data /app/workspaces /app/docs/submission

EXPOSE 18084

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:18084/healthz', timeout=3).read()"

CMD ["patchweaver", "serve-api", "--host", "0.0.0.0", "--port", "18084", "--foreground"]
