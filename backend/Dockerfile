FROM python:3.12-slim

WORKDIR /workspace
COPY backend /workspace/backend
RUN pip install --no-cache-dir /workspace/backend

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
