# Production weights

CURRENT GOLD: **v006**, previous stable: v005. `manifest.json` — authoritative registry: SHA256, размеры, входы, выходы, пороги, provenance и runtime. Все 7 текущих файлов включены в эту Git-поставку (~83 MB); дополнительная копия v005 сохранена для истории.

| Ключ | Путь от KROMA_ML_ARTIFACTS_PATH |
| --- | --- |
| af_model | af/af_fulltrain_model.joblib |
| bs_neural_ndvi | bs/neural/bs_full_ndvi_ohem40.pt |
| bs_neural_dual | bs/neural/bs_full_dual.pt |
| bs_thresholds | bs/physics_thresholds.json |
| bs_v004_refiner | bs/v004_refiner.txt |
| bs_component | bs/v006/component_full_v006_rededge.txt |
| bs_refiner2 | bs/v006/refiner2_full_v006_rededge.txt |

Проверка: `python scripts/mount_artifacts.py`. Копирование полного комплекта: `python scripts/mount_artifacts.py --source ml/artifacts --dest /path/to/bundle`. Затем `KROMA_ML_ARTIFACTS_PATH=/path/to/bundle`. Указанный root является единственным источником: скрытого fallback на research нет.

Если архив поставки исключил бинарные файлы, получите у команды **полный каталог ml/artifacts того же commit**, проверьте каждый SHA256 командой выше. Не переименовывайте произвольный `.pt` в ожидаемое имя. Не запускайте обучение ради подготовки production-весов. Проверка отсутствующих файлов: `/models`; при замене весов перезапустите backend.
