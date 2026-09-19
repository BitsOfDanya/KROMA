# Final product integration — 2026-09-19

## Main и границы работы

Baseline main/origin/main: `bf088ec8f9cf6e7bf3029ad55463805f47853e30`. Начальные status/branch/log/fetch выполнены; рабочее дерево было чистым. Повторный fetch перед завершением подтвердил ту же удалённую ревизию. Reset/clean/rebase/force не применялись. Модели не переобучались; `weighted_comboloss_sampler.pt` пропущен по явному последующему указанию пользователя.

## Что уже было

Существующий дизайн и страницы KROMA, MapLibre карта, FastAPI routes, scenario/live, prepared-analysis contract, geo area/clipping, TRAIN metadata index и previews, BS subprocess isolation, competition CLI и финальные веса. Шаблоны v001–v006 submission и исследовательская история уже присутствовали.

## Аудит и исправления

| Подсистема | Исходное состояние | Итог |
| --- | --- | --- |
| frontend | PARTIAL: Predict upload всегда unavailable, inspector prediction/errors placeholders, Research пустой | Полные TRAIN inference/results/exports; рабочие режимы инспектора, Research заполнен |
| backend | PARTIAL: готовые services не подключены к UI; только liveness | Единый adapter, readiness/version/device/missing files, cache, runtime header, raster endpoints |
| ML adapter | STALE: выбирал v005 при наличии v006 weights | Точный перенос существующего red-edge inference; полный byte-identical v006 |
| geo | BROKEN на реальных сложных соседних контурах | GeometryCollection intersection, densification общих границ, STRtree и кэш CRS |
| data/index | PARTIAL: builder только tar metadata | CLI для распакованного TRAIN, GeoTIFF CRS/transform, counts/area из масок |
| map | PARTIAL: яркие квадраты, нет validation geometry | Кластеры AF/BS, subtle footprints, selection, GT/PRED/ERROR на выбранной сцене |
| prepared analysis | MOCK по умолчанию | Сохранён CI fixture, добавлены реальные model/reference derived-наборы 3 BS + 3 AF |
| exports | PARTIAL: уже был Shapefile backend, UI не подключён | GeoJSON/Shapefile/CSV/JSON и NPZ проверены; GT export работает без весов |
| Docker | BROKEN: не устанавливал ml, не содержал bundle/index | Полные зависимости, CPU Torch, libgomp, данные/веса mounts, proxy frontend |
| research | KEEP: подробная история с устаревшим итогом интеграции | История сохранена; обновлён только статус handoff и уточнённые public scores |
| README/docs | STALE: ML объявлен пустым, Research stub, старый task backlog | Новый quickstart, model card/handoff/metrics/demo; планы в docs/archive/tasks |
| config | WORKING/PARTIAL | Расширены env, manifest и previous stable registry; проверен Compose config |
| tests | WORKING, но основные product gaps не покрыты | Регрессии geometry/area/Shapefile/missing mount; smoke и full inference выполнены |

## Статус страниц

| Страница | Статус | Реальная граница |
| --- | --- | --- |
| Overview | Работает | SCENARIO/live + TRAIN clusters; выбранная TRAIN validation geometry |
| Events | Работает | Сценарная таблица помечена SCENARIO; добавлены ссылки на реальные TRAIN BS events |
| Analytics | Работает | Overview остаётся SCENARIO; реальные сводки через Analysis |
| Analysis | Работает | Prepared scenes ∩ bbox ∩ UTC dates; downloader не реализован |
| Data | Работает | 420 AF / 224 BS, поиск/фильтры, previews при наличии raw TRAIN |
| Predict | Работает | Полный TRAIN package, AF/BS v006, metrics, probability, экспорт |
| About | Работает | Проект, два этапа AF+BS, существующие сведения 5BIT |
| Research | Работает | Score progression, pipeline, эксперименты, ограничения |
| Swagger | Работает | `/docs` и OpenAPI; routes вызываются HTTP/curl |

В браузере пройдены страницы, выбор TRAIN, BS prediction/errors, AF I4/I5/difference/GT и local TP/FP/FN, inspector before/after, scenario incident detail, Analysis на реальном prepared model, кнопка Shapefile, operator menu и Swagger UI через frontend proxy. В production подтверждены центрирование карты на выбранной TRAIN-сцене и переключение GT/PRED/ERROR; добавлена расшифровка цветов severity и ошибок. Проверен компактный viewport 900×800 без горизонтального переполнения Predict. Backend проверяет invalid query, missing data/artifacts, checksum, no coverage, empty result через существующие и новые тесты. Полный перебор каждого состояния каждой кнопки на каждом viewport не автоматизирован.

## Проверки и воспроизводимость

