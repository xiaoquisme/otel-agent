# syntax=docker/dockerfile:1

# ---- build stage: install the package ------------------------------------
# Dashboard assets ship committed in src/otel_agent/dashboard/frontend_dist,
# so no Node build is needed here (see hatch_build.py).
FROM python:3.12-slim AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /src
COPY pyproject.toml hatch_build.py README.md ./
COPY src ./src
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install .

# ---- runtime stage -------------------------------------------------------
FROM python:3.12-slim

LABEL org.opencontainers.image.title="otel-agent" \
      org.opencontainers.image.description="LLM API gateway with model-name-based provider routing and telemetry" \
      org.opencontainers.image.source="https://github.com/xiaoquisme/otel-agent"

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin otel \
    # Pre-create the state dir so a fresh named volume inherits otel ownership.
    && mkdir -p /home/otel/.otel-agent \
    && chown -R otel:otel /home/otel/.otel-agent

ENV HOME=/home/otel \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OTEL_AGENT_PORT=45638

COPY --from=build /opt/venv /opt/venv
COPY docker/entrypoint.sh /usr/local/bin/otel-agent-entrypoint
RUN chmod +x /usr/local/bin/otel-agent-entrypoint

USER otel
WORKDIR /home/otel

# State: ~/.otel-agent/ holds config.yaml, the telemetry DB, auth.json and logs.
VOLUME /home/otel/.otel-agent

EXPOSE 45638

# OTEL_AGENT_PORT must match the -p value when you override the listen port.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('OTEL_AGENT_PORT','45638')+'/health', timeout=3)"

ENTRYPOINT ["/usr/local/bin/otel-agent-entrypoint"]
CMD ["proxy", "--foreground"]
