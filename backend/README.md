# Backend

FastAPI-приложение с API `/api/v1` (обзор, события, гари, карта, аналитика) и `GET /health`. Данные сейчас отдаёт демонстрационный репозиторий (`app/demo/`, `app/repositories/demo.py`) с реалистичным набором для Красноярского края; интерфейс репозитория (`app/repositories/base.py`) не завязан на источник, так что подключение PostgreSQL/PostGIS в будущем не потребует менять API. Домены: incidents, observations, burn_scars, forecast_zones, risk_objects, satellite_passes. Подключение к базе и фоновые задачи ещё не реализованы.

Локально: `python3 -m venv .venv`, `source .venv/bin/activate`, `pip install -e geo -e backend`, `uvicorn app.main:app --app-dir backend --reload` из корня репозитория. Backend импортирует геоутилиты из `kroma_geo`, поэтому пакет `geo` нужно установить вместе с `backend`.

Переменные окружения (см. `.env.example` в корне): `KROMA_DATA_SOURCE` (сейчас только `demo`), `KROMA_CORS_ORIGINS`, необязательный `KROMA_DEMO_ANCHOR` (ISO-время, фиксирует «текущий момент» демо-данных вместо `now()`).
