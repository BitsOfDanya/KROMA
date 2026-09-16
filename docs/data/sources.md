# Первые источники данных

## Решение для первого этапа

1. **NASA FIRMS VIIRS NOAA-20 и S-NPP NRT** — начальный поток тепловых детекций. Используем Area API с ограниченным bbox, датой и диапазоном 1–5 дней. Для API нужен бесплатный MAP_KEY; в проекте он передаётся через `NASA_FIRMS_API_KEY`. Поля CSV и категории confidence документированы NASA. [Area API](https://firms.modaps.eosdis.nasa.gov/api/area/), [поля VIIRS](https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_VIIRS_Firehotspots.html).
2. **NASA FIRMS MODIS** — следующий источник для проверки покрытия и сопоставления наблюдений. Его числовая confidence шкала отличается от категорий VIIRS, поэтому нужен отдельный нормализатор. [Поля MODIS](https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_MODIS_Firehotspots.html).
3. **Copernicus Sentinel-2 L2A** — будущие снимки для анализа гарей; поиск сцен по времени, области и облачности через каталог. Загрузка и обработка снимков пока не реализованы. [Доступ к L2A](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S2L2A.html), [STAC каталог](https://documentation.dataspace.copernicus.eu/APIs/STAC.html).
4. **ERA5 hourly** — кандидат для исторического анализа погодных факторов. Это реанализ; для оперативной погоды потребуется отдельный прогнозный источник. [Описание ERA5](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=documentation).

Для воспроизводимого исследования используем опубликованный NASA [пример VIIRS S-NPP за 12 июля 2023 года](https://firms.modaps.eosdis.nasa.gov/content/notebooks/sample_viirs_snpp_071223.csv). Конкретный вход и контрольная сумма фиксируются в рецепте оценки. Исходные данные остаются вне Git.

Перед использованием дополнительных источников нужно отдельно проверить условия доступа, атрибуции, территориальное покрытие и задержку публикации. Порядок выше является планом интеграции, а не утверждением о готовом пайплайне.
