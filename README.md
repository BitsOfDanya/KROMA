# KROMA

Система спутникового мониторинга лесных пожаров. Проект объединит тепловые детекции в события, оценит достоверность и приоритет реагирования, а затем покажет результаты на карте.

Сейчас репозиторий содержит основу для параллельной разработки и первый CSV ingestion NASA FIRMS VIIRS. Модели и карта пожаров ещё не реализованы.

## Архитектура

Внешние спутниковые, погодные и геопространственные данные → ingestion → нормализация → ML и геообработка → PostgreSQL/PostGIS → FastAPI → веб-карта. Подробности: [обзор архитектуры](docs/architecture/overview.md).

## Структура

| Каталог | Назначение |
| --- | --- |
| `frontend/` | Next.js и TypeScript, будущая карта |
| `backend/` | FastAPI, схемы наблюдений и FIRMS ingestion |
| `ml/` | Код моделей и оценок |
| `geo/` | Растровая и векторная обработка |
| `research/` | Исследования и notebooks |
| `data/` | Локальные данные, исключённые из Git |
| `docs/`, `scripts/`, `configs/`, `infra/`, `tests/` | Документация, утилиты, настройки, инфраструктура и тесты |

## Локальный запуск

1. Скопируйте `.env.example` в `.env` и задайте локальный пароль Postgres. Значение `DATABASE_URL` должно использовать тот же пароль.
2. Запустите `docker compose up --build`.
3. Проверьте `http://localhost:8000/health` и `http://localhost:3000`.

Для запуска без Docker см. [backend](backend/README.md) и [frontend](frontend/README.md). Ключ NASA FIRMS пока не используется приложением.

## Ветки

`main` — стабильная основа; `develop` — интеграция; `research-ml-danya` — исследования и ML; `backend`, `frontend`, `geo`, `deploy` — командные направления. Новую работу начинайте от `develop`, объединяйте через review.

## Стек и статус

Python 3.12+, FastAPI, pytest, Ruff; Next.js, TypeScript, ESLint; PostgreSQL/PostGIS и Docker Compose. Работают стартовые приложения, smoke tests и нормализация CSV FIRMS. Автоматическая загрузка, хранение в БД, алгоритмы и продуктовый интерфейс ещё не реализованы.
