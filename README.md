# KROMA

Двухэтапный мониторинг природных пожаров: **Active Fire (AF)** по VIIRS и **Burn Severity (BS)** по Sentinel-2 до/после. Карта, Official TRAIN inspector, GOLD v006 inference, пространственно-временной анализ, площади и экспорт GeoJSON / Shapefile ZIP / CSV / JSON.

## Быстрый запуск

Python 3.12, Node.js 22. На macOS для LightGBM нужен `libomp` (`brew install libomp`). Полный комплект production-весов уже находится в `ml/artifacts` и проверяется по SHA256. Команды выполняются из корня репозитория; backend и frontend запускайте в разных терминалах.

```bash
git clone https://github.com/BitsOfDanya/KROMA.git && cd KROMA
python3.12 -m venv .venv && source .venv/bin/activate
python -m pip install -e geo -e ml -e backend pytest ruff
python scripts/mount_artifacts.py
npm ci --prefix frontend
OMP_NUM_THREADS=2 .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
npm run dev --prefix frontend
python inference.py --data-dir data/test --output tmp/submission.csv --workers 2 --threads 2
```

Последняя команда требует локальный официальный TEST; веб и встроенный prepared-анализ работают без него. Откройте **http://localhost:3000**, Swagger **http://localhost:8000/docs**. Frontend по умолчанию проксирует `/api`, `/docs`, `/health`, `/models` в backend; для другого порта используйте `KROMA_BACKEND_URL` при запуске/сборке frontend. Существующие процессы останавливать не требуется: задайте свободные порты.

Для Predict и исходных PRE/POST разместите официальный TRAIN в `data/Мониторинг DATA/train` либо задайте `KROMA_TRAIN_ROOT`. Затем:

```bash
python scripts/build_train_index.py --train-root "$KROMA_TRAIN_ROOT"
```

Без переменной используйте `python scripts/build_train_index.py`. Индекс и компактные derived-наборы уже включены в Git, сырые растры — нет. `.env.example` служит образцом; локальный Python не загружает `.env` автоматически. Для uvicorn можно явно добавить `--env-file .env`, предварительно исправив контейнерные пути на локальные.

## Что можно показать сразу

- **Обзор**: существующая карта KROMA; TRAIN AF/BS кластеры, сдержанные footprints, выбранная сцена и GT / Prediction / Errors при приближении.
- **События**: явно обозначенный SCENARIO; полный сценарный incident inspector. Реальные TRAIN-сцены и события доступны через «Данные».
- **Аналитика**: SCENARIO для демонстрационной динамики; реальные динамические итоги в «Анализе территории».
- **Анализ**: bbox + включительный период UTC → пересекающиеся prepared scenes → термоточки, контуры, severity и справка. Рабочие примеры берутся из каталога наборов.
- **Данные**: 420 AF + 224 BS official TRAIN, поиск/фильтры, метаданные, I4/I5/difference, PRE/POST slider, dNBR, landcover, GT и model output.
- **Предикт**: загрузка своего ZIP с полным чипом для AF/BS inference (маска и площадь/число термоточек) или выбор TRAIN-сцены для GT, errors, локальных метрик, GeoJSON, Shapefile и NPZ.
- **О проекте / Research / О команде**: реальные сведения проекта, pipeline, leaderboard и ограничения.

Обычный JPEG не является входом AF/BS. `/api/v1/inference/upload` принимает один ZIP до 64 МБ с TIFF одного чипа: каждый TIFF имеет размер 256×256, имена имеют общий `ID`. Для AF нужны `ID_VIIRS_I1-I5.tif` (8 каналов) и `ID_AUX.tif` (5 каналов). Для BS нужны `ID_Sentinel-2_pre.tif`, `ID_Sentinel-2_post.tif` (по 10 каналов), `ID_Sentinel-1_pre.tif`, `ID_Sentinel-1_post.tif` (по 2 канала) и `ID_AUX.tif` (3 канала). Папки внутри ZIP допустимы. Разметка и координаты не требуются; метрики качества и векторный экспорт для своего ZIP не доступны. TRAIN-предикт требует подключённых исходных растров на сервере.

## Архитектура

