FROM python:3.13-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH" HOST=0.0.0.0 PORT=8000
COPY pyproject.toml uv.lock ./
RUN useradd --system app

# The Portal, for self-hosting (compose.self-host.yml): `docker build --target portal .`
FROM base AS portal
RUN uv sync --frozen --no-default-groups --group portal
COPY portal ./portal
USER app
ENV DJANGO_SETTINGS_MODULE=portal.settings
EXPOSE 8000
CMD ["sh", "-c", "python -m django migrate && python -m django runserver 0.0.0.0:8000"]

# The core stays the last stage, so a plain `docker build` (Dokploy) still builds it.
FROM base AS core
RUN uv sync --frozen --no-default-groups
COPY voice ./voice
USER app
EXPOSE 8000
# GOOGLE_API_KEY and CORE_SECRET come from the environment (Dokploy); the app refuses to start without them. CORE_SECRET checks the Portal's call tickets, the only way into a call. SETTINGS_URL tells it where the Portal's settings are; without it the app starts and refuses every call.
CMD ["python", "-m", "voice.serve"]
