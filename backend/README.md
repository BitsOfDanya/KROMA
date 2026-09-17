# Backend

FastAPI-приложение с API `/api/v1` (обзор, события, гари, слои карты, аналитика, LIVE-статус) и `GET /health`. Полный список эндпоинтов — в корневом [README](../README.md).

Источники данных:

- **REPLAY** — `app/demo/` + `app/repositories/demo.py`, детерминированный демо-датасет для Красноярского края. Интерфейс `app/repositories/base.py` не завязан на источник, поэтому подключение PostgreSQL/PostGIS в будущем не потребует менять API.
- **LIVE** — `app/live/`, опрос NASA FIRMS (`firms_client.py`), спатио-темпоральная кластеризация (`clustering.py`) и in-memory кэш с фоновым обновлением (`store.py`), запускается через FastAPI lifespan в `main.py`.

Локально:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e geo -e backend
uvicorn app.main:app --app-dir backend --reload
```

Backend импортирует геоутилиты из `kroma_geo`, поэтому пакет `geo` нужно устанавливать вместе с `backend`.

Переменные окружения — в `.env.example` в корне репозитория (`KROMA_DATA_SOURCE`, `KROMA_CORS_ORIGINS`, `KROMA_DEMO_ANCHOR`, `NASA_FIRMS_API_KEY`, `KROMA_LIVE_*`).

Отдельно, вне LIVE-контура: `app/services/firms.py` + `scripts/ingestion/firms.py` — CLI для офлайн-нормализации выгруженного CSV NASA FIRMS в JSONL по контракту `app/schemas/observations.py`. Используется для подготовки исследовательских выборок, к рантайму API не относится.
