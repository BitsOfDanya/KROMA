FROM python:3.12-slim

ARG APP_REVISION=dev
LABEL org.opencontainers.image.revision="${APP_REVISION}"

WORKDIR /workspace
COPY geo /workspace/geo
COPY backend /workspace/backend
RUN pip install --no-cache-dir /workspace/geo /workspace/backend

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
