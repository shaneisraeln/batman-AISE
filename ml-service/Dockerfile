# Protected ML inference service.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /svc

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app

# Train the model at build time so the image is self-contained.
RUN python -m app.train

EXPOSE 9000
# Bind to $PORT when a PaaS (Render) injects it; default 9000 locally.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-9000}"]
