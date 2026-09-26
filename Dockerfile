# BATMAN gateway container.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BATMAN_DB_PATH=/data/batman.db

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml README.md ./
COPY batman ./batman
RUN pip install --upgrade pip && pip install -e .

# Copy the rest of the project (training, attacks, evaluation, models).
COPY attacks ./attacks
COPY training ./training
COPY evaluation ./evaluation
COPY scripts ./scripts

# Build the demo model + detector at image build time so the container is
# self-contained and ready to demo.
RUN python -m training.prepare && python -m training.train

# Persist telemetry outside the image layer.
VOLUME ["/data"]
EXPOSE 8000

CMD ["uvicorn", "batman.gateway.app:app", "--host", "0.0.0.0", "--port", "8000"]
