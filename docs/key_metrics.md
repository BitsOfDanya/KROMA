# Ключевые метрики

## Public leaderboard

| v001 | v002 | v003 | v004 | v005 | GOLD v006 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.5526 | 0.6457 | 0.7298 | 0.7406 | 0.8127 | **0.8176** |

Значения подтверждены командой. BS OOF v006: all-valid 0.43552, strict 0.44677. Локальный TRAIN F1/IoU in-sample не используется как оценка обобщения.

## Проверка production inference

Main baseline `bf088ec`; integration 2026-09-19. `python inference.py --data-dir data/test --output tmp/integration-submission.csv --workers 2 --threads 2 --verify-against artifacts/submissions/submission_v006.csv`.

- 447 строк: 180 AF + 267 BS class rows (89 chips × 3).
- Ошибок чипов: 0. Полный CSV-identical `submission_v006.csv`.
- AF fire pixels: 3977. BS burn pixels: 3,900,362.
- Runtime 452.88 с; neural batch 19.81 с; AF + BS postprocessing 432.49 с; сборка/валидация 0.52 с.
- RLE roundtrip, template order/keys, no NaN, no duplicates, no overlap.
- Прямой service→RLE: BS_te_000001 / 000020 / 000089 совпали с v006.

[Машинный протокол](qa/inference-verification.json). Измерение локальное, при параллельной нагрузке; это не SLA.

## Service runtime

TRAIN `AF_tr_000001` / `BS_tr_000001`, HTTP на локальном uvicorn. Холодный запрос включает загрузку моделей/данных. Cache хранит исходные model/vectorize timings, `total` отражает текущий вызов.

| Операция | Измерено |
| --- | ---: |
| AF cold HTTP | 4455.6 ms |
| AF cached HTTP | 5.2 ms |
| BS cold HTTP | 16034.0 ms |
| BS cached HTTP | 69.5 ms |
| BS vectorize | 147.6 ms |
| AF GeoJSON / Shapefile | 5.1 / 5.0 ms |
| BS GeoJSON / Shapefile | 23.0 / 11.8 ms |
| Prepared model analysis | 1702.3 ms |
| Prepared reference analysis | 765.2 ms |

[Полный протокол](qa/api-verification.json) сохраняет metadata исходного замера до сокращения display version AF до стабильного `af-v001`; веса и предсказания не менялись.

## Dataset / area

Official TRAIN: 644 сцены, 420 AF / 224 BS. Builder читает GeoTIFF, а не фиксирует counts вручную. Compact demo: 3 BS + 3 AF; model 2916 зон / 81 point, reference 1757 зон.

20×20 м = 400 м² = **0.04 га**. `BS_tr_000001`: prediction 462.12 га = low 461.52 + moderate 0.60 + high 0. GT 454.8 га. Prepared bbox-analysis использует EPSG:6933 и может немного отличаться от площади номинальных UTM-пикселей; оба метода явно указаны.
