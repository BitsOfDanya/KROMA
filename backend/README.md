# Backend

Минимальное FastAPI приложение с `GET /health`. Будущие домены: fires, hotspots, incidents, burned areas, satellites, observations, priorities. Подключение к базе и фоновые задачи ещё не реализованы.

Локально: `python3 -m venv .venv`, `source .venv/bin/activate`, `pip install -e backend`, `uvicorn app.main:app --app-dir backend --reload` из корня репозитория.
