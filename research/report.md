# KROMA: active-fire research baseline

Состояние на 18.09.2026. Целевая география — вся РФ; красноярский AOI лишь один пилот. Этот отчёт отделяет работающий код от проверяемых гипотез. Источники, лицензии и статусы загрузки сведены в [каталог](../docs/data/sources.md).

## PRODUCT: от аномалии к решению

`thermal anomaly → satellite observation → hotspot → suspected incident → confirmed/monitored incident → priority update → closed incident → burn scar → severity → damage summary`. Спутник наблюдает тепловую аномалию в пикселе, а не факт, границу или площадь пожара. `source_confidence` NASA описывает алгоритм детекции пикселя; `P(real wildfire)` требует других меток и калибровки. FRP — интенсивность излучения, не площадь.

| Блок | Сейчас в сервисе | Research/data слой | Другой ML поток |
| --- | --- | --- | --- |
| Detection | Backend LIVE получает FIRMS и нормализует VIIRS NRT | Воспроизводимые исторические выборки, источники, AOI, фильтрация | — |
| Monitoring | LIVE уже группирует наблюдения своим алгоритмом; UI показывает инциденты | Независимый DBSCAN baseline, временной ряд, Thermal Memory | — |
| Decision support | UI/backend имеют эвристические индикаторы | Контекст, размеченная confidence, отдельные threat и priority, проверка ложных тревог | — |
| Post-fire | У сервиса есть демо слои | Только интеграционный контракт и проверка связи с incident | Ромин Sentinel-2 segmentation, burn severity, площадь по классам |

Жизненный цикл требует постоянного `incident_id`, ручного подтверждения, закрытия/переоткрытия и журнала изменений. Текущий исследовательский ID — хэш полного набора наблюдений и **меняется при новой детекции**; его нельзя внедрять в LIVE без отдельной логики identity.

## Рынок и проверка гипотезы

