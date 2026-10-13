FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH" HOST=0.0.0.0 PORT=8000
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY voice ./voice
RUN useradd --system app
USER app
EXPOSE 8000
# GOOGLE_API_KEY and VOICE_PASSWORD come from the environment (Dokploy); the app refuses to start without them.
CMD ["python", "-m", "voice.serve"]
