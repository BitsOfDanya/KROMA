# Подготовленные наборы анализа

## Назначение

Backend читает подготовленные результаты только через неизменяемый `manifest.json`. Набор не обращается к FIRMS или спутниковому архиву во время пользовательского запроса. Одна версия должна после рестарта давать те же геометрии, числа и `result_id`.

Встроенный `backend/app/prepared_data` — малый `synthetic_demo` для CI. Для демонстрации качества модели нужен отдельный разрешённый набор с `origin: model_output`; менять origin у fixture запрещено.

## Структура каталога

```text
prepared-dataset/
├── manifest.json
├── hotspots.geojson
└── burn_zones.geojson
```

`KROMA_PREPARED_DATA_PATH` может указывать на этот каталог, непосредственно на manifest или на родительский каталог с несколькими дочерними наборами. Backend загружает только версии, у которых manifest, checksum и содержимое прошли проверку.

## Manifest v1

Обязательные группы полей:

| Поля | Смысл |
| --- | --- |
| `dataset_id`, `dataset_version`, `schema_version` | Стабильная идентичность и immutable-версия |
| `origin` | Только `model_output`, `reference` или `synthetic_demo` |
| `processing_version` | Версия весов/алгоритма или идентификатор запуска |
| `available_from`, `available_to`, `extent` | Доступный период и bbox WGS84 |
| `af_coverage`, `bs_coverage`, `bs_valid_coverage` | Раздельное покрытие термоточек, картирования и валидных BS-пикселей |
| `source_crs`, `area_crs` | CRS артефакта и выбранная равноплощадная/метрическая CRS расчёта |
| `mask` | Классы 0/1/2/3, nodata, resolution и правило validity |
| `scenes` | Реальные scene IDs, спутник, UTC-время, роль, известная облачность |
| `artifacts` | Относительный путь и SHA-256 каждого файла |
| `license`, `attribution`, `distribution` | Право использования и ограничения передачи |
| `example` | Содержательный bbox и даты для UI, Swagger и smoke-теста |

Путь артефакта не может выходить из каталога manifest. Абсолютные developer-paths и секреты не допускаются.

## GeoJSON термоточек

`hotspots.geojson` — `FeatureCollection` точек WGS84. У каждой feature обязательны уникальный `id`, `properties.id`, UTC `acquired_at` и честное название `source`. Допустимы исходные показатели вроде FRP, но FRP не интерпретируется как площадь.

Точки фильтруются по `[from 00:00 UTC, to + 1 день 00:00 UTC)` и включаются на границе bbox. Повторный ID отклоняется при загрузке.

## GeoJSON зон

`burn_zones.geojson` содержит только зоны классов, без отдельного полного контура, который мог бы удвоить площадь. Геометрия — Polygon или MultiPolygon WGS84, включая holes.

Обязательные properties:

- `id`, `burn_event_id`, `assessment_id`;
- `class_id`: 1, 2 или 3;
- `severity`: соответственно `low`, `moderate`, `high`;
- UTC `after_acquired_at`;
- `is_complete`; частичная assessment не выбирается как полная;
- `scene_ids`.

Внутри одной assessment классы не могут пересекаться по положительной площади. Для одного `burn_event_id` сервер выбирает последнюю полную assessment, дата которой попала в запрос. Затем геометрия пересекается с AOI, и только после этого площадь считается в `area_crs`.

## Проверка

```bash
python -m app.cli.validate_dataset /path/to/prepared-dataset
```

Команда проверяет manifest schema, наличие и SHA-256, JSON/GeoJSON, уникальность ID, времена с timezone, координаты, допустимые классы, валидность геометрий и положительные перекрытия классов. Возврат `0` означает, что набор можно публиковать в каталоге; `1` — что backend не должен выдавать из него результат.

После проверки:

```bash
curl -fsS http://localhost:8000/api/v1/analysis/readiness
curl -fsS http://localhost:8000/api/v1/analysis/datasets
```

## Подготовка из растровой маски

`kroma_geo.vector.vectorize_class_mask` предоставляет проверяемую базовую векторизацию малых категориальных масок 0–3 с affine transform, holes и несколькими компонентами. Для производственных растров допустим rasterio/GDAL pipeline, но его выход обязан пройти тот же manifest validator и независимую сверку площади с пиксельной маской.

Nodata/облачность не равны классу 0. Если валидной области нет, API возвращает `no_valid_data` и `null` для площадей, а не ложные нули.

## Передача и обновление

- Хранить единственную копию ограниченного набора внутри временного контейнера нельзя. В Compose host-каталог монтируется read-only через `KROMA_PREPARED_DATA_HOST_PATH`.
- При любом изменении артефакта пересчитать SHA-256 и выпустить новую `dataset_version`; старую версию не менять на месте.
- Не публиковать сцены, веса, ключи и производные данные, если лицензия этого не разрешает. Организаторам передаётся разрешённый архив или защищённая ссылка вместе с checksum.
- После рестарта повторить catalog → analysis → exports и сверить `result_id` и площади.
