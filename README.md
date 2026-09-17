# KROMA

Оперативный мониторинг лесных пожаров по спутниковым тепловым детекциям: приём и нормализация данных, объединение детекций в события, оценка приоритета, отображение на карте.

## Стек

- **Backend**: Python 3.12, FastAPI, Pydantic 2, pytest, ruff. Пакеты `backend`, `geo` (`kroma_geo`), `ml` (`kroma_ml`) — отдельные editable-пакеты одного репозитория.
- **Frontend**: Next.js 16 (App Router, Turbopack), React 19, TypeScript, MapLibre GL, Zustand, TanStack Query, vitest.
- **Данные**: PostGIS-образ поднят в `docker-compose.yml`, но backend его пока не использует — состояние живёт в памяти процесса (демо-репозиторий и live-кэш).
- **Инфраструктура**: Docker Compose (`db` + `backend` + `frontend`), GitHub Actions CI (ruff, pytest, eslint, tsc, next build).

## Структура репозитория

| Путь | Назначение |
| --- | --- |
| `backend/app/api/v1/` | REST-роуты `/api/v1/*` |
| `backend/app/models/` | Доменные Pydantic-модели (Incident, Observation, BurnScar, ForecastZone, RiskObject) |
| `backend/app/schemas/` | Схемы ответов API и GeoJSON-обёртки |
| `backend/app/services/` | Бизнес-логика: инциденты, аналитика, гари, слои карты, legacy FIRMS CSV-ingestion |
| `backend/app/repositories/` | Абстракция источника данных (`base.py`) + демо-реализация (`demo.py`) |
| `backend/app/demo/` | Генератор детерминированного демо-датасета (Красноярский край) |
| `backend/app/live/` | LIVE-контур: клиент NASA FIRMS, кластеризация, in-memory кэш, фоновое обновление |
| `frontend/src/app/` | Страницы: `/` (обзор+карта), `/events`, `/analytics` |
| `frontend/src/features/` | Карта, инциденты, таймлайн, слои, аналитика — по фиче |
| `frontend/src/lib/api/` | Типизированный клиент API + React Query хуки |
| `geo/src/kroma_geo/` | Геодезические утилиты (haversine, bearing, площадь полигона, point-in-ring) |
| `ml/src/kroma_ml/` | Пакет зарезервирован под ML-код, реализации пока нет |
| `research/`, `data/` | Гипотезы, воспроизводимые эксперименты, локальные датасеты (не в Git) |
| `scripts/ingestion/firms.py` | CLI для офлайн-нормализации CSV NASA FIRMS в JSONL (не связан с LIVE-режимом) |
| `docs/` | Архитектурные заметки и контракты данных |
| `tests/` | pytest по backend, geo, ml |

## Что реализовано

### Backend API (`/api/v1`)

| Метод | Путь | Описание |
| --- | --- | --- |
| GET | `/health` | Проверка живости процесса |
| GET | `/overview` | Сводка: регионы, счётчики инцидентов, источник данных |
| GET | `/timeline` | События хронологии за диапазон `from`/`to` |
| GET | `/observations/histogram` | Гистограмма наблюдений по бинам времени |
| GET | `/incidents` | Список инцидентов (фильтры: `status`, `priority_min`, `region`, `from`, `to`, `bbox`, `q`) |
| GET | `/incidents/{id}` | Карточка инцидента: confidence/threat/priority, evidence, риск-объекты, прогноз |
| GET | `/incidents/{id}/observations` | Наблюдения инцидента как GeoJSON |
| GET | `/incidents/{id}/timeline` | Снимки состояния и события инцидента во времени |
| GET | `/incidents/{id}/forecast` | Прогнозные зоны P50/P80/P95 (GeoJSON) |
| GET | `/burn-scars`, `/burn-scars/{id}` | Гари: список и деталка с зонами тяжести |
| GET | `/map/hotspots` | Сырые тепловые детекции (GeoJSON, поддержка bbox и агрегации по zoom) |
| GET | `/map/incidents`, `/map/perimeters`, `/map/burn-scars`, `/map/risk-objects`, `/map/thermal-sources`, `/map/wind`, `/map/clouds` | Слои карты как GeoJSON |
| GET | `/analytics/summary` | Динамика по неделям, разбивка по регионам, крупнейшие гари |
| GET | `/live/status` | Статус LIVE-источника: `configured`, `status` (`live`/`nrt`/`stale`/`offline`), время последней загрузки, интервал обновления |
| GET | `/live/hotspots` | Сырые детекции NASA FIRMS из кэша (GeoJSON, bbox) |
| GET | `/live/incidents` | Кластеризованные LIVE-инциденты (GeoJSON, bbox) |

Все геометрии — GeoJSON в WGS84 (EPSG:4326).

