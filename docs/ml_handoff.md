# ML → Product handoff

## Текущая версия

Исходный main интеграции: `bf088ec8f9cf6e7bf3029ad55463805f47853e30`. В нём уже были v006 артефакты, но service/manifest выбирали v005. Product integration подключила существующие red-edge maps/component statistics/ring contrast из исследования, сохранив float16 roundtrip, порядок признаков и правила 0.3/0.8/0.2.

Переобучение не проводилось. `weighted_comboloss_sampler.pt` по последующему указанию пользователя не исследовался и не подключался.

## Acceptance

Полный competition run: 180 AF, 89 BS, 447 строк, no failed chips. CSV-identical `artifacts/submissions/submission_v006.csv`. Три прямых service BS-прогона (`BS_te_000001`, `000020`, `000089`) дали те же RLE. TEST location/date не использовались. Timings и контрольная команда в `docs/key_metrics.md`.

## Следующий ML handoff

Передавайте комплект весов + manifest, SHA256, stable version, input/output contracts, threshold/feature order и эталонный submission. Backend вызывает адаптер и не должен импортировать Torch/LightGBM. Не заменяйте v006 файл молча: новая версия требует invalidation cache и новой версии prepared datasets, обновления UI/README/model card. После смены комплекта перезапускайте сервис.

Сохранено ограничение процесса: MPS Torch отдельно от LightGBM. Competition neural stage выполняется batch. Веб cache привязан к chip и version; persistent worker пока не применяется.