| Аналог | Подтверждённые возможности | Что это означает для KROMA |
| --- | --- | --- |
| [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/) | Бесплатные глобальные MODIS/VIIRS thermal detections, карты/API/уведомления; SP и NRT различаются по задержке и качеству. | Карта горячих точек и их доставка — **commodity**. Детекции включают промышленные и природные источники тепла. |
| [ИСДМ-Рослесхоз / Авиалесоохрана](https://aviales.ru/default.aspx?textpage=176) | Действующий мониторинг всей РФ объединяет спутники, метео, молнии, картографию, региональную отчётность и диспетчеризацию. | Nationwide мониторинг и интеграция погоды уже существуют. Открытая incident-level выгрузка и условия доступа к меткам не подтверждены. |
| [СКАНЭКС «Карта пожаров»](https://new.scanex.ru/company/news/analiz-pozharnoy-obstanovki-na-territorii-rossii-po-sputnikovym-dannym-za-period-s-18-po-27-iyulya-2/) | Покрывает РФ, показывает термоточки, скопления как крупные пожары, статистику по субъектам и снимки. | Простая группировка и региональная статистика тоже **commodity**; нужны проверенные triage и прозрачность. |
| [OroraTech Wildfire Solution](https://ororatech.com/all-products/wildfire-solution) | Коммерческий end-to-end продукт заявляет кластеры, fire confidence, погоду/растительность/terrain, spread simulation, burnt area и severity; [справка](https://help.ororatech.com/must-read) описывает фильтрацию false positives и Incident Overview. | Нельзя позиционировать confidence, кластеры, прогноз или severity как уникальные сами по себе. Сравнение алгоритмов/качества недоступно без данных. |
| [NOAA Hazard Mapping System](https://www.ospo.noaa.gov/products/land/hms.html) | Для Северной Америки аналитики проверяют автоматические fire detections и ложные тревоги, наносят дым. | Human-in-the-loop и контроль false positives — практичный эталон процесса, но география продукта не РФ. |

**Рабочая гипотеза отличия** — прозрачная российская очередь инцидентов, которая объясняет сочетание повторяющегося теплового источника, сезонности, типа земли, динамики и объектов под угрозой. Это **гипотеза**, пока нет ручной оценки false-positive reduction, скорости и полезности для операторов. Повторяющийся жар **не всегда ложный** (в частности, тление и повторные лесные пожары); Thermal Memory должна давать признак и объяснение, а не автоматически скрывать alert. [NASA](https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_MODIS_Firehotspots.html) прямо указывает факелы и вулканы среди аномалий; [NOAA](https://www.ospo.noaa.gov/products/land/hms.html) перечисляет промышленность, солнечные блики, дымовые плюмы и артефакты. Для РФ отдельно проверяем факелы нефтегазовой отрасли, металлургию, сельхозпалы, населённые пункты и повторные очаги.

## SCALE и архитектура данных

1. **Россия, лёгкий уровень:** детекции FIRMS, слой границ, метаданные источника, агрегаты инцидентов; запросы по `AOI / region / date_from / date_to / source / mode`, пространственные тайлы и интервалы API по 1–5 дней. Это не обещание скачать всю страну за один запрос.
2. **Регион:** тайлы land cover, extracts OSM, ERA5-Land, DEM и растительность по выбранному AOI. Упрощённый [geoBoundaries](https://www.geoboundaries.org/api/current/gbOpen/RUS/ADM1/) получен и проверен на пяти городах; его 2017/83 единицы не годятся для точной текущей статистики без ревизии. Для больших векторных слоёв есть необязательный Shapely: полный запуск четырёх пилотов сократился примерно с 28 до 3 секунд. Федеральный округ требует отдельной проверенной таблицы соответствия субъектов.
3. **Инцидент:** небольшой buffer, Sentinel-2, локальная инфраструктура, детальный рельеф и burn-severity результат Ромы. Глобальное хранилище Sentinel-2/WorldCover не требуется.

`geo/src/kroma_geo/context.py` принимает bbox, Polygon/MultiPolygon GeoJSON и индекс именованных регионов. `scripts/ingestion/historical_firms.py` использует **существующий** `fetch_csv` и VIIRS нормализатор backend, кэширует сырые CSV по source/тайлу/дате, потоково пишет JSONL и SHA manifest, дедуплицирует только текущий временной блок и добавляет небольшой адаптер для SP/MODIS. Поэтому память загрузчика не растёт вместе со всем историческим периодом; размер временного `seen` зависит от 1–5 дней одного источника. Для MODIS отдельное поле `brightness_modis_kelvin`, потому что канал MODIS не является VIIRS I4. Эти исследовательские записи совместимы с `kroma_ml.Observation.from_record`, но **не** с ограниченным `Literal` backend API 1.0; контракт интеграции потребуется согласовать. Секрет API не попадает в manifest. Прямой запуск исторической загрузки требует `NASA_FIRMS_API_KEY`; ключа сейчас нет, поэтому SP/MODIS загрузки не проводились.

`ml/src/kroma_ml/incidents.py` реализует DBSCAN по Haversine и временным соседям с пространственным индексом; параметры `eps_km`, `time_window_hours`, `min_samples` общие для любого AOI. Выход: временные границы, сферический центр, число детекций/спутников, FRP статистика/тренд, радиус охвата и регион при однозначном назначении. Радиус — **приближение размещения детекций**, не периметр и не площадь пожара. Мост между разными пролётами может ошибочно объединять соседние пожары; плотность зависит от сенсора и сезона.

`ml/src/kroma_ml/thermal_memory.py` хранит только занятые клетки равноплощадной сферической сетки и считает историю **строго до времени инцидента**: число детекций, дней/месяцев, FRP, night ratio, sensor diversity, разброс координат, последнее появление и тот же месяц. Сетка — простой независимый от H3 baseline; физическая форма клеток меняется с широтой. Novelty — исследовательский регионально-сезонный ранг, не калиброванная вероятность. Без истории профиль не публикуется.

`geo/src/kroma_geo/context.py` умеет вычислять расстояния до точек/линий/полигонов из локального GeoJSON, включая попадание в охраняемую территорию. `geo/src/kroma_geo/raster.py` умеет читать класс WorldCover по точке и состав по локальному полигону, а также вычислять NDVI/NBR; rasterio — необязательная зависимость, операции проверены на синтетическом растре. Исторический срез OSM на 12.07.2023 получен для небольшого окна Кузбасса (835 объектов, SHA в [manifest](experiments/osm-kuzbass-2023.manifest.json)): из двух пилотных инцидентов один внутри покрытия и имеет расстояние до дороги 0.034 км, другой явно помечен `outside_coverage`, его расстояния оставлены `null`. Внутренний статус — `partial_coverage`: границы запроса, пропущенные relations и неполнота OSM не допускают трактовать отсутствие объекта как доказательство отсутствия на местности. WorldCover COG, ERA5-Land и DEM ещё не подключены, полный impact context отсутствует. `ml/src/kroma_ml/features.py` формирует таблицу входных признаков без целевой переменной и раздельно сохраняет native confidence и brightness VIIRS/MODIS; пилотные JSONL содержат `confidence_inputs` с `null` вместо отсутствующих данных. `priority_score` и `threat_score` реализованы как объяснимые функции от нормированных входов; без подтверждённой confidence и контекстных данных пилотам не присвоены реальные priority scores.

## PILOTS и реальные измерения

Воспроизводимый [конфиг](experiments/pilots.json) задаёт четыре пересечения **AOI-окно ∩ субъект РФ** по полученному слою geoBoundaries; [manifest](experiments/pilots.manifest.json) содержит хэши входа и границ, параметры, число наблюдений/кластеров и runtime. Границы всё ещё требуют ревизии для актуальной статистики. Вход — опубликованный NASA S-NPP NRT **только за 12.07.2023**; полный файл глобальный, после фильтрации:

| AOI-окно ∩ субъект | Тип для проверки | Детекций | DBSCAN incidents | Noise | Время |
| --- | --- | ---: | ---: | ---: | ---: |
| Якутия `RU-SA`, 125–160°E, 56–74°N | удалённый лес | 3442 | 74 | 13 | ≈1.26 с |
| Кузбасс `RU-KEM`, 85–89°E, 52–57°N | промышленный | 10 | 2 | 2 | ≈0.004 с |
| Оренбуржье `RU-ORE`, 50–63°E, 50–55°N | аграрный | 10 | 3 | 2 | ≈0.004 с |
| Красноярский край `RU-KYA`, 85–110°E, 52–73°N | лес | 9 | 2 | 4 | ≈0.003 с |

Время в таблице — локальный однопроцессный запуск с `tracemalloc` **после чтения, фильтрации и назначения регионов**. Полный вызов с Shapely занял около 3 секунд. Python peak allocation для кластеризации пилота Якутии ~1.07 МБ, **не общая память процесса**. Конфиг содержит окно истории 2020–2023, но в локальном входе нет данных до 12.07.2023: `historical_observations=0`, Thermal Memory = `null` во всех четырёх пилотах. В промышленном, аграрном и красноярском окнах выборки слишком малы для вывода о типе аномалий.

Отдельный scale check самого DBSCAN на всех 74 599 глобальных детекциях того же дня: **8321 исследовательский кластер**, 5591 одиночная/noise детекция, **23.09 с** и **15.13 MiB** peak Python allocation с `tracemalloc` на этой машине. Вход уже был загружен в память; это не total RSS и не тест нескольких лет по РФ. Счёт кластеров не имеет смысловой валидации без ground truth.

Чувствительность на якутском окне внутри `RU-SA` (3442 наблюдения): `eps=2/5/10 км`, окно 24 ч, `min_samples=2` даёт **115/74/66** кластеров; при `eps=5`, окне 6 ч — **82**, при `min_samples=3` — **69**. Это показывает существенную зависимость от порога. Fragmentation и merge error пока **не измерены**: нет разметки конкретных пожаров/соседних очагов.

Повторить после установки editable-пакетов `backend`, `geo`, `ml` и получения NASA sample:

```bash
python research/experiments/build_evaluation_cohort.py --download
mkdir -p data/external/boundaries
curl -L https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/9469f09/releaseData/gbOpen/RUS/ADM1/geoBoundaries-RUS-ADM1_simplified.geojson -o data/external/boundaries/geoBoundaries-RUS-ADM1_simplified.geojson
python scripts/prepare/pilot.py --input data/interim/sample_viirs_snpp_071223.jsonl --regions data/external/boundaries/geoBoundaries-RUS-ADM1_simplified.geojson --config research/experiments/pilots.json --output-dir data/processed/pilots --manifest research/experiments/pilots.manifest.json
```

Для настоящего 1–3-летнего fixed пилота использовать `NASA_FIRMS_API_KEY` и `scripts/ingestion/historical_firms.py --help`, отдельно собрать даты события и историю, затем передать `--history` в пилот. Предпочесть SP для завершённых прошлых сезонов, проверив доступность каждой даты. NRT проходит через тот же core pipeline, но не подменяет SP в fixed evaluation.

## LABELS, CONFIDENCE, THREAT, PRIORITY, IMPACT

- **Разметка:** собрать stratified manual subset по региону/типу земли/сезону/сенсору, включить persistent industrial sites как *кандидаты* hard negative, сопоставить открытые отчёты/полигоны и GWIS burned area как слабое подтверждение. Фиксировать источник, дату, уверенность эксперта и статус `verified / weak / unresolved`. Нельзя объявлять burned-area отсутствие отрицательной меткой: мелкие пожары могут пропасть.
- **Confidence:** будущая `P(real wildfire | observations + context)` на incident-level. Признаки: FRP/brightness/native confidence **по сенсору**, день/ночь, размер пикселя, соседи, динамика, новизна, land cover, близость к факелу/промышленности, погода, регион и сезон. Начать с logistic regression после появления проверенных меток; затем сравнить бустинг. Пространственно-временной split по событиям и регионам предотвращает leakage. Главные метрики — precision, recall, PR-AUC и false-positive reduction при recall ≥90/95%. **Сейчас модель не обучалась, эти метрики отсутствуют.**
- **Threat:** потенциальная опасность развития: ветер, топливо/сухость, склон и рост инцидента. Код принимает нормированные входы и даёт раскладку; входные источники не подключены, формула не валидирована.
- **Priority:** срочность внимания оператора: confidence 25%, threat 30%, exposure 25%, accessibility 10%, freshness 10%; возвращает 0–100 и вклад каждого компонента. Вход `confidence` должен быть отдельно валидированной вероятностью; сейчас реальный score не выдаётся. Оценка позже — согласие экспертов в ранжировании и sanity cases, не выдуманная accuracy.
- **Impact context:** ближайшие поселение, дорога, ЛЭП, промышленный объект, аэропорт, ООПТ, land cover, ветер/осадки, рельеф, NDVI. Наличие OSM объекта не означает полное покрытие. Коридор распространения пока **research-only**: ансамбль сценариев по ветру, склону и топливу, uncertainty envelope P50/P80/P95, проверка на известных инцидентах до показа пользователю; это не физический прогноз и не реализовано.
- **Контракт post-fire:** ожидать `incident_id`, geometry/mask reference, `total_burned_area_ha`, `severity_classes`, `area_by_class`, `model_version`, даты pre/post изображения и quality metadata. Никакого конкурирующего burn-severity inference в этом слое нет.

## CLAIMS / RISKS / NEXT

| Claim | Статус | Основание |
| --- | --- | --- |
| FIRMS VIIRS NRT sample ingestion | READY для фиксированного опубликованного примера | 74 599 нормализованных наблюдений, SHA manifest; не live SLA |
| AOI-фильтр и исследовательский clustering | PARTIAL | 4 региона; ошибки группировки не размечены |
| Исторический FIRMS, MODIS/SP | PARTIAL | код, кэш, адаптер и unit tests; реальные запросы блокирует отсутствие ключа |
| Назначение субъекта РФ | PARTIAL | GeoJSON API и synthetic test; реальный актуальный слой не закреплён |
| Thermal Memory / false-positive reduction | RESEARCH / UNSUPPORTED для улучшения качества | алгоритм есть; 0 исторических наблюдений и нет меток |
| Confidence / threat / priority | RESEARCH | контракт и объяснимые формулы; нет валидированной вероятности и контекста |
| Impact context / corridor | PARTIAL / RESEARCH | один исторический OSM extract в Кузбассе и один incident внутри его покрытия; nationwide контекста и прогноза нет |
| Post-fire severity | вне этого слоя | интеграционный контракт; качество Роминого ML здесь не оценивалось |

Основные риски: доступность MAP_KEY и исторических SP; старый/ODbL административный слой; разница VIIRS/MODIS confidence; редкое покрытие спутников и пропуски под облаками; ложное подавление реальных повторных пожаров; отсутствие incident labels; низкая полнота OSM в удалённых местах; региональные смещения и неустойчивость порогов DBSCAN. Следующие пять шагов: (1) получить MAP_KEY и собрать 1–3 года SP для четырёх окон; (2) согласовать актуальный слой субъектов/округов и его лицензию; (3) вручную разметить случаи merge/split и persistent sources; (4) подключить AOI-тайлы land cover, OSM и ERA5-Land и сделать feature matrix; (5) валидировать confidence и операторское ранжирование до интеграции с сервисом.

## COMPETITION TRACK: Active Fire (AF) pixel segmentation

Отдельный трек, официальный датасет организаторов (`data/Мониторинг DATA/train/af/`), не пересекается с продуктовым разделом выше и не трогает Burn Severity (`train/bs/`). Задача: pixel-wise бинарная сегментация активного горения (VIIRS I1–I5 + вспомогательные растры → `1` = природное горение, `0` = всё остальное), метрика — `F1_af`.

### DATA

- `data/Мониторинг DATA/train/af/meta.csv` — 420 chips, единственный `kind=af`. Тест организаторов **не поставлен** (нет `test/`, `baseline/`, `sample_submission.csv`, `metric.py` — только train). Baseline организаторов реализовать было нечем; шаг P6 (section 6) пропущен по объективной причине, задокументировано как известное ограничение.
- Растры: `viirs/{chip}_VIIRS_I1-I5.tif` — 8 каналов float32 `I1,I2,I3,I4,I5,solar_zenith,sensor_zenith,valid` (GDAL band descriptions в тэге, не по имени файла — «I1-I5» в имени вводит в заблуждение). `aux/{chip}_AUX.tif` — 5 каналов float32 `landcover,dem,t2m,rh2m,wind_speed`. `masks/{chip}_MASK.tif` — uint8, `1`=fire, `nodata=255`. Все 256×256, gsd=375м, EPSG 32637/32638 (UTM 37N/38N).
- `meta.csv` — общая схема с BS; для AF пустые: `fire_event_id`, `region`, `date_pre/post`, `s1_date_*`, `cloud_frac`, `landcover_top`, `burn_area_ha`, `sev*_px`. Заполнены: `chip_id, kind, epsg, x_min..y_max, width, height, gsd, acq_datetime, satellite, valid_frac, n_fire_px`.

**OBSERVATION** `fire_event_id` пуст для всех 420 AF-строк (это поле — только для BS в общей схеме).
**DECISION** группировка для split не может идти по `fire_event_id`; использована пространственная плитка `(x_min,y_min,x_max,y_max)` как суррогатный group key (`kroma_ml.af_split.group_key`, с фоллбэком на `fire_event_id`, если он появится в будущей версии данных).

**OBSERVATION** 420 chips = 57 уникальных плиток, повторно снятых в разное время (до 38 chips на одной плитке).
**DECISION** случайный сплит по `chip_id` дал бы прямую утечку локации (один и тот же фон/landcover/DEM в train и val) — обязателен `GroupShuffleSplit` по плитке (`kroma_ml.af_split.train_val_split`, seed=42, проверка непересечения групп через исключение при overlap). 366 train / 54 val chips, доля positive-chips сохраняется (70.5% / 70.4%).

**OBSERVATION** 296/420 (70.5%) chips имеют хотя бы 1 fire-пиксель, 124 — полностью негативные (`n_fire_px=0`).
**DECISION** негативные chips нужны в train как источник «чистого» фона (без объектов) — включены в общий пул для сэмплирования фоновых пикселей, не отбрасываются.

**OBSERVATION** суммарно 9725 fire-пикселей на 27 525 120 пикселей датасета — `fire_frac = 0.000353` (0.035%). Медиана `n_fire_px` по позитивным chips = 21, максимум 243.
**DECISION** экстремальный дисбаланс подтверждён количественно → без sampling/взвешивания задача вырождается в «предсказывай всегда 0» с accuracy 99.96% и F1=0; обучение только на balanced-sampled наборе (все fire + ограниченная выборка фона на chip), `class_weight="balanced"` в LogisticRegression/LightGBM.

**OBSERVATION** нет дубликатов `chip_id`, нет NaN в `width/height/gsd/x_min`, `chip_id` разбирается 1:1 на файлы во всех трёх поддиректориях.
**DECISION** meta.csv не требует чистки перед использованием (не модифицировался).

### EDA (пиксельная выборка: все fire-пиксели + до 500 фоновых/chip, 155 034 строки, `research/experiments/af_eda.py` → `research/experiments/af_pixel_sample.pkl`)

**OBSERVATION** `I4`: fire mean=341.4K (std 8.6) vs bg mean=301.5K (std 11.8), `I5`: fire 301.4K vs bg 289.5K, `I4-I5`: fire mean=40.1 vs bg mean=12.0. Разделение сильное, но диапазоны заметно пересекаются (fire min I4=319, bg max I4=349).
**DECISION** сырых `I4`/`I5`/`I4-I5` недостаточно для точного порога — нужен контекстный (locally-relative) сигнал, не только абсолютный.

**OBSERVATION** контекстная аномалия `I4 - local_median(I4, window)` разделяет классы на порядок сильнее сырых каналов: при `window=7` fire mean=28.3 (std 13.5) vs bg mean=-0.21 (std 2.9); аналогично для `(I4-I5) - local_median(I4-I5)`. Разделение растёт с окном (3→11), но выходит на плато к 7–11.
**DECISION** контекстные thermal-признаки (`I4_minus_localmed_*`, `D_minus_localmed_*`) — главные фичи и для physics-baseline, и для ML; `window=7` выбран как рабочий компромисс (сопоставимое разделение с 11, дешевле считать).

**OBSERVATION** `I1`/`I2` (видимый/NIR) у fire ниже и с намного меньшим разбросом (std 0.03–0.05), чем у bg (std 0.12–0.14, max до 1.18–1.25) — у фона тяжёлый хвост ярких пикселей (glint/облака/снег). `I3` почти не различает классы (fire mean 0.179 vs bg 0.166).
**DECISION** `I3` не дал независимого сигнала для fire/non-fire в этой выборке — оставлен в фиче-стеке как дешёвый context-канал, но не как отдельный физический гейт в baseline; не подтверждено, что он специфично ловит solar-glint негативы (гипотеза раздела 3 не подтвердилась на этих данных).

**OBSERVATION** `aux_rh2m` (влажность) fire mean=32.5% vs bg mean=38.5%; `aux_wind_speed` fire mean=5.64 vs bg 4.83 м/с — оба в физически ожидаемую сторону (суше и ветреннее у огня).
**DECISION** влажность/ветер включены в фиче-группу `weather`, проверены в абляции (см. ниже) — вклад в F1 у ML почти нулевой при уже сильных thermal-признаках, оставлены как дешёвые доп. фичи, не как отдельный физический гейт.

**OBSERVATION** `aux_landcover` (числовой код) отличается по распределению (fire median=30 vs bg median=40), но без справочника классов интерпретация кода невозможна — организаторы не поставили легенду классов landcover.
**DECISION** landcover использован как сырой числовой признак для ML (полезен как категориальный split-фактор для LightGBM без интерпретации), но error-analysis по классам ландшафта (раздел 18) не проведён — нет карты кодов, зафиксировано как ограничение.

**OBSERVATION** насыщение `I4` (≥367K, типичный VIIRS saturation) не встретилось ни разу — max fire I4 = 358.2K.
**DECISION** гейт на насыщение не нужен, из физического baseline исключён (упрощение).

**OBSERVATION** сдвиг между спутниками умеренный: `I4` fire mean — SNPP 341.5K, NOAA-20 340.8K, NOAA-21 347.0K (последний на выборке всего 281 fire-пикселя из 17 chips — высокая дисперсия оценки).
**DECISION** sensor id как отдельная фича не добавлен — искажение того же порядка, что и шум от малой выборки NOAA-21; при появлении большего числа NOAA-21 chips стоит перепроверить.

### VALIDATION

`kroma_ml.af_split.train_val_split` — `GroupShuffleSplit(test_size=0.2, seed=42)` по плиточному group key, с жёсткой проверкой отсутствия пересечения групп (raise при overlap). Тест `tests/ml/test_af_pipeline.py::test_split_has_no_group_leakage` проверяет это на каждом прогоне. 366 train / 54 val chips.

### BASELINE ОРГАНИЗАТОРОВ

Не поставлен в `data/Мониторинг DATA/` (только train-данные и AOI-полигон, без test/baseline/metric/sample_submission). Секция 6 пропущена, зафиксировано как ограничение данных, не как невыполненный шаг.

### PHYSICS-AWARE BASELINE (`kroma_ml.af_physics`, `research/experiments/af_physics_baseline.py`)

Правило: `I4 > i4_min AND (I4-I5) > diff_min AND (I4 - local_median(I4, 7)) > anom_min`. Пороги подобраны grid search'ем по train (2940 комбинаций), подтверждены на val.

| Метрика | Train (тюнинг) | Val (held-out) |
| --- | ---: | ---: |
| precision | 0.9336 | 0.9434 |
| recall | 0.8996 | 0.8949 |
| **F1_af** | **0.9163** | **0.9185** |

Лучшие параметры: `i4_min=330K, diff_min=24K, anom_min=0` (окно 7×7). Val ≈ train — переобучения порогов нет.

**OBSERVATION** `anom_min` сошёлся к границе сетки (0 у первой сетки, −10 у уточнённой) — контекстный гейт не улучшает F1 сверх уже заданных `I4_min`/`diff_min`.
**DECISION** физический жёсткий threshold на `I4`+`I4-I5` уже неявно требует локальной тепловой аномалии (фон редко даёт `I4>330 & I4-I5>24` без реального горения) — третий гейт избыточен для этого baseline, оставлен в API с default 0 (не мешает, но и не помогает).

Инференс: 1.47 мс/chip (54 chips за 0.079с) — практически бесплатный.

### FEATURE PIPELINE (`kroma_ml.af_features`)

39 признаков на пиксель: raw I1–I5, `I4-I5`, углы, 5 aux-каналов, + для I4 и I4-I5 — local median/std/anomaly на окнах {3,5,7,11}, + I3 local median/anomaly на окне 7. Реализовано через `scipy.ndimage.median_filter/uniform_filter`, единая точка входа `chip_feature_stack`, с `lru_cache`-обёрткой `cached_feature_stack` для повторных экспериментов на одних и тех же chips. NaN/inf от invalid-пикселей и краевых эффектов фильтров санитизируются нулём внутри `chip_feature_stack` (тест `test_feature_stack_has_no_nan_or_inf`).

### ML BASELINE (tabular, `kroma_ml.af_model`, эксперимент `research/experiments/af_ablation.py`)

Сэмплирование: все fire-пиксели chip'а + случайные 400 фоновых/chip (+ hard negatives по мере добавления). LogisticRegression (`class_weight="balanced"`, StandardScaler) и LightGBM (`class_weight="balanced"`, 300 деревьев). Порог всегда подбирается sweep'ом 0.05–0.95 по val (`kroma_ml.af_threshold.sweep`).

### ABLATION TABLE (val, F1_af, порог подобран на val)

| # | Эксперимент | Precision | Recall | F1 | train, с | инференс, мс/chip |
| - | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | organizer baseline | — | — | — | — | не поставлен |
| 2 | physics baseline (I4, I4-I5, anomaly) | 0.9434 | 0.8949 | **0.9185** | — | 1.5 |
| 3 | ML raw channels (I1-I5), LogReg | 0.7271 | 0.9970 | 0.8409 | 109.8 | 302 |
| 4 | + thermal contextual, LogReg | 0.6895 | 0.9985 | 0.8157 | 5.2 | 23 |
| 5 | + landcover, LogReg | 0.6878 | 0.9992 | 0.8148 | 4.4 | 23 |
| 6 | + weather (dem/t2m/rh2m/wind), LogReg | 0.6963 | 1.0000 | 0.8210 | 4.2 | 21 |
| 7 | + angles (solar/sensor zenith), LogReg (=full features) | 0.6901 | 1.0000 | 0.8167 | 4.4 | 23 |
| 8 | full features, LightGBM | 0.7883 | 0.9992 | 0.8813 | 5.1 | 88 |
| 9 | + hard-negative mining (out-of-fold, 3-fold GroupKFold) | 0.9423 | 0.9758 | **0.9588** | 6.2 | 96 |
| 10 | + threshold re-tuning (finer grid 0.3–0.99) | 0.9470 | 0.9728 | **0.9597** | — | — |
| 11 | + post-processing (min connected component ≥2) | 0.9534 | 0.8050 | 0.8730 | — | — |

**Лучшая конфигурация: #10, LightGBM + full features + out-of-fold hard-negative mining, F1_af = 0.9597 на held-out val.** Прирост над physics baseline: +0.041 F1.

### U-Net и ансамбль: тот же spatial validation

Сохранённые эксперименты используют тот же `GroupShuffleSplit(seed=42)`: 366 train / 54 val чипа, что и LightGBM. Проверены ID validation, точное совпадение масок и воспроизведение карты вероятностей лучшего checkpoint на CPU (максимальное отличие первого чипа менее `1e-6`). PyTorch 2.14.0 на Apple Silicon; MPS доступен вне ограниченного процесса и использован для дообучения D. Все модели компактные, `base=16`, ~0.48–0.51 млн параметров. У старых запусков сохранились итоговые метрики и карты только лучшего checkpoint, но не поэпохальный журнал/early-stopping; их эпохи нельзя ретроспективно восстановить. Для исправленного D журнал 8 epoch есть в выполненном запуске, лучший вес выбран по val loss.

| MODEL | FEATURES | LOSS | PRECISION | RECALL | F1 | THRESHOLD | TRAIN RUNTIME |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| Physics baseline | I4, I4-I5, local anomaly | rule | 0.9434 | 0.8949 | 0.9185 | 330 K / 24 K | — |
| LightGBM, исходный best | 39 + OOF hard negatives | balanced logloss | 0.9470 | 0.9728 | 0.9597 | 0.92 | сохранённая модель |
| LightGBM, finer threshold | те же | то же | 0.9490 | 0.9713 | 0.9600 | 0.935 | без переобучения |
| U-Net A | I1–I5 | BCE + Dice | 0.7692 | 0.7029 | 0.7346 | 0.50 | 253.4 с |
| U-Net A | I1–I5 | Focal | 0.0005 | 0.9426 | 0.0011 | 0.05 | 252.4 с |
| U-Net A | I1–I5 | Focal Tversky | 0 | 0 | 0 | 0.05 | 246.1 с |
| U-Net B | I1–I5, I4-I5 | BCE + Dice | 0.8572 | 0.8670 | 0.8621 | 0.45 | 212.4 с |
| U-Net C | B + 2 local anomalies | BCE + Dice | 0.8400 | 0.8768 | 0.8580 | 0.80 | 267.1 с |
| U-Net D corrected | C + 8 aux/valid | BCE + Dice | 0.8277 | 0.8753 | 0.8508 | 0.992 | 179.7 с |
| U-Net B + hard negatives | B | BCE + Dice | 0.8666 | 0.8987 | 0.8824 | 0.05 | 85.5 с дообучение |
| ResUNet B, сохранённый best | B | BCE + Dice | 0.8980 | 0.9380 | 0.9176 | 0.635 | 160.7 с |
| Ансамбль `0.9·LightGBM + 0.1·ResUNet` | обе probability maps | — | 0.9506 | 0.9735 | **0.9619** | 0.89 | без обучения |

Для A–C и вспомогательных старых запусков приведён исходный coarse threshold sweep. Отдельные Focal/Focal Tversky запуски B–D также лежат в [результатах](experiments/af_unet_results.json); они уступили BCE + Dice. D переобучен, потому что прежняя нормализация ошибочно z-score'ила код landcover как непрерывную физическую величину. Теперь continuous-каналы получают статистику **только train**, `valid` остаётся 0/1, landcover ограничен 0–1 без mean/std. Маска 255 исключается из loss и метрик; в текущих 420 файлах 255 не встретился, защита проверена синтетическим тестом. Исправленный D выше прежних 0.8298, но ниже B. Порог 0.992 найден дополнительным sweep в верхнем диапазоне 0.95–0.999.

Старый лучший U-Net на самостоятельном threshold sweep получил F1 0.9176. Ансамбль на тех же валидных пикселях дал +0.0019 F1 к заново настроенному LightGBM и +0.0022 к исходному F1 0.9597. Пересечения ошибок: FP обоих 52, FP только LightGBM 17, FP только U-Net 89; FN обоих 12, FN только LightGBM 26, FN только U-Net 70. Вес и порог выбраны на тех же 54 val чипах, поэтому этот локальный прирост проверен ниже на других пространственных группах.

### 3-fold group CV

[Эксперимент](experiments/af_group_cv.py) сохранил исходный 366/54 split без изменений и отдельно построил 3 `GroupKFold` по тем же пространственным плиткам: в каждом 280 train и 140 val чипов. В каждом outer train LightGBM заново получил OOF hard negatives через внутренний 3-fold GroupKFold; ResUNet B заново получил train-only нормализацию и до 8 epoch. Внутри каждого val подобран порог; `alpha=0.9` ансамбля **зафиксирован до CV** по одиночному validation. [Полный manifest](experiments/af_group_cv_results.json) содержит все precision, recall, F1 и пороги.

| Модель | Fold 1 F1 | Fold 2 F1 | Fold 3 F1 | Mean F1 | Std F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| LightGBM + OOF hard negatives | 0.9687 | 0.9656 | 0.9579 | **0.9641** | 0.0056 |
| ResUNet B | 0.8985 | 0.9173 | 0.9051 | 0.9070 | 0.0095 |
| Ансамбль, alpha 0.9 | 0.9685 | 0.9656 | 0.9576 | 0.9639 | 0.0056 |

Ансамбль уступил LightGBM на 0.0002 среднего F1 и не выиграл ни один фолд; подбор alpha отдельно на каждом фолде выбирал 1.0, 0.9, 1.0 соответственно, но это дополнительный выбор по тем же val меткам и не является отдельной оценкой качества. **Решение: текущий лучший AF predictor — LightGBM; ансамбль и U-Net в общий inference не подключать.** 3-fold CV является проверкой устойчивости выбора модели, а не независимой test-оценкой: архитектура и alpha прежде выбирались с помощью исходного val, а пороги каждого фолда также настроены на его val. Пороги LightGBM по фолдам 0.77/0.85/0.765 показывают, что калибровку для внешнего test надо проверять отдельно.

**OBSERVATION** сырые/несколько добавленных ML-фич (#3–7, LogReg) хуже физического baseline (0.81–0.84 против 0.92) при случайном negative sampling — recall почти 1.0, но precision 0.69–0.73, то есть модель заливает фон ложными срабатываниями.
**DECISION** случайно засэмплированный фон не репрезентативен для реального распределения негативов (не содержит «трудных» похожих-на-огонь пикселей) — обучение только на random negatives системно недооценивает precision. Простое добавление фич (landcover/weather/angles) эту проблему не решает.

**OBSERVATION** переход LogReg→LightGBM на тех же фичах и той же random-negative выборке уже даёт +0.06 F1 (0.817→0.881), но precision всё ещё низкая (0.79).
**DECISION** нелинейная модель лучше использует контекстные признаки, но проблема репрезентативности негативов первична — не решается только выбором модели.

**OBSERVATION** hard-negative mining (out-of-fold FP, top-20 по confidence на chip, 3-fold GroupKFold без утечки в val) дал главный прирост эксперимента: F1 0.881→0.959 (+0.078), почти весь за счёт precision (0.79→0.94) при небольшой потере recall (0.999→0.976).
**DECISION** это самый эффективный из проверенных рычагов — зафиксирован как обязательный шаг финального пайплайна, а не опциональная доработка.

**OBSERVATION** post-processing по размеру связных компонент **портит** метрику: уже `min_size=2` роняет F1 с 0.959 до 0.873 (recall 0.976→0.805), дальше только хуже (`min_size=4` → F1 0.60).
**DECISION** подтверждена гипотеза ТЗ — многие реальные fire-детекции в этом датасете односвязны (1 пиксель). Морфологическая фильтрация по размеру компонент **не применяется** в финальном пайплайне.

### SATELLITE GENERALIZATION

Val-выборка по спутникам: SNPP (37 chips) F1=0.9496, NOAA-20 (16 chips) F1=0.9753, NOAA-21 — только 1 chip в val (F1 недостоверен на такой выборке, не интерпретируется). Существенного систематического проседания по сенсору не выявлено на доступных данных; sensor-id как фича не добавлялся (недостаточно оснований).

### LANDCOVER GENERALIZATION

Не выполнено — организаторы не предоставили расшифровку числовых кодов `aux_landcover`, группировка в forest/cropland/... без легенды была бы гаданием. Зафиксировано как открытый пункт.

### DATA LEAKAGE

Split по пространственной плитке исключает попадание одной и той же локации в train и val. Hard-negative mining использует only out-of-fold предсказания на train (3-fold GroupKFold) — val не участвует в отборе negatives или обучении весов модели. Но выбор конфигурации U-Net, alpha ансамбля и threshold использует тот же val, на котором опубликован F1; это источник оптимистического смещения, даже без пересечения пространственных групп. FIRMS/внешние lookup, координаты и даты не использовались как признаки модели (только как debug/EDA группировка).

### СКОРОСТЬ

Physics baseline: ~1.5 мс/chip в раннем измерении. Новый замер на 10 val чипах текущего хоста без кэша: подготовка 39 LightGBM признаков 276.1 мс/chip, `predict_proba` 196.5 мс/chip (сумма 472.6 мс/chip). Для ResUNet B: подготовка 6 каналов 2.1 мс/chip на CPU, модель 53.4 мс/chip на CPU или 4.8 мс/chip на MPS (после прогрева, 10 чипов, синхронизация MPS). Арифметическое смешивание готовых карт ~0.02 мс/chip без учёта передачи между устройствами. Старые 90–100 мс/chip относятся к иному прогону/условиям кэша и не подтверждены новым холодным замером. На инфраструктуре организаторов MPS может отсутствовать, поэтому U-Net интерфейс имеет CPU fallback.

### ЧТО НЕ СДЕЛАНО (в этой итерации)

- Независимый test организаторов отсутствует; настройка моделей, alpha и порогов выполнена на одном validation split, поэтому улучшение ансамбля требует проверки по другим группам.
- Landcover error-analysis по классам (нет легенды кодов от организаторов).
- Внешние historical AF данные — не привлекались, официального датасета хватило для F1>0.95, задача явно не в приоритете по ТЗ.

### FILES (AF track)

- `ml/src/kroma_ml/af_data.py`, `af_features.py`, `af_physics.py`, `af_model.py`, `af_metrics.py`, `af_threshold.py`, `af_postprocess.py`, `af_split.py`, `af_infer.py`, `af_torch_data.py`, `af_losses.py`, `af_unet.py` — AF модули; `AFUNetPredictor.predict_chip(...)` выдаёт бинарную маску 256×256 без изменения общего `inference.py`.
- `research/experiments/af_eda.py`, `af_physics_baseline.py`, `af_ablation.py`, `af_final_model.py`, `af_unet_experiments.py`, `af_ensemble.py`, `af_group_cv.py` — воспроизводимые эксперименты; checkpoints/карты вероятностей сохранены локально.
- `tests/ml/test_af_pipeline.py` — 22 прошедших AF теста, `skipif` на отсутствие официального датасета.
- `ml/pyproject.toml` — добавлены зависимости `pandas`, `scikit-learn`, `scipy`, `tifffile`, `joblib`, `lightgbm`, `kroma-geo`.

### NEXT (5 задач)

1. Получить независимый test организаторов и измерить F1 LightGBM без повторного выбора модели по этим меткам.
2. Проверить перенос порога на невидимые плитки через вложенную калибровку внутри train: CV пороги 0.765–0.85 заметно отличаются от 0.92 исходного артефакта.
3. Получить легенду `aux_landcover`, провести FP/FN анализ по типам поверхности и затем подготовить интеграцию уже выбранного `AFPredictor` в общий интерфейс без изменения Burn Severity.

## OFFICIAL TEST

`data/test/` содержит официальный test: 180 AF chips (`data/test/af/`), 89 BS chips (`data/test/bs/`), `meta.csv`, `sample_submission.csv` (447 строк = 180×1 + 89×3, формат `chip_id,class_id,rle` подтверждён точным сравнением с `research/experiments/af_official_test.py audit`, results — `artifacts/af_test_audit.json`). Ground truth в test отсутствует — F1/IoU на test не считается нигде в пайплайне.

### AF VALIDITY BUG И ИСПРАВЛЕНИЕ

**OBSERVATION.** Старая `valid_mask` требовала finite для всех VIIRS-каналов. У 127 train chips и 69 test chips отсутствуют I1–I3 при доступных I4/I5 (thermal), т.к. модель фактически не зависит от I1–I3 напрямую (features строятся из I4/I5/I3, но I1/I2 не входят в 39-канальный feature stack ML-модели). Старое правило превращало такие chips полностью invalid, теряя реальные thermal-детекции.

**DECISION.** `valid_mask` (`ml/src/kroma_ml/af_data.py`) теперь требует только: VIIRS `valid==1`, finite I4 и I5, `mask != 255`. Пиксели с невалидными I1–I3 остаются valid для AF-задачи; отсутствующие reflective-каналы обнуляются на этапе построения признаков (`np.nan_to_num`, уже было в `af_features.py`).

**RE-VALIDATION (3-fold spatial GroupKFold, тот же split, corrected validity, tag `thermal_valid`):**

| | precision | recall | F1 | threshold |
|---|---|---|---|---|
| fold 1 | 0.9415 | 0.9720 | 0.9565 | 0.84 |
| fold 2 | 0.9436 | 0.9790 | 0.9610 | 0.80 |
| fold 3 | 0.9500 | 0.9668 | 0.9583 | 0.745 |
| **mean ± std** | | | **0.9586 ± 0.0023** | |

Для сравнения: старая (invalidity-искажённая) CV — mean F1 = 0.9641 ± 0.0056. Скорректированная цифра **ниже** (больше валидных, но более разнородных по I1–I3-качеству пикселей включено в оценку) и является честной. Старые числа в разделах выше помечаются superseded этим блоком, без удаления истории.

### AF OOF CALIBRATION

Threshold зафиксирован на pooled out-of-fold train-предсказаниях (train-only, test не участвует): **threshold = 0.765, OOF precision = 0.9423, OOF recall = 0.9736, OOF F1 = 0.9577** (`research/experiments/af_oof_calibration.json`, `af_official_test.py calibrate`).

### AF FINAL MODEL (full train)

LightGBM, 39 признаков, hard-negative mining (leakage-safe, OOF на train), обучен на всех 420 train chips (`research/experiments/af_fulltrain_model.joblib`, `af_fulltrain_manifest.json`). 180 703 обучающих пикселя, 9 725 положительных, 276 chips дали hard negatives. Runtime полного обучения: 274 с.

### AF TEST INFERENCE

180 test chips, threshold=0.765, **детерминированность подтверждена** (3 прогона дают идентичный sha256 маски). 134 chips с предсказанным огнём, 46 пустых, 3 977 положительных пикселей суммарно (0.034% от всех валидных пикселей — на том же порядке, что и train-позитивы, явного сдвига positive-rate не выявлено). Согласие с physics-baseline: 3 041 пиксель пересечение, 936 только LightGBM, 299 только physics — умеренное расхождение, ожидаемо для ML-модели с контекстными признаками. `artifacts/af_test_manifest.json`, `artifacts/af_test_chips.csv`.

## BS BASELINE (воспроизведение ноутбука Ромы)

**Источник:** `cosmohack_dataset.ipynb`. Файл сплита (`bs_temporal_split_train_2019_2023_val_2024.csv`) и чекпоинты (`best_temporal_comboloss_sampler_dnbr_landcoverOnehot.pt`, `weighted_comboloss_sampler.pt`), на которые ссылается notebook, отсутствуют на диске — notebook сам по себе не воспроизводим "как есть". Перенесена рабочая часть (AttentionUNet, ConvBlock/UpConvBlock/AttentionBlock, CombinedLoss=CE+Dice, SCL-based valid mask, IGNORE_INDEX=255) в `ml/src/kroma_ml/bs_*.py`, split заменён на grouped `train_val_split` по `fire_event_id` (у BS train fire_event_id заполнен на 100%, 224/224 уникальны — leakage невозможен по построению).

Активная конфигурация каналов (config B, как у Ромы): pre+post B4/B8A/B11/B12 + RdNBR = 9 каналов. `BS_CONFIGS` в `bs_features.py` также определяет A (post-only), C (+dNDVI/dNBR1/dNBR2), D (+Sentinel-1 ΔVV/ΔVH), E (+dem/slope/landcover) для будущих ablations (спецификация п.18, не запущены в этой итерации).

**Результат (val, grouped split, 15 эпох, base=32, CE+Dice, SGD+cosine):**

| metric | value |
|---|---|
| IoU class 0 (background) | 0.848 |
| IoU class 1 (low) | 0.196 |
| IoU class 2 (moderate) | 0.462 |
| IoU class 3 (high) | 0.579 |
| **IoU_burn** | **0.414** |
| **mIoU_severity (1-3)** | **0.412** |
| BS_score (0.35×IoU_burn+0.30×mIoU_severity) | 0.269 |

**OBSERVATION.** Class 1 (low severity) IoU заметно ниже 2/3 — подтверждает описанную Ромой проблему background↔low-severity confusion (спец. п.14). Не устранялось в этой итерации (baseline reproduction only).

`research/experiments/bs_baseline.py`, `bs_baseline_model.pt`, `bs_baseline_results.json`.

### BS TEST INFERENCE

89 test chips, mean 542 мс/chip (CPU). Все 89 chips получили хоть один сгоревший пиксель (диагностика, не подгонка — модель отдельно не калибровалась под test). `artifacts/bs_submission.csv`, `artifacts/bs_test_manifest.json`.

## SUBMISSIONS

**submission_v001.csv** (`artifacts/submissions/`): AF final LightGBM (threshold 0.765) + BS baseline AttentionUNet (config B). 447 строк, validator PASSED (row count, column names, exact pair set и порядок, no duplicates, no NaN, RLE roundtrip на реальных test-размерах, AF class_id==1 только, BS classes 1/2/3 без пересечения, никаких утечек 255). Манифест: `artifacts/submissions/submission_v001.json` (включает sha256, локальные CV/OOF метрики AF и BS, `public_score`/`public_f1_af`/`public_iou_burn`/`public_miou_severity` = null до фактической загрузки на платформу).

## LEADERBOARD

Не заполнено — пользователь ещё не загрузил submission на платформу. Поля `public_*` в манифесте submission_v001 будут обновлены вручную после результата.

## SPEED

| stage | time |
|---|---|
| AF test inference | ~380 мс/chip (feature build доминирует, 52 c / 180 chips = features stage) |
| BS test inference | ~542 мс/chip (CPU, AttentionUNet base=32, 512×512×9) |
| AF full retrain | 274 с (420 chips, hard-negative mining включено) |
| BS train (15 эпох) | 819 с (179 train chips, CPU/MPS) |

## RISKS

- BS baseline обучен на одном grouped split (179/45), не на K-fold — доверительный интервал mIoU_severity неизвестен, возможен переобучение под конкретный сплит.
- BS-модель предсказывает burn на 100% test chips — не проверено, является ли это реалистичным или систематическим смещением (SCL/valid mask отличия test vs train не проаудированы так же тщательно, как для AF).
- AF corrected-validity CV (0.9586) использует тот же val для выбора threshold, что и раньше — оптимистическое смещение малое, но не равно нулю.
- U-Net/ResUNet и ensemble для AF остаются хуже LightGBM даже после validity fix (не переобучались в этой итерации, ожидается тот же результат).

## LEADERBOARD V001 = 0.5526

Локально ожидаемый score перед submission ≈ 0.35×0.958(CV F1_af) + 0.269(BS-часть) ≈ 0.604. Public дал **0.5526**, разрыв ≈ 0.052. Ниже — forensic audit источника разрыва.

### P0. FORENSIC AUDIT V001 — PASS

`submission_v001.csv` пересобран программно из сохранённых `af_submission.csv` + `bs_submission.csv` и **побайтово совпал** с уже загруженным файлом (тот же sha256 `e275d087...`). 447 строк = 180 AF + 267 BS (89×3), pair-set точно совпадает с `sample_submission.csv`, дублей/NaN/утечек 255 нет, BS-классы не пересекаются (все проверки — `build_submission.py validate()`).

### P0/3. RLE — ПЕРЕПРОВЕРЕНО С НУЛЯ

Независимая reference-реализация (без использования production-кода) на synthetic масках: top-left/top-right/bottom-left/bottom-right pixel, horizontal run, vertical run, два разрозненных run, empty, full — **все 9 случаев совпали побитово** с `kroma_ml.submission.encode_rle` (row-major/C-order flatten, 1-based start, `start length` пары, encode→decode round-trip точный). Официального эталонного RLE-примера в документации кейса нет (в `sample_submission.csv` все строки пустые), в критериях оценки только текстовое требование "RLE декодируется без ошибок, индексы не выходят за пределы чипа, маски не пересекаются" — что уже проверяется валидатором. **RLE признан не источником разрыва.**

### P0/4. BS CLASS MAPPING — PASS

Путь `pred(argmax)==1/2/3 → class_id=1/2/3`, `pred==0` не экспортируется, 255 никогда не попадает в submission — подтверждено кодом (`bs_test_infer.py`, `multiclass_to_binary_rles`) и валидатором (`build_submission.py`: `if 255 in mask: raise`). Маски классов 1/2/3 внутри чипа не пересекаются по построению (`argmax` даёт один класс на пиксель).

### P2/11/12. НАЙДЕНА ГЛАВНАЯ ПРИЧИНА: BS BURN OVER-PREDICTION

**OBSERVATION 1 (100%-burn на test).** На test все 89 BS chips получили хоть один "горелый" пиксель, средняя предсказанная burn-доля **40.1%** чипа. Официальная train-статистика (`sev1_px+sev2_px+sev3_px` из `meta.csv`) даёт среднюю burn-долю всего **10.1%** (медиана 7.5%). На **validation** (та же модель, тот же split) предсказанная burn-доля тоже завышена — **24.2%** против истинных **11.5%** — то есть проблема существует уже in-distribution, до какого-либо test-специфичного сдвига.

**OBSERVATION 2 (confusion matrix, val, pooled по всем валидным пикселям).**

| true \ pred | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| 0 (background) | 85.1% | **11.2%** | 2.9% | 0.8% |
| 1 (low) | 8.4% | 77.5% | 13.7% | 0.5% |
| 2 (moderate) | 0.4% | 9.2% | 84.3% | 6.1% |
| 3 (high) | 0.0% | 0.1% | 16.3% | 83.5% |

Класс 0 (фон) на порядки многочисленнее остальных (6.1M пикселей против 281K/335K/183K), поэтому даже 11.2% утечки 0→1 создаёт 803K лишних "low severity" пикселей — больше всей истинной популяции класса 1. Это и есть **class 0↔1 confusion**, главный failure mode, предсказанный в задании.

**ROOT CAUSE.** `calculate_class_weights` (унаследовано из ноутбука Ромы, `kroma_ml.bs_torch_data.class_weights`) — наивная инверсия частоты класса (`counts.sum() / (4 × counts)`), нормированная на среднее. Такое взвешивание сильно завышает вес редких классов (1/2/3) в CrossEntropy, что толкает модель к систематическому over-prediction burn-классов — именно тот "тупой class weight", о котором предупреждает задание.

**OBSERVATION 3 (SCL/ignore audit, п.12).** Отдельно найдено расхождение между нашей SCL-derived valid_mask (Роминой логики: invalid если ЛЮБОЙ из {pre, post} SCL ∈ {nodata, saturated, cloud shadow, cloud medium/high, cirrus}) и официальным `meta.valid_frac`: корреляция на выборке из 60 train chips всего **0.33**, есть чипы, где официально valid_frac=0.94, а наша маска даёт 0% (`BS_tr_000024`: pre-снимок полностью в облаках, post — чистый; наша AND-по-облакам-между-pre/post логика убивает весь чип, хотя официально он на 94% valid). В среднем по train наша логика помечает invalid **28%** пикселей (mean valid_frac=0.717), у 12/224 chips (5.4%) valid_frac≈0 — вероятно чрезмерно строго.

**SCL-STRATEGY EXPERIMENT (п.13, grouped split, тот же seed).** Переобучили с "loose" SCL (invalid только nodata+saturated, без cloud/shadow/cirrus): результат **не лучше** — bs_score=0.248 (собственная маска) / 0.267 (при оценке под старой строгой маской, для честного сравнения) против исходных 0.269. **Вывод: SCL-агрессивность не является главной причиной разрыва** (расхождение с `meta.valid_frac` реально, задокументировано как открытый риск, но не устраняет burn over-prediction) — не тащить это изменение дальше (`research/experiments/bs_baseline_results_loose_scl.json`, модель `bs_baseline_model_loose_scl.pt`).

### P8/22. TWO-STAGE CALIBRATION — ПОДТВЕРЖДЁННОЕ УЛУЧШЕНИЕ

Пофиксили logit bias для классов 1/2/3 (без переобучения) coordinate-descent'ом на val, оптимизируя напрямую `BSScore = 0.35×IoU_burn + 0.30×mIoU_severity` (не mIoU со фоном, не F1):

| | baseline | calibrated (bias 0,-1.6,-1.8,-1.6) |
|---|---|---|
| IoU class 0 | 0.848 | 0.933 |
| IoU class 1 | 0.196 | 0.297 |
| IoU class 2 | 0.462 | 0.510 |
| IoU class 3 | 0.579 | 0.619 |
| **IoU_burn** | **0.414** | **0.571** |
| **mIoU_severity** | **0.412** | **0.475** |
| **bs_score** | **0.269** | **0.342** |

На test та же калибровка сократила суммарные предсказанные burn-пиксели с 9.35M до 4.76M (burn-доля с 40% до ~20%, гораздо ближе к train-статистике 10%). `research/experiments/bs_calibrate.py`, `bs_calibration.json`, `bs_calibrated_results.json`.

## SUBMISSIONS (обновление)

**submission_v002.csv** (`artifacts/submissions/`): AF без изменений (тот же `af_submission.csv`, что в v001), BS = та же Roman-архитектура + logit-bias калибровка. Validator PASS, 447 строк, sha256 `da25702c...`. Манифест `submission_v002.json`.

## DIAGNOSTIC (AF-only / BS-only, п.5/26)

Подготовлены, **не загружены**: `artifacts/submissions/diagnostic/diagnostic_af_only.csv` (AF=v001, BS=all-empty) и `diagnostic_bs_only.csv` (AF=all-empty, BS=v001). Пустые RLE прошли собственный roundtrip. Манифест `artifacts/submissions/diagnostic/manifest.json`. Пользователь сам решает, тратить ли на них submission-попытки — если платформа даёт ненулевой score на all-empty части, это дополнительно подтвердит/опровергнёт гипотезу о вкладе AF vs BS.

## AF SUBGROUP VALIDATION (п.6, corrected validity OOF)

| subgroup | n chips | precision | recall | F1 (@0.765) |
|---|---|---|---|---|
| missing I1–I3 (`i1_finite_frac<0.05`) | 127 | 0.905 | 0.968 | **0.9355** |
| I1–I3 present (`i1_finite_frac>0.95`) | 147 | 0.945 | 0.983 | **0.9636** |

Разрыв ≈0.028 F1 реален, но умеренный (обе подгруппы >0.93) и уже отражён в честной 3-fold CV (0.9586) — 127/420≈30% train chips в этом режиме, соотносимо с 69/180≈38% на test. **Решение: thermal-only expert не обучать в этой итерации** — разрыв недостаточно велик, чтобы оправдать отдельную модель/routing (см. п.28 задания: время отдаётся BS). AF threshold=0.765 сохранён без изменений.

## EXPERIMENTS TABLE (эта итерация)

| id | что изменилось | IoU_burn | mIoU_severity | bs_score | вывод |
|---|---|---|---|---|---|
| bs_baseline (Roman, strict SCL) | референс, v001 | 0.414 | 0.412 | 0.269 | baseline, зафиксирован, не перезаписывается (`bs_roman_baseline_*`) |
| bs_loose_scl | invalid только nodata+saturated | 0.378 (own) / 0.398 (strict-mask) | 0.385 / 0.427 | 0.248 / 0.267 | не лучше — отклонено |
| bs_calibrated | + logit bias (0,-1.6,-1.8,-1.6) поверх baseline | **0.571** | **0.475** | **0.342** | принято → v002 |

## BEST BS (текущий)

IoU_burn=0.571, IoU_1/2/3=0.297/0.510/0.619, mIoU_severity=0.475, bs_score=0.342 (val, single grouped split, 45 chips — без K-fold CI, см. RISKS).

## EXPECTED NEXT (3 самых перспективных шага) — SUPERSEDED, см. LEADERBOARD V002 ниже

1. ~~BS GroupKFold + hierarchical burn/severity head~~ — выполнено, см. ниже.
2. ~~Загрузить v002~~ — выполнено: public 0.6457 (+0.0931 vs v001), подтверждает калибровку как главный источник прироста.
3. ~~BS input ablation~~ — в процессе, см. ниже.

## LEADERBOARD V002 = 0.6457 (+0.0931 vs v001)

Записано в `submission_v002.json` (`public_score_recorded_at`). Единственное отличие от v001 — logit-bias калибровка BS (AF byte-identical). Прирост +0.0931 на leaderboard при локальном приросте bs_score +0.073 (0.269→0.342 на single split) — то же направление и сопоставимая величина, **подтверждает**, что калибровка была главным источником разрыва v001, и что local↔public корреляция для BS в этом диапазоне надёжна (п.47).

### P1/P6. BS GROUP K-FOLD (fire_event_id, 3 fold, 10 эпох, config B, CombinedLoss)

| | IoU_burn | mIoU_severity | BSScore |
|---|---|---|---|
| raw (no calibration) | 0.375 ± 0.026 | 0.336 ± 0.013 | 0.232 ± 0.006 |
| per-fold calibrated | **0.527 ± 0.010** | **0.393 ± 0.017** | **0.302 ± 0.008** |
| OOF pooled + global bias | 0.516 | 0.392 | 0.298 |

Это более честная оценка, чем single-split (0.342) — меньше train-чипов на fold (149 vs 179) и вдвое меньше эпох (10 vs 15) частично объясняют разницу; **0.298–0.302 — рабочий диапазон ожидания для BSScore на новом domain/fold**, а не 0.342. `research/experiments/bs_group_cv_baseline_results.json`.

Замечено: fold 2 эпоха 7 дала `loss=nan` (transient, SGD momentum spike), тренировка продолжилась и метрики фолда не пострадали — не критично, но `torch.nn.utils.clip_grad_norm_` добавлен в последующие эксперименты (`bs_feature_ablation.py`) как профилактика.

### P5/P7. HIERARCHICAL BURN/SEVERITY LOSS — ОТРИЦАТЕЛЬНЫЙ РЕЗУЛЬТАТ

Реализован как единая 4-class softmax голова с `BurnSeverityLoss` (burn-logit через `logsumexp` по severity-каналам + severity CE только на burn-пикселях) — не требует смены архитектуры. Тот же GroupKFold протокол (config B, 10 эпох):

| | IoU_burn | mIoU_severity | BSScore |
|---|---|---|---|
| hierarchical, raw | 0.308 ± 0.014 | 0.314 ± 0.022 | 0.202 ± 0.010 |
| hierarchical, calibrated | 0.395 ± 0.044 | 0.343 ± 0.034 | **0.241 ± 0.025** |

Хуже baseline (0.302±0.008) на всех метриках и с большей дисперсией. **Зафиксировано как отклонённый эксперимент** — не использовать дальше в этой итерации (могла бы помочь с большим числом эпох/литеральными раздельными головами, но приоритет отдан направлениям с уже подтверждённым выигрышем). `research/experiments/bs_group_cv_hierarchical_results.json`.

Найден и исправлен попутный баг в `BurnSeverityLoss`: severity target для IGNORE_INDEX-пикселей (255-1=254) выходил за диапазон классов и падал в `F.cross_entropy` до применения маски — исправлено safe-target паттерном (аналогично `DiceLoss`). Добавлены regression-тесты (`test_hierarchical_loss_handles_ignore_index_and_improves_toward_target`, `test_hierarchical_loss_all_ignored_is_finite`).

### P2. CLASS 0↔1 ERROR BREAKDOWN (baseline calibrated model, single-split val)

**По landcover** (доля background-пикселей, ошибочно предсказанных как class 1):

| код (WorldCover) | тип (по группировке Ромы) | FP rate 0→1 |
|---|---|---|
| 40 | cropland | **3.56%** |
| 30 | grass/moss | 1.75% |
| 10 | forest/shrub | 1.18% |
| 90 | wetland | 0.28% |
| 80/60/50/20 | прочее | 0.18–0.70% |

**По RdNBR-бину** (background-пиксели): резкий скачок FP-rate ровно в зоне `RdNBR ∈ [0.00, 0.10]` — **4.26%** против <0.15% за пределами этой зоны. Это классическая decision-boundary ошибка: слабые, но ненулевые сезонные спектральные изменения (не пожар) в частности на пашне/пастбище (уборка урожая, вспашка) дают тот же знак и малую величину RdNBR, что и слабый burn.

**OHEM-диагностика (keep_ratio=0.4, тот же val).** Hard-40% пикселей: **54.9%** приходится на код 40 (cropland), **32.7%** — код 30 (grass/moss), т.е. 87.6% hard-пикселей — это именно cropland/grassland, не облака/invalid. True-class распределение внутри hard-pool: class 1 доля 7.6% (vs 3.5% overall, ×2.1), class 2 — 6.9% (vs 4.2%, ×1.65). **Вывод: OHEM у Ромы (`keep_ratio=0.4`) корректно концентрируется на background↔weak confusion в cropland/grassland, не на шуме** — п.9/10 задания предупреждал именно об этом риске, риск не подтвердился. Дальнейший OHEM-grid (0.25/0.40/0.60) не запускался в этой итерации (calibration и feature-ablation имели больший ожидаемый ROI на вложенное время).

**Вывод по direction:** главный оставшийся резерв — сделать модели доступным landcover-код как явный input (уже есть в config E) и/или ограничить false burn-triggering именно в зоне низкого положительного RdNBR на cropland/grassland — natural next step, см. FEATURES ниже.

### P8-P10/P12. FEATURE ABLATION И TTA (single grouped split 179/45, 15 эпох, CombinedLoss, calibrated)

| config | каналы | IoU_burn | mIoU_severity | BSScore | вывод |
|---|---|---|---|---|---|
| B (baseline) | S2 pre/post 8 + RdNBR | 0.571 | 0.475 | 0.342 | reference |
| C | + dNDVI, dNBR1, dNBR2 | 0.561 | 0.492 | 0.344 | +0.002, ниже порога +0.01 |
| D | C + Sentinel-1 ΔVV/ΔVH | 0.541 | 0.463 | 0.328 | хуже — не использовать |
| E | D + DEM/slope/landcover (scalar) | 0.536 | 0.448 | 0.322 | хуже — не использовать |

Разброс между single-split запусками сопоставим с разницей между конфигами, поэтому ни одна добавка не считается подтверждённой. Landcover добавлен как скалярный код (не one-hot/embedding) — это ограничение эксперимента, гипотеза "landcover помогает cropland FP" тестом E не опровергнута окончательно. Полный лог C/D/E: `research/experiments/bs_feature_ablation_CDE_15ep.log`.

TTA (baseline model, каждая вариация со своей калибровкой bias на val): none 0.3424 → 2 flips 0.3448 → dihedral-8 0.3476 (+0.005 при 8× стоимости инференса). Ниже порога +0.01, submission из-за этого не создаётся. `research/experiments/bs_tta_results.json`.

Проверка числа эпох (config B, 25 vs 15 эпох, тот же split, calibrated): 0.3478 vs 0.3424 (+0.005, bias 0/-1.6/-1.4/-1.0) — в пределах шума одного split, ниже порога +0.01. Результат: `research/experiments/bs_feature_ablation_B_25ep_results.json`.

### ИТОГ ПЛАТО (single split, calibrated BSScore)

Калибровка дала главный скачок (0.269→0.342, public +0.0931). После неё все проверенные рычаги дают ≤ +0.005: dNBR-индексы +0.002, TTA-8 +0.005, 25 эпох +0.005; Sentinel-1, terrain/landcover, hierarchical loss — хуже baseline. **Submission v003 не создан**: ни одно изменение не прошло порог +0.01, а комбинацию (полное обучение на 224 чипах + 25 эпох + TTA) нельзя проверить локально, потому что нет held-out данных для её калибровки bias.

## ITERATION 3: DATA-CENTRIC BS PIPELINE (`ml/src/kroma_ml/bs_crop.py`, `research/experiments/bs_train.py`)

### Current state audit

Leaderboard: v001 0.5526, v002 0.6457 (только BS logit calibration, AF без изменений). Новый ноутбук Ромы (`cosmohack_dataset (1).ipynb`) содержит лог 100-эпохной OHEM-тренировки (keep_ratio 0.4, без class weights, temporal split val=2024, raw без калибровки): BSScore шумит в диапазоне 0.20–0.35, пик 0.351 на эпохе 60, финал 0.323; предсказанная burn-доля 7–8% против истинных 9.2% (без over-prediction). Чекпоинта и split-файла на диске нет, поэтому на общем evaluator оценить эту модель нельзя; в лог смотреть только как независимое подтверждение, что OHEM без class weights не переливает burn.

### SCL audit (доля пикселей каждого класса, теряемая при ignore)

| ignore-правило | class 0 | class 1 | class 2 | class 3 |
|---|---|---|---|---|
| strict (старая логика Ромы), train | 28.7% | **19.9%** | 13.8% | 10.3% |
| strict, val | 32.6% | **36.9%** | 27.3% | 10.4% |
| true-invalid only (SCL 0,1) | 0.95% | 0.0% | 0.0% | 0.0% |

Старый evaluator (strict mask) поэтому выкидывал 37% class 1 на val: все прошлые цифры BSScore (0.342 и т.д.) посчитаны на «лёгком» подмножестве. Теперь каждый эксперимент оценивается двумя evaluator: `strict_mask` (сопоставимо с прошлым) и `all_valid_mask` (все пиксели, кроме SCL 0/1; ближе к возможному официальному подсчёту). v002-модель: 0.342 (strict) / 0.270 (all-valid, 0.282 после перекалибровки).

### Найденный дефект признаков

Прежний `rdnbr` считался с B11 (SWIR1), а стандартный S2 NBR = (B8A−B12)/(B8A+B12). Добавлены `dnbr12`/`rdnbr12` (стабилизированный знаменатель, clip, тест на NaN/inf).

### Что реализовано

- crop sampler 256×256 без ресайза; mix random/class1/burn = 50/30/20; целевой пиксель попадает в случайную позицию внутри кропа; валидация всегда на полных 512×512 сценах;
- один и тот же geometric transform (rot90/flip) для всех модальностей и target; один общий brightness-коэффициент U(0.95,1.05), p=0.3, на pre и post, индексы пересчитываются после; категориальные каналы не интерполируются, assert на `unique(GT) ⊂ {0,1,2,3,255}`;
- OHEM (`OHEMLoss`), soft-capped weights, true dual-head (`DualHeadAttentionUNet` + `DualHeadLoss`, ordinal-член);
- landcover как 5 one-hot групп (forest/shrub, grass/moss, cropland, wet/water, other), NDVI/dNDVI, SCL quality-каналы (cloud/shadow/dark/water/snow/clear);
- 8 новых регрессионных тестов (`tests/ml/test_bs_crop.py`), всего 52 теста.

Замечание: brightness-аугментация меняет только сырые каналы отражения; нормализованные индексы (dNBR, NDVI) инвариантны к общему масштабу, поэтому «пересчёт индексов» здесь формально верен, но практически не создаёт сигнала.

### Результаты screening (single grouped split 179/45, seed 42, config B если не указано, 30 crop-эпох×2 ≈ 15 full-scene-эпох по compute)

| id | что | strict raw→cal | all-valid raw→cal | bias (all-valid) |
|---|---|---|---|---|
| ref_full_ce | full scene, CE, без весов | 0.289→0.316 | 0.199→0.237 | (0,1.0,-0.4,-1.0) |
| crop_ce | crop 256 mix 50/30/20, CE | 0.345→0.347 | 0.274→0.297 | (0,-0.2,-1.0,-1.6) |
| full_ohem25 | full scene, OHEM 0.25 | 0.294→0.335 | 0.242→0.275 | (0,1.0,0.4,0.4) |
| crop_ohem25 | crop + OHEM 0.25 | 0.356→0.357 | 0.301→0.301 | (0,0,0,0) |
| crop_ohem10 | OHEM 0.10 | 0.316→0.316 | 0.276→0.276 | |
| crop_ohem40 | OHEM 0.40 | 0.361→0.362 | 0.313→0.315 | |
| crop_ohem25_bright | + brightness p=0.3 | 0.350→0.359 | 0.305→0.312 | |
| crop_ohem25_true | ignore только SCL 0/1 | 0.352→0.353 | 0.319→0.321 | |
| crop_ohem25_B12 | NBR на B8A/B12 | 0.364→0.365 | 0.320→0.320 | |
| crop_ohem25_lc5 | B12 + 5 landcover-групп | 0.366→0.368 | 0.325→0.328 | |
| v002-модель (для сравнения) | old pipeline + bias(0,-1.6,-1.8,-1.6) | 0.342 | 0.270 | |

Выводы: (1) crop sampler — главный рычаг (+0.03 strict, +0.06 all-valid относительно full-scene с теми же loss/данными); (2) OHEM 0.25–0.40 добавляет ≈+0.01, OHEM 0.10 вредит (слишком узкий hard-pool); (3) при crop+OHEM калибровочный bias ≈ 0 — модель больше не завышает burn изначально, зависимость от post-hoc bias (которая и сделала v002) исчезла; (4) true-invalid ignore чуть хуже на strict, но лучше на all-valid — то есть выигрывает именно на пикселях, которые старый evaluator скрывал; (5) B12 и landcover дают маленькие, но однонаправленные приросты (≈+0.003…+0.008), каждый на уровне шума одного seed. Все разницы <0.02 и не подтверждены на GroupKFold.

### Stacked recipe и подтверждение на GroupKFold

Стек: crop 256 (50/30/20) + ignore только SCL 0/1 + shared brightness p=0.3 + OHEM 0.40 + B12-NBR + 5 landcover-групп (single split 179/45, all-valid evaluator, calibrated): `stack_lc5` 0.346 (strict 0.370), `+NDVI` 0.350, `+quality-каналы` 0.345, `dual-head` 0.348, `dual+ordinal 0.1` 0.348. Всё в пределах ±0.005 друг от друга — плато ≈0.345–0.35 all-valid; quality-каналы, NDVI, ordinal-член не дали подтверждённого прироста. True dual-head (общий encoder, отдельные burn/severity головы) даёт лучший IoU class 1 (0.367) и не требует bias (≈0), но по суммарному BSScore равен OHEM-варианту.

**3-fold GroupKFold (fire_event_id, те же фолды, что у baseline-CV), без какой-либо калибровки (raw), strict evaluator:**

| recipe | fold1 | fold2 | fold3 | mean |
|---|---|---|---|---|
| старый baseline (calibrated, 10 эпох full-scene) | 0.308 | 0.306 | 0.293 | 0.302 ± 0.008 |
| NDVI + OHEM 0.4 (raw) | 0.360 | 0.360 | 0.349 | 0.356 |
| dual-head (raw) | 0.371 | 0.353 | 0.353 | 0.359 |

Pooled OOF, глобальный bias, BSScore (strict / all-valid): NDVI+OHEM 0.361 / 0.343; dual 0.359 / 0.339; **blend 50/50 0.365 / 0.346**; старый baseline pooled OOF 0.298 (strict). Прирост ≈ +0.06 на каждом из трёх фолдов; калибровочный bias у нового recipe ≈0…0.4 (у v002 был −1.6…−1.8). Оговорка: новый recipe учился 30 crop-эпох ≈ 15 full-scene-эпох по compute против 10 у старого CV; по прошлым замерам (15→25 эпох ≈ +0.005) это объясняет ≤ 0.01 из 0.06. Blend даёт +0.004–0.005 к лучшей одиночной модели. IoU по классам pooled OOF (blend, all-valid): burn 0.542, class1 0.343, class2 0.533, class3 0.683, mIoU_severity 0.520.

### V003 (не загружен)

`artifacts/submissions/submission_v003.csv` (+`.json`): AF без изменений (строки AF побайтово равны v002), BS = full-train (все 224 чипа) ансамбль двух моделей (logit-average) + OOF global bias (0, 0.4, 0.2, 0.2). Validator PASS, 447 строк, sha256 `6a61626d...`. Инференс детерминирован (двойной прогон каждого чипа), 120 мс/чип на MPS, 24 с на 89 чипов. Test: средняя предсказанная burn-доля 18.7% (v002 ≈20%, v001 40%; train 10%) — только логируется, на выбор модели не влияло. v001/v002 не изменены (sha256 совпадают).

Ожидания: BSScore = 0.35·IoU_burn + 0.30·mIoU_severity — это ровно BS-часть public Score, поэтому локальный прирост переносится в Score напрямую. Оценки прироста относительно v002-модели расходятся по протоколу: на одном split +0.028 (strict) / +0.06…0.07 (all-valid), на GroupKFold +0.06 (но у старого CV было 10 эпох вместо ≈15). Разумный диапазон ожидания — +0.03…+0.06 к Score, т.е. примерно 0.68–0.70; это ожидание, не гарантия (у v002 локальные +0.073 дали public +0.093).

Не запускалось в этой итерации: hard-negative crop pool, boundary sampler/aux head, chip-level head, cloud-aware S1 + optical dropout, boosting refiner, external pretraining, AF thermal expert.

## ITERATION 4: HARD-NEGATIVE / BOUNDARY SAMPLING ПОВЕРХ V003 (нейросетевой трек)

**v003 = public 0.72** (v002 0.6457, v001 0.5526) — gold baseline; v003 артефакты (csv, manifest, full-train чекпоинты, OOF logits, калибровка) не менялись (sha256 csv `6a61626d…` совпадает).

Гипотеза: v003 выиграл за счёт crop sampling + OHEM, значит следующий естественный шаг — добавить в sampler ошибки самой модели (hard negatives 0→1, hard positives class 1, граница 0↔1).

**Pools** (179 train-чипов single split; hard-примеры майнились только по train-чипам из OOF logits v003-модели `cv_ndvi`; оговорка: OOF logits чипа j получены моделью, обучавшейся в том числе на чипах валидации, то есть утечка второго порядка, метки валидации в отбор не входят):

| pool | пикселей | состав |
|---|---|---|
| hard negatives (GT=0, уверенно burn, p_burn>0.5) | 1 870 864 | cropland 75.5%, grass/moss 22.2%, forest 1.1%, wet/water 1.1%, other 0.1% |
| hard positives (GT=1, уверенно 0 или 2, conf>0.6) | 666 652 | — |
| 0↔1 boundary (dilation 2px по GT) | 1 797 741 | — |

Подтверждает диагностику iteration 2: ложный burn сосредоточен на cropland/grass (97.7% hard negatives).

**Controlled fine-tune** (модель 1 v003: B12+landcover5+NDVI, OHEM 0.4, lr 3e-4, 8 эпох, тот же single split, config/loss/аугментации те же). Контроль `ft_ref` — тот же fine-tune с референсным sampler, чтобы отделить эффект sampler от дообучения:

| run | sampler | strict cal | all-valid cal | IoU1 (all) | 0→1 FP px (all) | 0→1 rate | 1→0 FN px | 1→2 px |
|---|---|---|---|---|---|---|---|---|
| v003 model 1 (без fine-tune) | 50/30/20 | 0.3692 | 0.3495 | 0.358 | 259 904 | 2.44% | 153 278 | 32 138 |
| ft_ref (контроль) | 50/30/20 | 0.3735 | 0.3511 | 0.356 | 249 682 | 2.34% | 165 000 | 21 912 |
| ft_A | 40 rnd/25 c1/15 burn/20 hardneg (+hardpos в квоте class1) | 0.3726 | 0.3519 | 0.367 | 271 340 | 2.55% | 146 591 | 26 381 |
| ft_B | 35/25/15/15 hardneg/10 boundary01 | 0.3696 | 0.3490 | 0.357 | 286 655 | 2.69% | 141 532 | 36 795 |

**Результат — отрицательный.** Относительно контроля: ft_A −0.001 / +0.001, ft_B −0.004 / −0.002 (порог +0.008 не пройден ни близко). IoU1 у ft_A вырос (+0.011 all-valid), но за счёт большего числа предсказаний class 1 (recall 0.581→0.612, precision 0.480→0.478), а не за счёт меньшего числа ложных: 0→1 FP **вырос** (250k→271k у A, →287k у B), и потребовался больший калибровочный bias. Критерий успеха (IoU1↑ при 0→1 FP↓) не выполнен. Вероятное объяснение: hard negatives на cropland — пиксели около слабых ожогов и с неоднозначной разметкой; передискретизация сдвигает границу решения в сторону class 1, а не учит разделять cropland-сезонность и ожог. Граничный sampler 0↔1 добавляет 1→2 путаницу (28–37k против 16–22k).

Дообучение само по себе (+8 эпох на малом lr) даёт лишь +0.002…+0.004 — обучение v003 уже насыщено по длительности.

**Не запускалось (осознанно):** 3-fold подтверждение и blend с v003 — не имеют смысла без прохождения fast-screen порога; Focal Tversky (α=0.2, β=0.8) — β=0.8 штрафует пропуски (FN) сильнее ложных, а наш дефект — ложные срабатывания 0→1, поэтому ожидаемо ухудшит целевую метрику; Ромин standalone BSScore ≈0.323 ниже нашего OOF.

**Вывод: NEURAL CANDIDATE — NOT READY.** Победителем нейросетевого трека остаётся v003-пайплайн; кандидатных артефактов не создавалось (`artifacts/submissions/candidates/` не создан), v004/v005 не занимались.

## V003 PUBLIC = 0.72

v003 (`artifacts/submissions/submission_v003.csv`, sha256 `6a61626d…039c`) — текущий gold baseline, заморожен. AF без изменений от v002. BS: ансамбль двух full-train Attention U-Net (B12 NBR + 5 групп landcover + NDVI с OHEM 0.4; B12 + landcover с true dual head), crop 256, ignore только SCL 0/1, blend логитов + OOF bias (0, 0.4, 0.2, 0.2). GroupKFold pooled OOF: 0.3458 all-valid / 0.3650 strict. Чекпоинты, OOF-логиты (`/tmp/bs_oof/cv_{ndvi,dual}_f*.npz`) и калибровка v003 использовались только на чтение.

## CLASS-1 / PHYSICS-GUIDED IMPROVEMENT TRACK

Код: `kroma_ml.bs_physics`, `kroma_ml.bs_cv` (канонический evaluator + контракт предсказаний), `kroma_ml.bs_sampling`, `kroma_ml.bs_track_losses`, `kroma_ml.bs_fast_models`; скрипты `bs_class1_audit.py`, `bs_physics_baseline.py`, `bs_eval_contract.py`, `bs_fusion.py`, `bs_track.py`. Тесты: `tests/ml/test_bs_class1_track.py`.

**Canonical evaluator.** `python research/experiments/bs_eval_contract.py <npz...>`: NPZ с `ids` + одним из `logits (N,4,512,512)` / `probs` / `labels (N,512,512)`, опционально `class_order = (background, low, moderate, high)`. Считает per-fold (фолды определяются по chip_id через GroupKFold по fire_event_id), mean/std/worst, pooled, per-class IoU/P/R/F1 на strict и all-valid масках. На OOF-логитах очереди cv_ndvi fold 1 воспроизводит собственные числа очереди точно (0.3597 / 0.3360) — сравнивать чужие результаты (в т.ч. «0.81») только через него.

**Class-1 audit (224 сцены, GroupKFold 3).** Class 1 есть в 100% сцен, 4.0% пикселей; 41 187 компонент, медиана 3 px, 73% компонент ≤ 9 px, но они несут лишь 3.2% пикселей class 1; 43% пикселей class 1 касаются другого класса (32% — фона, 18% — class 2). Выравнивание pre/post в норме (медианный сдвиг 0.05 px), маска vs dNBR без сдвига в 94% сцен.

**Главный вывод.** Внутри контура гари severity почти детерминирована физикой: dNBR (B8A/B12) даёт перекрытие распределений 1↔2 = 0.14, 1↔3 = 0.01. Если контур взять из разметки, а severity — из органайзерских порогов по landcover, BSScore = **0.615**, IoU1 = 0.917 (с одним глобальным порогом 0.596). Единственная плохо разделимая пара — 0↔1 (перекрытие 0.22): контур разметки задан внешним периметром (на монтажах — дуги-буферы), и такие же по спектру поля за периметром размечены фоном. В OOF v003-компонент 95% FP class 1 приходят из фона, 1→0 = 39%, 1→2 = 3%.

**SCL audit.** Strict SCL выбрасывает 23.1% пикселей class 1 (в основном перистые облака SCL 10 и облака средней вероятности SCL 8); у выброшенных пикселей dNBR такой же, как у оставшихся (медиана 0.121 vs 0.117), то есть это настоящие метки, а не облачный шум. 29 сцен теряют >90% class 1. Режимы true-invalid (SCL 0/1) и «только невозможные пиксели» совпадают.

**Physics baseline (пороги подобраны только на train-фолдах, тот же evaluator):**

| variant | BS all-valid | BS strict | IoU1 | burn IoU |
|---|---|---|---|---|
| USGS dNBR 0.10/0.27/0.66 без подбора | 0.183 | 0.226 | 0.168 | 0.371 |
| dNBR, 3 порога (full-train 0.105/0.205/0.39) | 0.240 | 0.300 | 0.194 | 0.372 |
| RdNBR B12 / legacy B11 | 0.200 / 0.148 | 0.238 / 0.191 | 0.116 / 0.076 | 0.408 / 0.293 |
| RdNBR-gate 0.5 + dNBR-severity | 0.258 | 0.308 | 0.160 | 0.413 |
| **организаторские пороги по landcover (рис. 6)** | 0.247 | 0.301 | 0.230 | 0.358 |

Переход B11→B12 физически подтверждён (+0.05). ML (v003) выше лучшей физики на +0.09 all-valid — почти целиком за счёт контура (burn IoU 0.54 vs 0.41).

**Post-hoc fusion «ML-контур + единый dNBR-порог»** на OOF cv_ndvi/cv_dual нейтрален (−0.002…0.000): нейросеть уже выучила глобальные полосы. Прирост появляется только с **landcover-условными** порогами организаторов (см. ниже).

**Длинная очередь из ~15 кандидатов (sampler/hard/loss/prior/context/SegFormer/MobileUNet) остановлена по новому приоритету**, контрольный прогон c0 был прерван на 15/30 эпохе, результатов нейросетевых абляций нет. Код (`bs_track.py`, `bs_track_queue.py`, `bs_infer_bench.py`) готов и покрыт тестами.

## FAST V004 CLASS1/PHYSICS TRACK

**Organizer physics** (Постановка кейса, с. 8, рис. 6; машиночитаемо в `research/experiments/bs_v004_physics_thresholds.json`). NBR = (B8A − B12)/(B8A + B12), dNBR = NBR_pre − NBR_post, RdNBR = dNBR/(√|NBR_pre| + 0.01), clip ±6. Пороги 0/1, 1/2, 2/3: лес/кустарник 0.10/0.27/0.66 (WorldCover 10, 20); травы 0.062/0.204/0.386 (30); пашня 0.07/0.177/0.38 (40); болото/пойма 0.075/0.331/0.677 (90, 95). Для редких кодов 50/60/80 эмпирически лучше подходят пороги поймы — используются как fallback. Совпадение с GT severity внутри GT-контура: 0.938 (глобальный подобранный порог — 0.900). GEE-ноутбук организаторов (`MK1_Krasnoyarsk_fires_GEE.ipynb`) использует только глобальную шкалу EFFIS 0.10/0.27/0.44/0.66 и B8 вместо B8A — для эталона кейса он не является источником порогов.

**Refiner.** LightGBM multiclass (400 деревьев, 63 листа) на OOF-вероятностях v003 (обучение для фолда k — только на OOF-пикселях двух других фолдов). 37 признаков: p0..p3, p_burn, p1−p0, top-1/top-2 margin, предсказание v003, dNBR, RdNBR, расстояния до органайзерских порогов (d_low/d_mod/d_high, |d_low|), органайзерский класс, группа landcover, NDVI pre/post/dNDVI, B4/B8A/B11/B12 pre/post, SCL pre/post, окна 5/15/31 по p_burn/p1/dNBR/доле физической гари, знаковое расстояние до предсказанной границы. Выборка на сцену: 5k равномерно + до 2k ошибок v003 (hard pos/neg) + 1.5k class 1 + 1.5k GT-границы 0↔1. Главные признаки по gain: d_low 21%, органайзерский класс 20%, d_mod 7%, dNBR 6%, p1 5%. Применяется **только** в зоне p_burn ∈ [0.3, 0.7] или ≤ 2 px от предсказанного контура; уверенные class 2/3 (p ≥ 0.6) не трогаются. Class bias (0, 0.4, 1.0, 0.8) подобран на pooled OOF.

**Hybrid C.** Контур burn/no-burn — от (уточнённого) ML; severity = argmax(log p_sev + 1.0 · onehot(органайзерский класс)). Физика не может нарисовать гарь с нуля (проверяется тестом).

| experiment | IoU_burn | IoU1 | IoU2 | IoU3 | mIoU | BSScore all-valid (mean / worst fold) | BSScore strict | 0→1 FP | 1→0 FN | cropland 0→1 FP | runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v003 (OOF, frozen) | 0.542 | 0.343 | 0.533 | 0.683 | 0.620 | 0.3455 / 0.3406 | 0.3648 | 0.0354 | 0.339 | 0.0477 | — |
| organizer physics, full scene | 0.358 | 0.230 | 0.397 | 0.591 | 0.504 | 0.2468 / 0.2427 | 0.3008 | 0.1329 | 0.033 | 0.1113 | 5 ms/chip CPU |
| oracle: GT contour + organizer severity | 1.000 | 0.917 | 0.849 | 0.882 | 0.912 | 0.6148 / 0.6117 | 0.6145 | 0 | 0 | 0 | — |
| hybrid A: v003 contour + organizer severity | 0.542 | 0.357 | 0.540 | 0.699 | 0.630 | 0.3493 / 0.3450 | 0.3685 | 0.0322 | 0.339 | 0.0422 | +0.3 s |
| hybrid B τ=0.7 | 0.542 | 0.359 | 0.562 | 0.719 | 0.640 | 0.3536 / 0.3485 | 0.3732 | 0.0337 | 0.339 | 0.0447 | +0.3 s |
| hybrid C w=1.0 | 0.542 | 0.360 | 0.562 | 0.721 | 0.641 | 0.3538 / 0.3487 | 0.3735 | 0.0336 | 0.339 | 0.0444 | +0.3 s |
| refiner, wide gate | 0.527 | 0.362 | 0.546 | 0.700 | 0.630 | 0.3448 / 0.3418 | 0.3589 | 0.0491 | 0.203 | 0.0543 | ≈1.9 s |
| refiner, p_burn∈[0.2,0.8] ∪ ≤2 px | 0.557 | 0.390 | 0.543 | 0.690 | 0.636 | 0.3568 / 0.3528 | 0.3720 | 0.0433 | 0.185 | 0.0551 | ≈1.9 s |
| refiner, p_burn∈[0.3,0.7] ∪ ≤2 px | 0.561 | 0.388 | 0.543 | 0.691 | 0.636 | 0.3584 / 0.3546 | 0.3752 | 0.0388 | 0.228 | 0.0510 | ≈1.9 s |
| **v004 = refiner [0.3,0.7] ∪ ≤2 px + hybrid C** | **0.561** | **0.399** | **0.566** | **0.724** | **0.653** | **0.3652 / 0.3608** | **0.3822** | 0.0378 | 0.228 | 0.0492 | ≈2.0 s |

Прирост v004 над v003 на OOF: +0.020 all-valid (по фолдам +0.0205 / +0.0186 / +0.0202), +0.017 strict; IoU1 +16% отн., IoU2/IoU3 тоже растут, IoU0 не меняется (0.922). Выбор из ~9 вариантов gate/hybrid на тех же OOF даёт небольшой оптимизм (разброс между соседними вариантами ≈0.002), он много меньше прироста.

**Что именно улучшилось:** (1) пропуски class 1 (1→0 FN 0.339 → 0.228) — refiner по d_low и контексту возвращает слабую гарь внутри контура; (2) severity внутри контура — органайзерские пороги по landcover (+0.008 сами по себе). **Что не улучшилось:** ложная гарь на пашне — cropland 0→1 FP 0.0477 → 0.0492, на срезе «пашня, 0 < dNBR < 0.177» доля FP-гари 0.098 → 0.109. Hard negatives пашни этим refiner не решены.

**Submission v004** — `artifacts/submissions/submission_v004.csv` (sha256 `743138c2…17c8`), манифест `submission_v004.json`. AF построчно byte-identical v003; BS = v003 full-train ансамбль (на тесте воспроизведён побайтно для всех 89 сцен) + refiner, обученный на OOF всех 224 сцен, + hybrid C. Validator PASS, 447 строк (AF 180, BS 267). Инференс детерминирован (повторный полный прогон, включая переобучение refiner, дал тот же sha). На тесте изменено 4.8% пикселей; сдвиг объёмов классов (sev1 +7%, sev2 +10%, sev3 −6%) того же знака, что на OOF для class 1/2. Воспроизведение: `bs_v004_fasttrack.py` → `bs_v004_combo.py` → `bs_v004_logits.py` (torch/MPS) → `bs_v004_infer.py --refiner --band 0.3 --radius 2 --bias 0,0.4,1.0,0.8 --hybrid hybrid_C_w1.0` → `bs_v004_build.py`. Torch-стадия и LightGBM-стадия разнесены по процессам: при загрузке torch раньше lightgbm на macOS конфликтует libomp (segfault).

**Внешние данные (только инвентаризация, ничего не скачивалось).** HLS Burn Scars (США, HLS 30 м, 6 каналов, ~800 чипов 512², бинарная маска, лицензия указана как MIT) — бинарное предобучение; CaBuAr (Калифорния, S2 L2A pre/post, бинарные маски CAL FIRE, CC BY-NC 4.0) — бинарное предобучение, только некоммерческое; CEMS Wildfire (S2, маски разграничения и grading Copernicus EMS, 500+ снимков) — единственный кандидат с severity, но таксономия другая (damaged/destroyed); EO4WildFires (S1+S2+метео, 31 730 событий, аннотации EFFIS) — бинарный/размерный сигнал; SSL4EO-S12 (251k локаций S1/S2, CC BY 4.0, есть веса для 13 каналов S2) — самообучаемое предобучение энкодера. Прямой supervised transfer severity невозможен: в кейсе severity относительна landcover и задана органайзерскими порогами.

**NEXT (максимальный ожидаемый эффект).** Периметр — единственное, что осталось между 0.365 и oracle 0.615. (1) Короткий fine-tune одной компоненты v003 с каналами d_low/d_mod/d_high и hard negatives пашни (GT = 0, высокий p_burn, 0 < dNBR < 0.177) — refiner эти FP не снял. (2) Контекст для периметра: кропы 384/512 (другой процесс уже запускал ctx256/384/512) или глобальное внимание. (3) Refiner второго уровня с признаками формы периметра (выпуклость контура, расстояние до крупного ядра гари).

## LEADERBOARD: v003 = 0.7298, v004 = 0.7406 (gold baseline)

OOF-прирост v004 +0.020 (all-valid) дал на public +0.011. v001–v004, их манифесты, OOF-логиты, full-train чекпоинты и артефакты refiner не изменялись (sha256 проверены).

## V005 CONTOUR TRACK: main-fire components

Код: `kroma_ml/bs_v005.py`, `research/experiments/bs_v005_oof_v004.py` (OOF-карты v004, воспроизводят 0.3652/0.3822 точно), `bs_v005_contour_diag.py`, `bs_v005_components.py`, `bs_v005_refiner2.py`, `bs_v005_combo.py`, `bs_v005_infer.py`, `bs_v005b_infer.py`, `bs_v005_build.py`.

**Где лежит score (OOF, all-valid).** GT-контур + severity v004 → 0.621; контур v004 + GT-severity → 0.380 (+0.015); попиксельный best-of v003/v004 → 0.412. Главная ошибка контура — ложная гарь: 3.46 млн FP-пикселей (59% площади GT-гари) против 0.65 млн FN.

**Core → class1 (гипотеза проверена, в простом виде отвергнута).** Доля пикселей на расстоянии ≤ 2 px от ядра:

| ядро | GT class 1 | FP-гарь v004 | FP на пашне |
|---|---|---|---|
| GT class 2/3 (оракул) | 0.19 (≤ 5 px: 0.37) | 0.02 (> 20 px: 0.88) | 0.01 |
| предсказанное (p_burn ≥ 0.8 или severity 2/3) | 0.66 | 0.82 | 0.84 |
| физическое (органайзерский класс ≥ 2) | 0.20 | 0.52 | 0.57 |

Связь со *всяким* уверенным ядром не отделяет ложную гарь: ложные области сами являются уверенными ядрами (целые поля). Hysteresis (T_high 0.7–0.9, T_low 0.3–0.5, радиус 0/2), distance-conditioned порог и глобальный порог 0.40–0.65 — все в пределах ±0.001 от v004.

**Что сработало: компонента против «главного пожара» чипа.** Связные компоненты предсказанной гари (p_burn ≥ 0.5) → 34 признака (площадь, форма, p/dNBR/органайзерская физика, landcover, кольцо вокруг, ранг по площади/по severity 3 в чипе, **расстояние до главной компоненты чипа**, доля гари чипа, число компонент). LightGBM real vs false (overlap ≥ 0.5 с GT), обучение только на компонентах других фолдов. AUC 0.80/0.83/0.81. Главный признак — `dist_main_sev3` (23% gain): разметка обводит основной пожар, а похожие на гарь поля вдали от него — фон.

**Refiner v2** (пиксельный, бинарный burn): вероятности v004, организаторская физика, контекст 11/41 px, расстояния до главной компоненты чипа, статистика чипа, признаки своей компоненты на уровнях p_burn 0.5 и 0.3; выборка ошибок v004 (FP, FN, class 1, граница). Вероятности компонентного классификатора в него сознательно не подаются (избегаем третьего уровня стекинга). Главные признаки: `dist_main_sev3_px` 16%, `d_low` 10%, доля гари чипа 6%.

| experiment | BS all-valid | BS strict | IoU_burn | IoU1 | IoU2 | IoU3 | 0→burn FP | 1→0 FN | cropland FP | grassland FP | worst fold | contour runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v004 | 0.3652 | 0.3822 | 0.561 | 0.399 | 0.566 | 0.724 | 0.066 | 0.228 | 0.095 | 0.050 | 0.3608 | — |
| hysteresis (лучший, h0.9 l0.5) | 0.3661 | 0.3829 | 0.564 | 0.401 | — | — | 0.065 | 0.237 | 0.094 | 0.048 | 0.3610 | <0.1 s |
| distance-conditioned (лучший) | 0.3648 | 0.3817 | 0.561 | 0.400 | — | — | 0.067 | 0.221 | 0.097 | 0.050 | 0.3611 | <0.1 s |
| component classifier, drop p < 0.3 (v005a) | 0.4129 | 0.4312 | 0.645 | 0.462 | 0.651 | 0.762 | 0.033 | 0.310 | 0.042 | 0.034 | 0.4101 | 0.2 s |
| refiner v2 alone (t = 0.35) | 0.4077 | 0.4180 | 0.631 | 0.468 | 0.645 | 0.753 | 0.042 | 0.180 | 0.046 | 0.051 | 0.4024 | 1.3 s |
| **components + refiner v2 (v005b)** | **0.4298** | **0.4401** | **0.671** | **0.504** | **0.669** | **0.775** | **0.032** | **0.218** | **0.036** | **0.039** | **0.4267** | 1.5 s |

v005b по фолдам: 0.4267 / 0.4325 / 0.4303 против v004 0.3667 / 0.3682 / 0.3608 (+0.060…+0.070). Правило: убрать компоненты с вероятностью < 0.3; refiner v2 добавляет гарь при p ≥ 0.8 вне убранных компонент и убирает пиксели с p < 0.2 внутри оставшихся; severity добавленных пикселей — v004 + органайзерский prior. Пороги выбраны из ~50 вариантов на тех же OOF; соседние варианты дают 0.425–0.430, поэтому ожидаемый оптимизм выбора ≈ 0.003.

**Перенос на тест.** v004 на тесте воспроизводится побайтно перед пост-обработкой. Доли изменений: удалено 22.0% гари v004 (OOF 30.3%), добавлено 5.7% (OOF 8.2%) — то же направление, ~0.72 от OOF-масштаба (full-train модели на тесте увереннее). С учётом того, что +0.020 OOF у v004 дали +0.011 public, ожидаемое направление для v005b — рост public; величину не обещаем (ориентир по масштабу — примерно половина OOF-прироста).

**Не сделано в этой итерации.** CatBoost не установлен (установка требует скачивания пакета) — остался LightGBM. Выделенная бинарная сегментационная сеть, context 384/512 (другой процесс ещё обучает, OOF нет) и стекер — не запускались: GPU и память заняты обучением другого процесса. Внешние данные: только инвентаризация (HLS Burn Scars, CaBuAr, CEMS Wildfire, EO4WildFires, FLOGA, SSL4EO-S12); скачивание требует отдельного подтверждения.

**Кандидаты.** `artifacts/submissions/candidates/submission_v005a_component.csv` (OOF 0.4129) и `submission_v005b_component_refiner2.csv` (OOF 0.4298, рекомендован). AF в обоих побайтно совпадает с v004/v003.

## ITERATION 5: КОНТЕКСТ (размер crop) — controlled experiment

Гипотеза: 0↔1 путаница — от нехватки пространственного контекста, а не от нехватки hard-примеров (hard-negative sampling закрыт в iteration 4). Меняется ТОЛЬКО размер crop; всё остальное как в v003-модели 1 (B12 + landcover5 + NDVI, OHEM 0.4, ignore SCL 0/1, brightness p=0.3, 30 эпох × 2 crop/чип, тот же single split 179/45, тот же evaluator, mix 50/30/20). 384 и 512 обучались с batch 4 × accumulation 2 (эффективный batch 8, как у 256; из-за памяти) — BatchNorm видит по 4 сэмпла вместо 8, это известное отличие. 256 повторён с текущим кодом и воспроизвёл прежний результат до последней цифры (детерминизм подтверждён).

| context | BSScore strict (cal) | BSScore all-pixel (cal) | IoU_burn (all) | IoU1 / IoU2 / IoU3 (all) | mIoU_sev | 0→1 FP px (all) | cropland 0→1 (px, rate) | grass 0→1 (px, rate) | 1→0 FN px |
|---|---|---|---|---|---|---|---|---|---|
| 256 (control = v003 recipe) | 0.3692 | 0.3495 | 0.556 | 0.358 / 0.525 / 0.666 | 0.516 | 259 904 | 188 543 (3.89%) | 56 318 (1.54%) | 153 278 |
| 384 | 0.3707 | 0.3423 | 0.552 | 0.343 / 0.508 / 0.640 | 0.497 | 210 452 | 142 725 (2.95%) | 54 097 (1.48%) | 176 372 |
| 512 (full scene) | 0.3709 | 0.3470 | 0.560 | 0.352 / 0.515 / 0.642 | 0.503 | 190 259 | 115 614 (2.39%) | 57 831 (1.59%) | 182 536 |

Runtime: замеры искажены — 384 и 512 обучались параллельно друг другу и стороннему процессу (train 871 / 2969 / 3708 с). Инференс всегда на полной 512-сцене, поэтому стоимость одинакова по построению (измерено 104 / 179 / 97 мс/чип на MPS — разброс от конкуренции за GPU, не от модели). Сырые (некалиброванные) all-pixel скоры: 0.346 / 0.328 / 0.324; калибровочные bias у 384/512 заметно больше (0.4–0.8 против 0.2–0.4): модель с большим контекстом консервативнее по burn.

**Результат: контекст — победитель НЕТ.** Gate (BSScore ≥ +0.008, либо IoU1 заметно ↑ при 0→1 FP ↓) не пройден: all-pixel −0.007 (384) и −0.0025 (512), strict +0.002 (в пределах шума), IoU1 у обоих ниже контроля (0.343 и 0.352 против 0.358).

Но механизм подтверждён частично: больший контекст **резко снижает ложные срабатывания на cropland** (−39% пикселей, 3.89%→2.39% у 512; общий 0→1 FP −27%), как и предполагала гипотеза. Одновременно растёт 1→0 (+19% FN): модель просто становится осторожнее, и после оптимальной калибровки чистый BSScore не меняется. То есть контекст сдвигает точку на кривой precision/recall class 1, но не раздвигает саму кривую. 3-fold подтверждение и blend не запускались (условие gate не выполнено, пункт 7 задания).

Ромина модель: чекпоинта в репозитории нет (`cosmohack_dataset (1).ipynb` содержит только лог обучения) — на каноническом evaluator не оценивалась.

Не проверено (осознанно, пункт 7 задания — не запускать zoo): логит-blend уже обученных ctx256 и ctx512 (их ошибки комплементарны по FP/FN, blend не требует переобучения), но подтверждать его пришлось бы 3-fold переобучением (~1 ч+).

**NEURAL TRACK: заморожен на v003 (public 0.72). Кандидата нет.**

## LEADERBOARD: v004 = 0.7406 → v005 = 0.81

v005 = v004 → классификатор связных компонент (отбраковка областей вне главного пожара чипа) → пиксельный contour refiner v2 → organizer severity physics. OOF all-valid 0.3652 → 0.4298 (+0.065) перенёсся в public как +0.069. Подтверждено: component-level рассуждение о контуре — главный прорыв. v005 заморожен, как и v001–v004.

## POST-V005: CONTEXT + RED-EDGE (закрыто по таймбоксу)

**Context (ctx512, single split, 45 val-чипов — только диагностика).** 58% FP-пикселей v005 ctx512 считает фоном, но ctx512 теряет 186k пикселей class 1, которые v005 находит. На уровне компонент доля отвержения ctx512 разделяет ложные и настоящие компоненты v005: AUC 0.84 (пашня), 0.93 (травы). Oracle «убрать ложную компоненту, если ctx512 согласен» = +0.030; наивные правила по доле отвержения — от −0.013 до −0.095. Fold-safe 3-fold ctx512 был запущен и остановлен по таймбоксу на 1-й эпохе (логи `data/processed/bs_v006/ctx512cv_f*.log`); leakage-safe context-признаков нет.

**Red-edge B5/B6/B7.** Против «похожего на гарь фона» ΔB5 несёт в 3–4 раза больше информации сверх dNBR (|AUC−0.5| внутри dNBR-бинов 0.175 vs 0.047), но против остаточных FP v005 — слабо (0.04–0.06). Контролируемый ablation (компонентный классификатор + refiner v2, переобучены fold-safe, правило v005 0.3/0.8/0.2):

| config | BS all-valid | folds | strict | IoU_burn | IoU1 | IoU2 | IoU3 | 0→1 FP | 1→0 FN | cropland FP | grass FP |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A: v005 (переобучен тем же кодом) | 0.4292 | .4266/.4315/.4297 | 0.4395 | 0.670 | 0.505 | 0.667 | 0.773 | 0.0211 | 0.218 | 0.0358 | 0.0394 |
| C: + red-edge | 0.4355 | .4332/.4349/.4383 | 0.4468 | 0.681 | 0.519 | 0.672 | 0.777 | 0.0198 | 0.211 | 0.0354 | 0.0362 |

+0.006 (на всех фолдах +0.003…+0.009) — ниже порога +0.01, **v006 не создан**. Red-edge — первый кандидат для следующей итерации, context — второй (после fold-safe OOF).

## SERVICE ADAPTER (v005, frozen)

`ml/src/kroma_ml/service.py`: `predict_af(chip_id, root=None)`, `predict_bs(chip_id, root=None)`, CLI `python -m kroma_ml.service {af|bs} CHIP_ID [--root DIR] [--out file.npz]`. Нейросетевая стадия BS запускается отдельным процессом (`kroma_ml.bs_neural`): torch/MPS и LightGBM в одном процессе на macOS дают segfault. Проверено: на AF_te_000001/000050 и BS_te_000001/000040 выход побайтно совпадает с submission_v005. Время: AF ≈ 0.4 s/чип, BS ≈ 4–7 s/чип на CPU/MPS (из них U-Net ≈ 1.7 s). Для train-чипов адаптер возвращает GT и карту ошибок (0 верно, 1 FP, 2 FN, 3 неверная severity); train-чипы входят в full-train обучение, поэтому качество на них оптимистично.

## POST-V005 FAST CONTOUR (таймбокс 40 мин) → v006 (conservative)

**Оракулы на OOF v005 (all-valid 0.4298).** Идеальные решения в полосе ±1/±2/±3 px от контура: +0.035/+0.052/+0.067. Идеальное восстановление дыр и гари рядом с принятой (≤ 2/5/10 px): +0.016/+0.023/+0.029. Идеальное удаление оставшихся ложных компонент: +0.040. FN v005: 54% дальше 10 px от любой принятой гари (целые пропущенные области), 8.8% — в дырах; FP: 33% на глубине 1–2 px от контура.

**Boundary micro-refiner** (LightGBM только в полосе ±3 px, fold-safe, признаки refiner v2 + red-edge + расстояние до контура + локальная доля гари 3/5/7 + вероятности компонент): лучший вариант (только добавления, t = 0.6) 0.4346 против 0.4355 у C; замена решений в полосе — от −0.003 до −0.009. Высокий оракул полосы доступными признаками не предсказывается — точность периметра разметки. Отвергнут; class-1 recovery (частный случай добавлений у контура) — тоже без прироста.

| experiment | BS all-valid | fold1 / fold2 / fold3 | strict | IoU_burn | IoU1 | IoU2 | IoU3 | 0→1 FP | 1→0 FN | cropland FP | grass FP | runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v005 | 0.4298 | .4267 / .4325 / .4303 | 0.4401 | 0.671 | 0.504 | 0.669 | 0.775 | 0.0211 | 0.218 | 0.036 | 0.039 | ≈4.1 s |
| + red-edge (C) = **v006** | **0.4355** | .4332 / .4349 / .4383 | **0.4468** | **0.681** | **0.519** | 0.672 | 0.777 | 0.0198 | 0.211 | 0.035 | 0.036 | +0.7 s |
| + boundary (add-only, t 0.6) | 0.4346 | .4329 / .4331 / .4379 | 0.4466 | 0.680 | 0.519 | 0.669 | 0.778 | 0.0200 | 0.208 | 0.037 | 0.037 | +~0.5 s |
| + boundary (replace, t 0.4) | 0.4321 | .4284 / .4359 / .4320 | 0.4432 | 0.676 | 0.509 | 0.666 | 0.776 | 0.0173 | 0.255 | 0.034 | 0.033 | +~0.5 s |

**v006** = v005 + red-edge-признаки (ΔB5/ΔB6/ΔB7, ΔNDRE5/6/7, NDRE7 post, локальные средние, контраст с кольцом компоненты) в компонентном классификаторе и refiner v2, правило решения v005 (0.3/0.8/0.2) не изменено. OOF +0.0057 (все фолды +0.002…+0.008) — между 0.005 и 0.010, поэтому это консервативный кандидат с небольшим ожидаемым приростом. Тест: v005 воспроизведён побайтно в том же прогоне; сдвиг относительно v005 — удалено 3.0% гари, добавлено 3.9% (OOF: 4.5% / 4.1%); severity-объёмы почти не изменились. Два полных прогона дают одинаковый результат (sha 4108db72…). `artifacts/submissions/submission_v006.csv`, validator PASS, 447 строк, RLE roundtrip, без пересечения классов, без NaN, AF побайтно = v005.

**Context ctx512 (не включён).** Снижает ложную гарь на пашне примерно на 39% (0→1 на пашне 3.89% → 2.39% относительно ctx256), но теряет слабую гарь (1→0 FN 153k → 183k); standalone-скор не вырос. Fold-safe 3-fold OOF требовал ~2–2.5 часа и был остановлен по таймбоксу, поэтому контекст в финальный кандидат не вошёл. Следующий шаг: fold-safe ctx512 OOF → признаки отвержения в компонентном классификаторе (oracle на 45 чипах +0.030, AUC отвержения ложных компонент 0.84 пашня / 0.93 трава).

На момент исследовательского прогона service воспроизводил v005. Финальная product integration подключила v006 без переобучения; полный competition CSV воспроизведён точно (180 AF + 89 BS, 447 строк). См. `docs/ml_handoff.md`.


## Final product integration · 2026-09-19

CURRENT GOLD **v006**, public score **0.8176**; previous stable v005 **0.8127** (уточнённые значения команды). Исторические записи выше сохраняют состояние соответствующего эксперимента, включая ранний вывод «v006 не создан».

Production adapter использует red-edge artifacts и неизменные правила 0.3/0.8/0.2. Переобучение в integration-проходе не проводилось. Full submission: 447 строк, exact match v006, без ошибок; 452.88 с при 2 workers × 2 threads, neural batch 19.81 с. Показатель зависит от машины/параллельной нагрузки.

Сервисные TRAIN overlays и метрики помечены in-sample; подготовленные derived-наборы 3 BS + 3 AF включены для воспроизводимой демонстрации. TEST геометрия/даты не восстанавливались. См. `docs/key_metrics.md`, `docs/model_card.md` и `docs/qa/final-integration.md`.