### Два режима данных

- **Сценарий (REPLAY)** — фиксированный детерминированный демо-датасет для Красноярского края (`backend/app/demo/`): инциденты, наблюдения, эволюция во времени, периметр, прогноз, гари. Не требует внешних сервисов, работает всегда.
- **Актуально (LIVE)** — реальные детекции NASA FIRMS (VIIRS SNPP/NOAA-20/NOAA-21). Backend раз в `KROMA_LIVE_REFRESH_SECONDS` (по умолчанию 600 c) сам опрашивает FIRMS Area API, кэширует детекции (`KROMA_LIVE_RETENTION_HOURS` часов) и строит из них простую spatial-temporal кластеризацию (`backend/app/live/clustering.py`) в инциденты. Без `NASA_FIRMS_API_KEY` режим корректно деградирует в статус `offline` — фронтенд отображает это как «источник не подключён», без падений.

Переключатель режима — в верхней панели фронтенда. Переключение не перезагружает страницу и не трогает состояние карты/темы.

### Frontend

- `/` — карта (MapLibre GL: векторная подложка/спутник/рельеф), очередь инцидентов, инспектор события, таймлайн с ретроспективой, панель слоёв, переключатель LIVE/REPLAY.
- `/events` — таблица инцидентов с сортировкой/фильтрами и split-view.
- `/analytics` — динамика по неделям, разбивка по регионам, сравнение гари «до/после» (Sentinel-2 cloudless + оверлей severity).
- Тёмная и светлая темы, переключение мгновенное, без перезагрузки.

## Локальный запуск

### Docker (рекомендуется)

```bash
cp .env.example .env
# задать POSTGRES_PASSWORD и синхронный DATABASE_URL в .env
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend: http://localhost:8000 (`/health`, `/docs`)

### Без Docker

Backend:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e geo -e backend
uvicorn app.main:app --app-dir backend --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Frontend читает `NEXT_PUBLIC_API_BASE_URL` (по умолчанию `http://localhost:8000`).

## Переменные окружения

Полный список — в `.env.example`. Ключевые:

| Переменная | Назначение |
| --- | --- |
| `NASA_FIRMS_API_KEY` | Ключ NASA FIRMS для LIVE-режима. Без него LIVE отдаёт статус `offline` |
| `KROMA_LIVE_SOURCES` | Источники VIIRS для опроса (по умолчанию SNPP + NOAA-20 + NOAA-21) |
| `KROMA_LIVE_AREA` | Область запроса к FIRMS (`world` или bbox) |
| `KROMA_LIVE_REFRESH_SECONDS` | Интервал фонового опроса FIRMS backend'ом |
| `KROMA_LIVE_RETENTION_HOURS` | Сколько часов хранить детекции в кэше |
| `KROMA_LIVE_CLUSTER_RADIUS_KM`, `KROMA_LIVE_CLUSTER_WINDOW_HOURS` | Параметры кластеризации LIVE-детекций в инциденты |
| `KROMA_CORS_ORIGINS` | Разрешённые origin для CORS |
| `KROMA_DEMO_ANCHOR` | Фиксирует «текущий момент» демо-датасета вместо `now()` (для воспроизводимой демонстрации) |
| `NEXT_PUBLIC_API_BASE_URL` | URL backend для фронтенда |
| `NEXT_PUBLIC_MAP_*` | Переопределение провайдеров тайлов (по умолчанию OpenFreeMap, Esri World Imagery, AWS Terrarium, EOX Sentinel-2 cloudless — все без ключей) |

## Тесты

```bash
# backend + geo + ml
.venv/bin/pytest

# ruff
.venv/bin/ruff check .

# frontend
cd frontend
npm run typecheck
npm run lint
npx vitest run
npm run build
```

Актуально: 32 backend-теста (API, FIRMS-парсинг и кластеризация, гео-утилиты, legacy CSV-ingestion), 19 frontend-тестов (форматирование, replay-логика, гео-хелперы).

## Чего пока нет

- Persistence: PostgreSQL/PostGIS поднят в compose, но не подключён — оба режима хранят состояние в памяти процесса backend (демо-датасет генерируется при старте, LIVE-кэш не переживает рестарт).
- ML-пакет (`ml/src/kroma_ml/`) пуст: оценка confidence/priority в LIVE-режиме — эвристика по числу и интенсивности детекций, не модель.
- LIVE-режим не считает периметр, прогноз (P50/P80/P95) и гари — только детекции и кластеры-инциденты; эти слои в UI скрыты, пока активен LIVE.
- Нет авторизации, ролей, персистентных пользовательских настроек.
- Мобильная адаптация не проработана (десктоп-first, от 1280px).

## Ветки

`main` — единственная и основная ветка, содержит весь текущий код.
