FROM python:3.12-slim

ARG APP_REVISION=dev
LABEL org.opencontainers.image.revision="${APP_REVISION}"

WORKDIR /workspace
COPY geo /workspace/geo
COPY backend /workspace/backend
COPY ml /workspace/ml
COPY data/fire-aoi /workspace/data/fire-aoi
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -e /workspace/geo -e /workspace/ml -e /workspace/backend

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
