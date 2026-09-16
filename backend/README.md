# Backend

Минимальное FastAPI приложение с `GET /health`. Будущие домены: fires, hotspots, incidents, burned areas, satellites, observations, priorities. Подключение к базе и фоновые задачи ещё не реализованы.

Локально: `python3 -m venv .venv`, `source .venv/bin/activate`, `pip install -e backend`, `uvicorn app.main:app --app-dir backend --reload` из корня репозитория.

Первый ingestion: `python scripts/ingestion/firms.py --source VIIRS_SNPP_NRT --input path/to/firms.csv --output data/interim/firms-observations.jsonl`. Для загрузки из NASA FIRMS установите `NASA_FIRMS_API_KEY` в окружении и замените `--input` на `--bbox WEST SOUTH EAST NORTH --date YYYY-MM-DD`. Скрипт сохраняет исходный CSV в `data/raw/firms/`, нормализованный JSONL и manifest с хешем входа. Данные в Git не добавляются. Формат описан в [контрактах](../docs/data/contracts.md).
