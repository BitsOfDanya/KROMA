# ML

Production contract: `kroma_ml.service.predict_af` / `predict_bs`. CURRENT GOLD v006. Competition CLI: `python inference.py --data-dir data/test --output tmp/submission.csv`. Backend и competition используют один adapter. Полный запуск, веса, API и ограничения — в [README](../README.md); описание моделей — [model card](../docs/model_card.md); перенос из исследований — [handoff](../docs/ml_handoff.md).

## Исследования и обучение

В product integration обучение не выполнялось. Исторические training-программы и результаты сохранены в `research/experiments` и [research/report.md](../research/report.md).

AF full-train bundle воспроизводится исследовательским `python research/experiments/af_final_model.py` при наличии TRAIN и описанных в отчёте кэшей hard negatives. BS training-контракт доступен через `python research/experiments/bs_track.py --help`; конфигурации ансамбля и сохранённые normalization/channel_names перечислены в checkpoint metadata. Full refiners строились последовательно v004 → v005 → red-edge v006; `research/experiments/bs_v006_infer.py` содержит обучение и требует OOF/cache inputs. Это исследовательская цепочка, не команда установки production.

Для запуска готовой модели достаточно 7 файлов из `artifacts/manifest.json`. Файлы raw/OOF в `data/processed` не нужны inference. Архивные DBSCAN/thermal-memory/priority модули сохранены как исследовательская история; LIVE backend не выдаёт их за обученный `P(real wildfire)`.
