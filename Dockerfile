# ── Stage 1: builder — install dependencies ───────────────────────────────────
FROM public.ecr.aws/docker/library/python:3.11-slim AS builder

WORKDIR /app

# System deps for Pillow + asyncpg (needs gcc + libpq headers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libjpeg-dev \
    zlib1g-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: runtime — lean final image ──────────────────────────────────────
FROM public.ecr.aws/docker/library/python:3.11-slim AS runtime

WORKDIR /app

# Runtime libs: Pillow + libpq (asyncpg needs it at runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo \
    zlib1g \
    libfreetype6 \
    fonts-dejavu-core \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy source code
COPY . .

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Non-root user for security
RUN useradd -m botuser && chown -R botuser:botuser /app
USER botuser

CMD ["python", "bot.py"]
