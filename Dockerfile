# The core (the call app). The Portal has its own image: Dockerfile.portal.
FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f AS core
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH" HOST=0.0.0.0 PORT=8000
COPY pyproject.toml uv.lock ./
RUN useradd --system app
RUN uv sync --frozen --no-default-groups
COPY voice ./voice
USER app
EXPOSE 8000
# GOOGLE_API_KEY and CORE_SECRET come from the environment (Dokploy); the app refuses to start without them. CORE_SECRET checks the Portal's call tickets, the only way into a call. SETTINGS_URL tells it where the Portal's settings are; without it the app starts and refuses every call.
# Healthy once the server accepts connections (TCP only: every page here asks for a call ticket). With the update order start-first, Dokploy keeps the old copy until the new one passes this (VOI-121).
HEALTHCHECK --interval=5s --timeout=3s --start-period=20s --retries=3 CMD ["python", "-c", "import socket; socket.create_connection(('127.0.0.1', 8000), 2)"]
# A stop (SIGTERM, a deploy) waits for open calls to end (voice.serve.DrainingServer), at most DRAIN_CEILING_S (MAX_CALL_SECS + 30 = 630 s,
# then it logs the Businesses still open and cuts them): the stop wait on Dokploy (Swarm settings) must be longer, 660 s.
CMD ["python", "-m", "voice.serve"]