```text
Next.js / React / MapLibre
          ↓ REST
FastAPI → dataset/index → previews / TRAIN geometry
        → ML adapter predict_af / predict_bs → versioned cache
        → prepared scenes + bbox/dates → summary / vector exports
          ↓
kroma_ml: AF LightGBM | isolated BS Torch → physics / refiners v006
kroma_geo: CRS, raster geometry, pixel area, clipping, topology
```

Backend не импортирует Torch и LightGBM: модель вызывается через `kroma_ml.service`. Torch BS stage изолирован в subprocess для совместимости macOS MPS + LightGBM. Competition запускает один neural subprocess на весь набор BS. Первый запрос новой сцены в вебе пока запускает отдельный neural subprocess; повторные результаты и геометрии кэшируются по `scene_id + model_version` (LRU, 12 записей). После замены комплекта весов требуется перезапуск сервиса.

| Каталог | Назначение |
| --- | --- |
| `frontend/` | Существующий интерфейс KROMA и карта |
| `backend/app/` | REST, сервисы, источники, derived prepared datasets |
| `ml/src/kroma_ml/` | Production adapter, competition inference, модели и признаки |
| `ml/artifacts/manifest.json` | CURRENT GOLD, входы/выходы, пороги, SHA256 файлов |
| `geo/` | Площадь, CRS, векторизация и проверка геометрий |
| `data/fire-aoi/` | TRAIN index и разрешённый AOI |
| `research/` | Сохранённая история экспериментов и итоговый отчёт |
| `scripts/` | Проверка/упаковка весов, builder индекса и prepared-наборов |
| `tests/` | Backend, geo, ML, интеграционные проверки |
| `artifacts/submissions/` | Исторические submission v001–v006 и metadata |

## Данные и происхождение

