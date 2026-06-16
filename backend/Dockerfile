FROM --platform=linux/amd64 python:3.14.0-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential dnsutils \
    && rm -rf /var/lib/apt/lists/*

COPY app /app/app
COPY pyproject.toml /app/pyproject.toml

RUN python -m pip install --upgrade pip \
    && python -m pip install .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
