# Данные

Данные хранятся локально и исключены из Git. Скрипты создают `raw/` для исходных загрузок, `interim/` для нормализованных наблюдений и `samples/` для исследовательской выборки.

## fire-aoi/

Конкурсная территория мониторинга из [Мониторинг DATA](https://disk.yandex.ru/d/-rpmevTflbXZQg):

- `fire_monitoring_aoi.geojson` — АОИ «Нижнее Поволжье и Подонье» + зоны UTM 37N/38N (в git)
- копия для карты: `frontend/public/data/fire_monitoring_aoi.geojson`
- локально (не в git): `.gpkg`, `_shapefile.zip`

Регионы в UI/API: субъекты АОИ (Ростовская, Волгоградская, Астраханская, Саратовская, Калмыкия) + демо-сценарий Сибири.

Обновить:

```bash
bash scripts/download_monitoring_data.sh          # AOI
bash scripts/download_monitoring_data.sh --with-tars
python3 scripts/ingest_monitoring_chips.py        # footprints train → карта
```

На карте: слой «Чипы датасета (train)» — footprints с реальной UTM-привязкой.
Test-чипы без геопривязки на карту не кладутся.

## yandex/

Сюда складываются `fire-test-renamed.tar` / `fire-train-renamed.tar` (не в git):

```bash
bash scripts/download_monitoring_data.sh --with-tars
```

Это ML-чипы AF/BS — не live-слой карты. На карту сервиса переносится только `fire-aoi`.

## Официальные train/test (локально, не в git)

ML-код и сервис ожидают такую раскладку (пути настраиваются переменными окружения `KROMA_AF_ROOT`, `KROMA_BS_ROOT`):

```text
data/Мониторинг DATA/train/af/{meta.csv,viirs/,aux/,masks/}   # 420 AF-чипов
data/Мониторинг DATA/train/bs/{meta.csv,sentinel2_pre/,sentinel2_post/,sentinel1_pre/,sentinel1_post/,aux/,masks/}   # 224 BS-чипа
data/test/{meta.csv,sample_submission.csv,af/,bs/}            # 180 AF + 89 BS, без меток и без геопривязки
```

Test-чипы не геопривязываются и не показываются на карте; train-чипы имеют UTM-привязку в `meta.csv`.
