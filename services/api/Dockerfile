FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.9.5

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra genblaze --no-install-project

COPY app ./app

RUN useradd --create-home --uid 10001 recallcast \
    && chown -R recallcast:recallcast /app
USER recallcast

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
