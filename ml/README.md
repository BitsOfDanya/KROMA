# ML / active-fire intelligence

`kroma_ml.incidents` — исследовательский DBSCAN по пространству и времени; `thermal_memory` — разреженная равноплощадная историческая сетка; `features` — таблица входных признаков без меток; `priority` — объяснимые формулы threat и priority для уже подготовленных входов. Это независимый fixed-data baseline; backend LIVE не переключён на него.

В [едином отчёте](../research/report.md) указаны реальные пилоты, ограничения confidence и необходимые метки. Классификатор `P(real wildfire)` не обучался: подтверждённых incident labels пока нет.

Отдельная конкурсная AF сегментация работает с размеченными чипами организаторов: `af_infer.AFPredictor` для LightGBM и `af_unet.AFUNetPredictor` для сохранённого U-Net checkpoint. Оба выдают бинарную маску 256×256, без подключения к общему сервису. Выбор AF модели и ограничения validation приведены в том же отчёте.
