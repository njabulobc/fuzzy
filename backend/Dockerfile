# backend/Dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install Docker CLI so this container can run "docker <commands>"
RUN apt-get update && apt-get install -y docker.io && rm -rf /var/lib/apt/lists/*


# System deps for psycopg2 and reportlab fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# Note:
# - app.main:app is the FastAPI app
# - host 0.0.0.0 to accept external connections inside Docker
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
