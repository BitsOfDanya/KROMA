# Backend

FastAPI, REST `/api/v1`, Swagger `/docs`, liveness `/health`, model status `/models`.

Из корня: `pip install -e geo -e ml -e backend`, затем `OMP_NUM_THREADS=2 uvicorn app.main:app --app-dir backend --reload`. Полный quickstart и env — в [README](../README.md).

Источники разделены: SCENARIO replay, RAW FIRMS LIVE, official TRAIN rasters/index, immutable prepared model/reference datasets. ML вызывается через единый adapter; Torch/LightGBM не импортируются backend напрямую. Нет весов → readiness false, процесс остаётся жив. Нет FIRMS key → LIVE offline.

GeoJSON/Shapefile/CSV/JSON и TRAIN NPZ доступны через документированные endpoints. Геометрии WGS84, площади вычисляются до UI-упрощения. Контракт prepared datasets: [docs/data/prepared-datasets.md](../docs/data/prepared-datasets.md). Проверки: [приёмка](../docs/qa/final-integration.md).
