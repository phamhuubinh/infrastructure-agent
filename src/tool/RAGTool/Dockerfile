FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/

WORKDIR /srv

# System deps needed by common optional providers (uncomment as needed):
# - libgl1, libglib2.0-0: OpenCV (PaddleOCR dependency)
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     libgl1 libglib2.0-0 \
#     && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock .
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app

RUN uv sync --frozen --no-dev \
    && useradd --create-home --shell /usr/sbin/nologin --uid 10001 orion \
    && mkdir -p /data \
    && chown -R orion:orion /srv /data

EXPOSE 8080

ENV HOME="/home/orion" PATH="/srv/.venv/bin:$PATH"

USER orion

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