Официальные TRAIN/Test выдаются организаторами: [Мониторинг DATA](https://disk.yandex.ru/d/-rpmevTflbXZQg). Условия использования определяются организаторами; собственную лицензию на исходные данные проект не назначает.

```text
data/Мониторинг DATA/train/
  af/meta.csv, viirs/, aux/, masks/
  bs/meta.csv, sentinel2_pre/, sentinel2_post/, sentinel1_pre/, sentinel1_post/, aux/, masks/
data/test/
  meta.csv, sample_submission.csv, af/, bs/
```

Builder TRAIN читает meta и маски GeoTIFF, CRS, affine transform, размер, bbox, event/date/satellite, cloud/valid и counts severity. Идентификаторы TEST не геопривязываются, дата/место TEST не восстанавливаются. Альтернатива распакованному TRAIN для старых previews — `data/yandex/fire-train-renamed.tar`; для production inference нужен распакованный каталог.

В `backend/app/prepared_data/` включены:

| Набор | Источник | Содержимое |
| --- | --- | --- |
| `kroma-ci-demo@1.0.0` | `synthetic_demo` / SCENARIO | Малый детерминированный CI fixture |
| `kroma-official-train-model@v006` | `model_output`, in-sample | 3 BS + 3 AF сцены, 2916 severity-зон, 81 AF point |
| `kroma-official-train-reference@v006` | `reference` | 1757 зон official TRAIN GT тех же BS-сцен |

Prepared-анализ **выбирает уже подготовленные результаты**, а не скачивает спутниковую съёмку для произвольного AOI. Вне покрытия API возвращает `no_coverage`. Встроенный каталог проверяет SHA256, классы, геометрии, даты и непересечение зон.

Воспроизведение компактного demo (без обучения):

```bash
OMP_NUM_THREADS=2 python scripts/build_train_prepared_dataset.py --bs 3 --af 3
python -m app.cli.validate_dataset backend/app/prepared_data
```

Построение другой выборки требует отдельной версии immutable-набора. Веса и TRAIN должны соответствовать handoff.

## Модели и метрики

**CURRENT GOLD = v006; previous stable = v005.** AF не менялся между submission v001–v006. Порог AF — 0.765; 39 признаков LightGBM. BS: v003 neural ensemble → v004 physics/refiner → component classifier + refiner2 с red-edge v006. Решающие пороги BS: 0.3 / 0.8 / 0.2.

| Submission | Public score |
| --- | ---: |
| v001 | 0.5526 |
| v002 | 0.6457 |
| v003 | 0.7298 |
| v004 | 0.7406 |
| v005 | 0.8127 |
| **v006** | **0.8176** |

Public scores подтверждены командой. Они не равны локальному TRAIN F1 или BS OOF. BS v006 OOF: all-valid **0.43552**, strict **0.44677** по metadata эксперимента. TRAIN predictions — **in-sample**, поскольку финальные веса обучены на всём TRAIN. Подробности: [model card](docs/model_card.md), [метрики](docs/key_metrics.md), [research/report.md](research/report.md).

## Веса и конфигурация

`KROMA_ML_ARTIFACTS_PATH` задаёт единственный production root, по умолчанию `ml/artifacts`. Неявного fallback на исследовательские файлы нет. `python scripts/mount_artifacts.py` проверяет все 7 текущих артефактов до копирования; `--source <bundle> --dest <directory>` переносит валидированный комплект с manifest. Не скачивает и не обучает модели.

Пути и контрольные суммы: [ml/artifacts/README.md](ml/artifacts/README.md). В текущем Git входят оба neural checkpoint, AF bundle, physics JSON, v004 refiner и v006 refiners; v005 файлы сохранены для истории. Health остаётся доступным при отсутствии весов, inference сообщает недоступность.

## Competition inference и воспроизводимость

```bash
python inference.py --data-dir data/test --output tmp/submission.csv \
  --workers 2 --threads 2 --profile tmp/runtime.json \
  --verify-against artifacts/submissions/submission_v006.csv
```

Default — v006. Pipeline не запускает REST, векторизацию, аналитику или DB. Сверяются ключи/порядок sample_submission, 447 строк для данного TEST, RLE, отсутствие NaN/дубликатов и пересечений BS-классов. Ошибка chip останавливает выдачу submission; пустая маска не выдаётся за успешный fallback.

На машине интеграции полный прогон 180 AF + 89 BS дал **CSV-identical v006**, 452.88 с при 2 workers × 2 threads, BS neural stage 19.81 с. Это измерение при параллельных проверках; время зависит от железа. Побитовое равенство между разными Torch/device версиями не обещается. Seeds training-конфигов — 42; production inference не обучает модели. Для своей платформы выполняйте `--verify-against`.

## Обучение и исследовательская история

Обучение не требуется для запуска поставки. В этом integration-проходе модели не переобучались. Исторические команды и разбиения сохранены в [ml/README.md](ml/README.md), [research/report.md](research/report.md), `research/experiments/af_final_model.py`, `bs_track.py`, `bs_v004_build.py`, `bs_v005_build.py`, `bs_v006_infer.py`. Последний исследовательский скрипт **содержит обучение** full refiners; для готового inference используйте корневой `inference.py`. OOF-кэши/промежуточные массивы не являются обязательными runtime-артефактами и не входят в Git.

## REST API и экспорт

| Endpoint | Результат |
| --- | --- |
| `GET /health`, `GET /models` | Liveness, AF/BS readiness, версия, missing artifacts, device policy |
| `GET /api/v1/models`, `/api/v1/ml/status` | Manifest provenance и model status |
| `GET /api/v1/datasets/train?kind=bs` | Настоящий TRAIN index и counts |
| `GET /api/v1/datasets/train/{id}` | Метаданные и доступность inspector |
| `POST /api/v1/inference/af`, `/inference/bs` | JSON `{"chip_id":"..."}` → mask metadata, metrics, runtime, geometry |
| `GET /api/v1/datasets/train/{id}/overlay/{layer}` | PNG: pred / gt / error / probability |
| `GET /api/v1/datasets/train/{id}/rasters` | NPZ: исходные mask/probability/GT/valid, version |
| `GET /api/v1/datasets/train/{id}/geometry?layer=pred` | WGS84 validation features для карты |
| `GET /api/v1/datasets/train/{id}/export?format=geojson` | GeoJSON; `format=shp` → ZIP Shapefile |
| `GET /api/v1/analysis/datasets`, `/analysis/readiness` | Каталог и проверка целостности prepared-наборов |
| `GET /api/v1/analysis` | `dataset_id`, `dataset_version`, `bbox`, `from`, `to` |
| `GET /api/v1/analysis/export/contours` | GeoJSON текущего result_id |
| `GET /api/v1/analysis/export/shapefile` | ZIP с SHP/SHX/DBF/PRJ/CPG |
| `GET /api/v1/analysis/export/report?format=csv` | CSV; `format=json` → полный JSON |
| `GET /api/v1/live/status`, `/live/hotspots`, `/live/incidents` | RAW FIRMS и эвристические кластеры |

Все exports анализа требуют `expected_result_id`, равный отображаемому результату; mismatch → 409. На HTTP-ответах есть `X-Runtime-Ms`, inference дополнительно возвращает model/vectorize/total. Shapefile ограничивает имена DBF-полей десятью символами: `model_version` → `model_ver`, `scene_id` сохраняется, CRS — WGS84. GeoJSON содержит `contour_id`, scene/event, severity, area_ha, model_version, source.

Площадь BS-пикселя **20 × 20 м = 0.04 га**. TRAIN inference считает площадь в исходной проекции растра. AOI analysis обрезает несглаженные векторы и считает EPSG:6933; небольшая разница с номинальной UTM-пиксельной площадью ожидаема и метод указан в `calculation`. UI не определяет отчётную площадь.

Пример:

```bash
curl -fsS http://localhost:8000/health
curl -fsS -H 'Content-Type: application/json' -d '{"chip_id":"BS_tr_000001"}' http://localhost:8000/api/v1/inference/bs
curl -fSLo tmp/contours.zip 'http://localhost:8000/api/v1/datasets/train/BS_tr_000001/export?format=shp'
```

## Docker и deployment

```bash
cp .env.example .env
docker compose up --build
```

Compose монтирует TRAIN и веса read-only; пути `KROMA_TRAIN_HOST_PATH` / `KROMA_ML_ARTIFACTS_HOST_PATH` можно изменить в `.env`. Backend image устанавливает geo + ml + backend и CPU Torch; GPU deployment требует соответствующего Torch runtime. Необязательная БД: `docker compose --profile persistence up db`.

Production: `docker compose -f docker-compose.prod.yml up -d --build`; Caddy обслуживает API и frontend. `.github/workflows/deploy.yml` выкладывает main через release/health/rollback. При первом деплое `deploy/prepare-train.sh` скачивает официальный TRAIN (~2.14 ГБ) в `/opt/kroma/shared/train`, который монтируется в backend и сохраняется между релизами. Для загрузки требуется не менее 3 ГиБ свободного места в `/opt/kroma/shared`. Integration-проход сам по себе не публикует изменения и не запускает deploy.

## Проверки

```bash
.venv/bin/ruff check .
.venv/bin/python -m pytest -q
npm run typecheck --prefix frontend
npm run lint --prefix frontend
npm test --prefix frontend
npm run build --prefix frontend
```

Проверены API, площади, CRS, geometry intersection, Shapefile roundtrip, hash/missing-artifact behavior, TRAIN previews/overlays, полный submission и frontend. Подробности, страницы, timings и ограничения: [приёмка](docs/qa/final-integration.md). Стабильная демонстрация: [docs/demo_script.md](docs/demo_script.md).

## Ограничения

- Analysis принимает bbox + даты; произвольный polygon в этом UI/API не заявлен. Автоматического скачивания Sentinel нет.
- Реальные prepared outputs охватывают 6 выбранных TRAIN-сцен; это демонстрация тракта, не независимый test качества.
- Events и обзорная аналитика остаются явно маркированным SCENARIO. Нет доказанной связи отдельного AF chip с конкретным BS fire event; такая связь не выдумывается.
- LIVE требует `NASA_FIRMS_API_KEY`; без ключа возвращает offline. RAW FIRMS не эквивалентен входу AF-модели, LIVE не рассчитывает BS/прогноз.
- Карта использует внешние тайлы, которые требуют сети. TEST никогда не отображается на карте.
- Кэш и настройки процесса неперсистентны; PostGIS не подключён к текущим сервисам. Нет авторизации/ролей.
- На новой TRAIN-сцене веб BS запускает отдельный изолированный neural subprocess; competition использует batch. Persistent worker не внедрялся без отдельной гарантии точного равенства.