- Python: **134 passed, 3 skipped**. Skips относятся к legacy AF research checkpoint и U-Net validation maps, которых нет в локальной поставке; текущий production AF/BS проверен отдельно.
- Frontend: **22 passed**, TypeScript, ESLint, production build — PASS после чистой генерации Next-кэша.
- Ruff и `git diff --check` — PASS.
- `pip check` — PASS; clean Docker dependency install — PASS.
- Geo: 20×20 м = 0.04 га; 4 pixels = 0.16 га, 900 pixels = 36 га; CRS, holes, adjacent classes, geometry collections и Shapefile roundtrip.
- Полный inference: **447 строк, 180 AF + 89 BS, 0 failed chips**, SHA256 `4ad1876c70836b6a003629f4d1dda836f17d8070a59d2a5c88c29b50c024865a` совпал с submission_v006. Проверены keys/order, RLE roundtrip, duplicates, NaN и class overlap. В данном TEST нет BS с cloud_frac ≥ 0.5; все имеющиеся облачные сцены включены в полный прогон.
- Service smoke `BS_te_000001`, `000020`, `000089` совпал с reference; финальный повтор `BS_te_000001` после metadata-изменений также exact.
- Missing weights: `/health` 200/ok, readiness false, inference unavailable; GT export 200.
- Все три prepared-набора проходят dataset validator. Valid coverage построен по маскам; BS date-only normalizes to 00:00 UTC, произвольное время съёмки не выдумывается.
- Docker backend и frontend builds — PASS; контейнерный AF_tr_000001 = 44 pixels, BS_tr_000001 = 462.12 га. Compose local/prod config — PASS.
- HTTP/curl: health/models/docs/openapi, datasets, inference, overlays, raw masks/probability, validation geometry, scenario/live/map routes, real prepared analysis и exports — PASS.

[Inference evidence](inference-verification.json), [API timing evidence](api-verification.json), [локальные runtime versions](runtime-versions.txt), [метрики](../key_metrics.md).

## Cleanup

KEEP: source, tests, license/критичные notices, final weights, submission CSV/metadata, research report и experiment history. Синтетический CI fixture сохранён с origin synthetic_demo.

MOVE: прежние планы `docs/tasks` → `docs/archive/tasks`; ссылки архива исправлены.

DELETE: пустой `docs/tasks/task-1`; из UI удалены неработающий JPEG predict flow, placeholders prediction/errors и фиктивная анимация стадий Analysis. Старый upload endpoint остался совместимым диагностическим endpoint с явным unavailable.

IGNORE: venv, IDE/cache, raw datasets, previews/runtime/tmp, OOF `.npy/.npz`, local candidates, logs, распакованный локальный checkpoint `best_class1.pt/`. Дубли правил .gitignore сокращены. В tracked не было OS/IDE/log/temp/notebook мусора. Репозиторий не очищался разрушительными Git-командами.

## Сверка отчёта

README, UI, manifest и research/report.md согласованы: GOLD v006 / 0.8176; previous v005 / 0.8127. Старые утверждения research сохранены как исторические этапы, итоговая строка «v006 не интегрирован» исправлена. Полный pipeline и inputs не менялись математически; обучение не выполнялось.

## Известные ограничения

1. Пространственный query — bbox + даты; polygon API/downloader не добавлялись. Prepared outputs используются только в своём покрытии.
2. Метрики TRAIN in-sample; prepared real demo содержит 6 сцен. Это не независимая оценка качества.
3. Нет доказанной связи каждого AF chip с BS event; полная цепочка incident lifecycle остаётся SCENARIO и не выдаётся за реальное наблюдение.
4. Первый web BS запрос новой сцены запускает изолированный neural subprocess; competition запускает один batch. Persistent worker не внедрялся. Кэш versioned, неперсистентный, 12 записей; при замене bundle перезапуск.
5. LIVE требует FIRMS key; внешние картографические тайлы требуют сети. RAW FIRMS не вход AF-модели.
6. Нет авторизации/ролей и интегрированного PostGIS. Кроссплатформенная bit-exact гарантия не заявлена.
7. Полное воспроизведение training history требует исследовательских OOF/raw inputs вне Git. Запуск inference требует только shipped bundle и официальный input package.
8. Deployment/push не выполнялись; существующий main workflow разворачивает новые опубликованные коммиты.

## Команды и demo

Команды запуска — в начале [README](../../README.md). Demo: Overview → Events → Data → BS_tr_000001 → PRE/POST → GT/pred/errors → Predict → area/severity → GeoJSON/Shapefile/NPZ → real Analysis → Swagger. Подробный сценарий: [demo_script](../demo_script.md).

## Изменённые файлы

Полный состав integration-коммита (A — добавлен, M — изменён, R — перемещён, D — удалён):

