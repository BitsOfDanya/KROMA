# Контракты наблюдений и событий

Версия `1.0` фиксирует обменный формат. Pydantic-модели находятся в `backend/app/schemas/observations.py`; ingestion выдаёт по одному `HotspotObservation` на строку JSONL. Эти модели не означают, что база данных и API событий уже реализованы.

| Сущность | Основные поля | Правило |
| --- | --- | --- |
| `Coordinates` | `latitude`, `longitude` | WGS84, градусы; долгота −180…180, широта −90…90 |
| `HotspotObservation` | `observation_id`, `source`, `satellite`, `acquired_at`, `location`, `brightness_ti4_kelvin`, `brightness_ti5_kelvin`, `frp_mw`, `scan_km`, `track_km`, `source_confidence`, `daynight`, `source_version` | Одна детекция источника; время UTC; `observation_id` детерминирован из источника, спутника, времени и координат |
| `FireEvent` | `event_id`, `first_observed_at`, `last_observed_at`, `centroid`, `observation_ids`, `kroma_confidence`, `priority_score` | Будущий результат кластеризации; `observation_ids` связывают событие с исходными детекциями |

`source_confidence` сохраняет категорию VIIRS `l`, `n` или `h`. Это характеристика исходного алгоритма NASA, а не вероятность пожара от KROMA. `kroma_confidence` и `priority_score` пока не рассчитываются и могут быть `null`. `frp_mw` означает мощность излучения в МВт, а не площадь пожара.

При повторной загрузке одинаковой детекции её ID сохраняется. Изменение алгоритма формирования ID или полей требует новой версии схемы и миграции. Сырые CSV и нормализованные наборы находятся в `data/`, а код — в `backend/` и `scripts/`.
