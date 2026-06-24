FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt
# Embeddings are now served by the Fireworks API (see app/services/embeddings.py),
# so there is no local model to pre-download.
COPY . .
EXPOSE 8400
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8400", "--workers", "2"]