```text
M	.dockerignore
M	.env.example
M	.github/workflows/ci.yml
M	.gitignore
M	README.md
M	backend/Dockerfile
M	backend/README.md
M	backend/app/api/health.py
M	backend/app/api/v1/datasets.py
M	backend/app/main.py
A	backend/app/prepared_data/kroma-official-train-model/burn_zones.geojson
A	backend/app/prepared_data/kroma-official-train-model/hotspots.geojson
A	backend/app/prepared_data/kroma-official-train-model/manifest.json
A	backend/app/prepared_data/kroma-official-train-reference/burn_zones.geojson
A	backend/app/prepared_data/kroma-official-train-reference/hotspots.geojson
A	backend/app/prepared_data/kroma-official-train-reference/manifest.json
M	backend/app/services/analysis.py
M	backend/app/services/ml_service.py
M	backend/app/services/prediction.py
M	backend/app/services/train_dataset.py
M	backend/pyproject.toml
M	data/fire-aoi/monitoring_chips.geojson
M	data/fire-aoi/train_chips_index.json
M	docker-compose.prod.yml
M	docker-compose.yml
R098	docs/tasks/README.md	docs/archive/tasks/README.md
R100	docs/tasks/WEB-001-analysis-contract.md	docs/archive/tasks/WEB-001-analysis-contract.md
R100	docs/tasks/WEB-002-prepared-datasets.md	docs/archive/tasks/WEB-002-prepared-datasets.md
R100	docs/tasks/WEB-003-geometries-and-areas.md	docs/archive/tasks/WEB-003-geometries-and-areas.md
R100	docs/tasks/WEB-004-analysis-api.md	docs/archive/tasks/WEB-004-analysis-api.md
R100	docs/tasks/WEB-005-analysis-query-ui.md	docs/archive/tasks/WEB-005-analysis-query-ui.md
R100	docs/tasks/WEB-006-analysis-map.md	docs/archive/tasks/WEB-006-analysis-map.md
R100	docs/tasks/WEB-007-analysis-report.md	docs/archive/tasks/WEB-007-analysis-report.md
R100	docs/tasks/WEB-008-exports.md	docs/archive/tasks/WEB-008-exports.md
R100	docs/tasks/WEB-009-data-provenance.md	docs/archive/tasks/WEB-009-data-provenance.md
R100	docs/tasks/WEB-010-verification.md	docs/archive/tasks/WEB-010-verification.md
R100	docs/tasks/WEB-011-reproducible-delivery.md	docs/archive/tasks/WEB-011-reproducible-delivery.md
R100	docs/tasks/WEB-012-final-acceptance.md	docs/archive/tasks/WEB-012-final-acceptance.md
R100	docs/tasks/analysis-contract.md	docs/archive/tasks/analysis-contract.md
A	docs/demo_script.md
A	docs/key_metrics.md
A	docs/ml_handoff.md
A	docs/model_card.md
A	docs/qa/api-verification.json
A	docs/qa/final-integration.md
A	docs/qa/inference-verification.json
A	docs/qa/runtime-versions.txt
D	docs/tasks/task-1
M	frontend/Dockerfile
M	frontend/README.md
M	frontend/eslint.config.mjs
M	frontend/next.config.ts
M	frontend/public/data/monitoring_chips.geojson
M	frontend/src/app/about/page.tsx
M	frontend/src/app/research/page.tsx
M	frontend/src/features/analysis/AnalysisProgress.tsx
M	frontend/src/features/analysis/AnalysisReport.tsx
M	frontend/src/features/analytics/AnalyticsView.tsx
M	frontend/src/features/events/EventsView.tsx
M	frontend/src/features/explorer/ChipInspector.tsx
M	frontend/src/features/explorer/ExplorerView.tsx
M	frontend/src/features/map/KromaMap.tsx
M	frontend/src/features/map/MapDataSync.tsx
M	frontend/src/features/map/MapInteractions.tsx
M	frontend/src/features/map/MapLegend.tsx
M	frontend/src/features/map/layers/chips.ts
M	frontend/src/features/map/map.module.css
M	frontend/src/features/predict/PredictView.tsx
A	frontend/src/features/predict/PredictionResult.tsx
M	frontend/src/lib/api/endpoints.ts
M	frontend/src/lib/api/types.ts
M	frontend/src/state/workspace.ts
M	geo/README.md
M	geo/pyproject.toml
M	geo/src/kroma_geo/raster_vector.py
M	geo/src/kroma_geo/vector.py
M	ml/README.md
A	ml/artifacts/README.md
M	ml/artifacts/manifest.json
M	ml/pyproject.toml
M	ml/src/kroma_ml/artifacts.py
M	ml/src/kroma_ml/bs_neural.py
A	ml/src/kroma_ml/bs_rededge.py
M	ml/src/kroma_ml/competition.py
M	ml/src/kroma_ml/service.py
M	pyproject.toml
M	research/README.md
M	research/experiments/bs_v006_ctx_diag.py
M	research/experiments/bs_v006_rededge_diag.py
M	research/report.md
M	scripts/build_train_index.py
M	scripts/build_train_prepared_dataset.py
M	scripts/mount_artifacts.py
M	tests/backend/test_analysis_api.py
M	tests/backend/test_health.py
A	tests/backend/test_product_integration.py
M	tests/geo/test_raster_vector.py
M	tests/geo/test_vector.py
```
