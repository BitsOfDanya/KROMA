#!/usr/bin/env bash
# Скачать Мониторинг DATA с Яндекс.Диска (с resume)
# https://disk.yandex.ru/d/-rpmevTflbXZQg
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AOI_OUT="$ROOT/data/fire-aoi"
PUBLIC_OUT="$ROOT/frontend/public/data"
YANDEX_OUT="$ROOT/data/yandex"
KEY="https://disk.yandex.ru/d/-rpmevTflbXZQg"
mkdir -p "$AOI_OUT" "$PUBLIC_OUT" "$YANDEX_OUT"

href_for() {
  local path="$1"
  curl -fsS "https://cloud-api.yandex.net/v1/disk/public/resources/download?public_key=$(python3 -c "import urllib.parse; print(urllib.parse.quote('''$KEY'''))")&path=$(python3 -c "import urllib.parse; print(urllib.parse.quote('''$path'''))")" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['href'])"
}

download() {
  local path="$1" dest="$2"
  echo "→ $path"
  local href
  href=$(href_for "$path")
  curl -fL --retry 12 --retry-all-errors --continue-at - -o "$dest" "$href"
  echo "✓ $dest ($(du -h "$dest" | cut -f1))"
}

echo "== fire-aoi (территория мониторинга) =="
download "/fire-aoi/README.md" "$AOI_OUT/README.md"
download "/fire-aoi/fire_monitoring_aoi.geojson" "$AOI_OUT/fire_monitoring_aoi.geojson"
download "/fire-aoi/fire_monitoring_aoi.gpkg" "$AOI_OUT/fire_monitoring_aoi.gpkg"
download "/fire-aoi/fire_monitoring_aoi_shapefile.zip" "$AOI_OUT/fire_monitoring_aoi_shapefile.zip"
cp -f "$AOI_OUT/fire_monitoring_aoi.geojson" "$PUBLIC_OUT/fire_monitoring_aoi.geojson"
echo "✓ карта: $PUBLIC_OUT/fire_monitoring_aoi.geojson"

if [[ "${1:-}" == "--with-tars" ]]; then
  echo "== train/test чипы (крупные, с resume) =="
  download "/fire-test-renamed.tar" "$YANDEX_OUT/fire-test-renamed.tar"
  download "/fire-train-renamed.tar" "$YANDEX_OUT/fire-train-renamed.tar"
  echo "Ожидаемые размеры: test=920483840 (~878M), train=2305976320 (~2.14G)"
  ls -lh "$YANDEX_OUT"/*.tar
else
  echo "Чипы train/test пропущены (добавьте --with-tars)."
fi

echo "Готово."
