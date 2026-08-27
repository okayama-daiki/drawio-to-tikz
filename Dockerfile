# syntax=docker/dockerfile:1.26.0@sha256:ecfaec9ed6d810b56388c508f4121597bfbba70d41a6dfeee4d8cad5f295fc32

ARG DRAWIO_VERSION=31.3.2
ARG DRAWIO_SHA256=725453f32ef7f2f63f8b50b374857a5c312e2aaabcf221cb0600332741ae1094
ARG UV_VERSION=0.12.6

FROM ghcr.io/astral-sh/uv:${UV_VERSION}@sha256:88bc6eb1ccd4b82efd0e1b530caffabddf50dc2bf612e66c14ea25b8ee8a4d3d AS uv

FROM python:3.14-slim@sha256:83ff1d245a3d57d04152252d3ef9cb361494d0b3395abd65a5ebe91c401c8e83 AS builder

COPY --from=uv /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml README.md LICENSE uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY stubs ./stubs

RUN uv sync --frozen --no-dev --no-editable

FROM python:3.14-slim@sha256:83ff1d245a3d57d04152252d3ef9cb361494d0b3395abd65a5ebe91c401c8e83 AS drawio-package

ARG DRAWIO_VERSION
ARG DRAWIO_SHA256

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -fsSL \
        "https://github.com/jgraph/drawio-desktop/releases/download/v${DRAWIO_VERSION}/drawio-amd64-${DRAWIO_VERSION}.deb" \
        -o /tmp/drawio.deb \
    && echo "${DRAWIO_SHA256}  /tmp/drawio.deb" | sha256sum --check --strict \
    && rm -rf /var/lib/apt/lists/*

FROM python:3.14-slim@sha256:83ff1d245a3d57d04152252d3ef9cb361494d0b3395abd65a5ebe91c401c8e83 AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DRAWIO_BIN=drawio-headless \
    HOME=/home/appuser \
    HOST=0.0.0.0 \
    PORT=8000 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=drawio-package /tmp/drawio.deb /tmp/drawio.deb

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        libasound2t64 \
        libcairo2 \
        libgirepository-1.0-1 \
        libgirepository-2.0-0 \
        libglib2.0-0t64 \
        libjpeg62-turbo \
        libxml2 \
        libxslt1.1 \
        xauth \
        xvfb \
        /tmp/drawio.deb \
    && rm -rf /var/lib/apt/lists/* /tmp/drawio.deb \
    && printf '%s\n' \
        '#!/bin/sh' \
        'exec xvfb-run -a /usr/bin/drawio --no-sandbox "$@"' \
        > /usr/local/bin/drawio-headless \
    && chmod +x /usr/local/bin/drawio-headless \
    && groupadd --system appuser \
    && useradd --system --gid appuser --create-home --home-dir /home/appuser --shell /usr/sbin/nologin appuser

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv

USER appuser

EXPOSE 8000

CMD ["drawio2tikz-web"]
