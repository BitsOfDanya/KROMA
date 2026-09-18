# KROMA

Оперативный мониторинг лесных пожаров по спутниковым тепловым детекциям и воспроизводимый пространственно-временной анализ подготовленных результатов: карта, площади трёх классов поражения и экспорт GeoJSON/CSV/JSON.

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
| GET | `/analysis/datasets` | Каталог проверенных immutable-наборов, охват, период и пример запроса |
| GET | `/analysis` | Единый bbox+период: термоточки, обрезанные зоны, площади, coverage и provenance |
| GET | `/analysis/export/contours` | Контуры того же `result_id` в GeoJSON |
| GET | `/analysis/export/report` | Справка того же `result_id` в CSV или JSON |
| GET | `/analysis/readiness` | Готовность manifest и артефактов; отличается от живости `/health` |
| GET | `/live/status` | Статус LIVE-источника: `configured`, `status` (`live`/`nrt`/`stale`/`offline`), время последней загрузки, интервал обновления |
| GET | `/live/hotspots` | Сырые детекции NASA FIRMS из кэша (GeoJSON, bbox) |
| GET | `/live/incidents` | Кластеризованные LIVE-инциденты (GeoJSON, bbox) |

Все геометрии — GeoJSON в WGS84 (EPSG:4326).

### Два режима данных

- **Сценарий (REPLAY)** — фиксированный детерминированный демо-датасет для Красноярского края (`backend/app/demo/`): инциденты, наблюдения, эволюция во времени, периметр, прогноз, гари. Не требует внешних сервисов, работает всегда.
- **Актуально (LIVE)** — реальные детекции NASA FIRMS (VIIRS SNPP/NOAA-20/NOAA-21). Backend раз в `KROMA_LIVE_REFRESH_SECONDS` (по умолчанию 600 c) сам опрашивает FIRMS Area API, кэширует детекции (`KROMA_LIVE_RETENTION_HOURS` часов) и строит из них простую spatial-temporal кластеризацию (`backend/app/live/clustering.py`) в инциденты. Без `NASA_FIRMS_API_KEY` режим корректно деградирует в статус `offline` — фронтенд отображает это как «источник не подключён», без падений.
- **Подготовленный анализ** — отдельный versioned-набор из manifest. Источник может быть `model_output`, `reference` или `synthetic_demo`; выбранные origin и processing version проходят в API, интерфейс и экспорт без зависимости от FIRMS.

Переключатель режима — в верхней панели фронтенда. Переключение не перезагружает страницу и не трогает состояние карты/темы.

### Frontend

- `/` — карта (MapLibre GL: векторная подложка/спутник/рельеф), очередь инцидентов, инспектор события, таймлайн с ретроспективой, панель слоёв, переключатель LIVE/REPLAY.
- `/events` — таблица инцидентов с сортировкой/фильтрами и split-view.
- `/analytics` — общая демонстрационная динамика и вкладка «Анализ территории» с bbox/датами, картой одного `result_id`, справкой и экспортами. Старое сравнение честно подписано как обзорная подложка с demo-оверлеем, а не снимки указанных сцен.
- Тёмная и светлая темы, переключение мгновенное, без перезагрузки.

## Локальный запуск

### Docker (рекомендуется)

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend: http://localhost:8000 (`/health`, `/api/v1/analysis/readiness`)
- Swagger UI с рабочими примерами: http://localhost:8000/docs
- OpenAPI JSON: http://localhost:8000/openapi.json

PostGIS не участвует в текущем backend и не нужен для основного запуска. При необходимости его можно поднять отдельно: `docker compose --profile persistence up db`.

### Быстрая проверка анализа

В репозитории есть малый набор `kroma-ci-demo@1.0.0` с честным origin `synthetic_demo`. Он нужен для CI и проверки всего тракта, но не подтверждает качество модели на реальных сценах.

```bash
curl -fsS http://localhost:8000/api/v1/analysis/datasets

curl -fsS 'http://localhost:8000/api/v1/analysis?dataset_id=kroma-ci-demo&dataset_version=1.0.0&bbox=99.03,58.03,99.13,58.13&from=2024-08-10&to=2024-08-20'
```

Ответ содержит стабильный `result_id`. Подставьте его в `expected_result_id`:

