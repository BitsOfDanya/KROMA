# Стабильный demo KROMA

## Подготовка

1. Выполнить README quickstart; `/health`: status ok, AF/BS ready; `/api/v1/analysis/readiness`: ready.
2. Подключить TRAIN, проверить `/api/v1/datasets/train`: AF 420, BS 224. Если исходников нет, показывать только честно подписанный prepared-анализ, без обещания PRE/POST/inference.
3. Открыть `/predict`, заранее выполнить `BS_tr_000001` и `AF_tr_000001`, чтобы прогреть процесс и кэш. Интернет нужен для подложки карты.

## Показ

1. **Overview** — существующая карта, AOI, кластеры TRAIN; пояснить отличие SCENARIO и RAW FIRMS.
2. **Events** — открыть сценарное событие и evidence/timeline. Явно назвать SCENARIO; не связывать его с конкурсным TRAIN.
3. **Data** — OFFICIAL TRAIN, 420 AF / 224 BS, выбрать `BS_tr_000001`.
4. **Inspector** — PRE ↔ POST slider, GT severity, AUX / physics с dNBR и landcover. Нажать «Модель», показать in-sample disclaimer, затем Errors.
5. **Scene on map** — выбранная сцена, GT / PRED / ERROR. Цвета error: FP красный, FN синий, severity mismatch жёлтый, AF TP зелёный.
6. **Predict** — выбрать BS chip, запустить. Для `BS_tr_000001`: 462.12 га, low 461.52, moderate 0.60, high 0. Маска не является прогнозом будущего пожара.
7. **Export** — GeoJSON, Shapefile ZIP (внутри .prj/.cpg), NPZ masks/probability.
8. **Analysis** — выбрать `kroma-official-train-model@v006`, применить пример bbox/dates, выполнить. Показать dataset provenance, severity distribution и JSON/CSV/Shapefile.
9. **Swagger** — `/docs`: выполнить `/models`, `/datasets/train`, `/analysis`; показать согласованный result_id у exports.
10. **Research** — v001…v006 leaderboard и ограничения. Public score не сравнивать с локальным in-sample F1.

## Если что-то недоступно

Нет весов → health жив, model readiness false; не обещать prediction. Нет TRAIN → prepared model/reference остаются доступны. Нет FIRMS key → LIVE offline; использовать SCENARIO и TRAIN с маркировкой. Нет сети тайлов → статистика/экспорт/API работают, подложка карты может отсутствовать.
