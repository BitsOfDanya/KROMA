# Model card: KROMA GOLD v006

## Назначение

AF — бинарное обнаружение активного горения на VIIRS; BS — background/low/moderate/high на Sentinel-2 pre/post. Область применения ограничена официальным форматом и распределением конкурсных данных.

## Contract

`kroma_ml.service.predict_af(chip_id, root=None)` и `predict_bs(chip_id, root=None, logits=None)` возвращают NumPy arrays и metadata. Явный root означает inference без GT; default TRAIN root добавляет GT для локальной валидации. Backend использует только этот adapter. Competition передаёт batched logits, пропуская сервисные геометрии.

AF: VIIRS I1–I5, angles/valid и AUX; 39 выбранных признаков LightGBM, threshold 0.765. Выход mask uint8, probability float32, valid, fire_pixels, runtime, model_version; TRAIN добавляет gt_mask/error_map.

BS: Sentinel-2 pre/post с red-edge, Sentinel-1, AUX. Ансамбль NDVI Attention U-Net + DualHead U-Net → v004 physics/refiner → v006 component/refiner2. Пороги 0.3/0.8/0.2 неизменны. Выход mask uint8 0/1/2/3, burn_mask, burn_probability, severity_probability, valid, area, timings. Probability является оценкой pipeline, а не доказанной калиброванной вероятностью.

## Метрики и ограничения

Public score v006 0.8176; BS OOF all-valid 0.43552, strict 0.44677. Это разные метрики. Финальные модели обучены на всём TRAIN; локальные F1/IoU имеют маркировку in-sample. TEST не геопривязывается. Облака, слабая severity, смешанные пиксели и перенос на неизвестные регионы ограничивают надёжность.

AF invalid pixels исключаются из mask; BS valid policy сохранена byte-exact из GOLD. Ошибки GT nodata=255 исключаются из локальной матрицы и error overlay. Облака не интерпретируются как гарантированно обследованная территория.

## Поставка

Manifest: `ml/artifacts/manifest.json`. Seed исследовательских training-конфигов 42. Интеграция не переобучала модели. Torch нейросеть изолирована от LightGBM; device автоматически CUDA → MPS → CPU. Межплатформенная битовая идентичность не обещается; используйте `--verify-against` для своей среды.