```bash
KROMA_RESULT_ID='ar_...'
KROMA_QUERY='dataset_id=kroma-ci-demo&dataset_version=1.0.0&bbox=99.03,58.03,99.13,58.13&from=2024-08-10&to=2024-08-20'

curl -fSLo contours.geojson "http://localhost:8000/api/v1/analysis/export/contours?${KROMA_QUERY}&expected_result_id=${KROMA_RESULT_ID}"
curl -fSLo report.csv "http://localhost:8000/api/v1/analysis/export/report?${KROMA_QUERY}&expected_result_id=${KROMA_RESULT_ID}&format=csv"
curl -fSLo report.json "http://localhost:8000/api/v1/analysis/export/report?${KROMA_QUERY}&expected_result_id=${KROMA_RESULT_ID}&format=json"
```

Swagger выполняет те же запросы без браузерного frontend: сначала `GET /api/v1/analysis`, затем экспорты с возвращённым `result_id`.

### Подключение подготовленного набора

1. Поместите `manifest.json` и указанные в нём артефакты в постоянный каталог.
2. Проверьте checksum, метаданные, геометрии, классы и дубли:

```bash
.venv/bin/python -m app.cli.validate_dataset /path/to/prepared-dataset
```

3. Для Docker задайте `KROMA_PREPARED_DATA_HOST_PATH=/path/to/prepared-dataset`; контейнер получает каталог read-only. Для запуска без Docker задайте `KROMA_PREPARED_DATA_PATH=/path/to/prepared-dataset`.
4. Проверьте `/api/v1/analysis/readiness`, затем каталог и пример из него.

Формат и правила подготовки описаны в [`docs/data/prepared-datasets.md`](docs/data/prepared-datasets.md). Смена содержимого требует новой `dataset_version`; checksum mismatch даёт диагностируемую неготовность, а не правдоподобные числа.

## Production и автодеплой

Production-стек описан в `docker-compose.prod.yml`: Caddy принимает HTTP на
порту 80, маршрутизирует API в FastAPI и остальные запросы в production-сборку
Next.js. Пример ручного запуска:

```bash
cp .env.example .env
# задать POSTGRES_PASSWORD, DATABASE_URL и публичный origin в KROMA_CORS_ORIGINS
docker compose -f docker-compose.prod.yml up -d --build
```

Workflow `.github/workflows/deploy.yml` запускает развёртывание после каждого
коммита в `main`. Он передаёт на сервер архив конкретной Git-ревизии, а
`deploy/activate-release.sh` собирает и запускает её. Для workflow требуется
repository secret `KROMA_DEPLOY_SSH_KEY`; сервер принимает этот отдельный ключ
пользователя `kroma-deploy`. При неуспешной проверке здоровья выполняется откат
к предыдущей ревизии.

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
| `KROMA_PREPARED_DATA_HOST_PATH` | Постоянный host-каталог manifest/артефактов для read-only mount в Compose |
| `KROMA_PREPARED_DATA_PATH` | Путь к manifest внутри backend/контейнера |
| `KROMA_ANALYSIS_MAX_DAYS` | Максимальный включительный диапазон дат; по умолчанию 366 дней |
| `KROMA_ANALYSIS_MAX_AREA_HA` | Максимальная площадь bbox; по умолчанию 5 000 000 га |
| `KROMA_ANALYSIS_MAX_FEATURES` | Максимум features в одном результате; по умолчанию 50 000 |
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

Актуально: 44 pytest-теста и 22 frontend unit-теста. В новый набор входят проверки дат UTC, дедупликации assessments, обрезки, площади, hole/MultiPolygon, no coverage vs empty, checksum, `result_id`, MIME/заголовков и CSV/GeoJSON/JSON round-trip.

## Чего пока нет

- Persistence: PostgreSQL/PostGIS поднят в compose, но не подключён — оба режима хранят состояние в памяти процесса backend (демо-датасет генерируется при старте, LIVE-кэш не переживает рестарт).
- ML-пакет (`ml/src/kroma_ml/`) пуст: оценка confidence/priority в LIVE-режиме — эвристика по числу и интенсивности детекций, не модель.
- LIVE-режим не считает периметр, прогноз (P50/P80/P95) и гари — только детекции и кластеры-инциденты; эти слои в UI скрыты, пока активен LIVE.
- Встроенный prepared-набор — `synthetic_demo`. Для финального закрытия WEB-002/WEB-012 команда данных должна подключить разрешённый геопривязанный `model_output` с реальными scene IDs, лицензией и ожидаемыми контрольными числами. Интерфейс и API не выдают synthetic fixture за результат модели.
- Нет авторизации, ролей, персистентных пользовательских настроек.

## Ветки

`main` — единственная и основная ветка, содержит весь текущий код.
