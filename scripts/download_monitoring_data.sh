#!/usr/bin/env bash
# Скачать Мониторинг DATA с Яндекс.Диска в data/yandex/
# https://disk.yandex.ru/d/-rpmevTflbXZQg
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/data/yandex"
KEY="https://disk.yandex.ru/d/-rpmevTflbXZQg"
mkdir -p "$OUT"

download() {
  local path="$1" name="$2"
  echo "→ $name"
  local href
  href=$(curl -fsS "https://cloud-api.yandex.net/v1/disk/public/resources/download?public_key=$(python3 -c "import urllib.parse; print(urllib.parse.quote('''$KEY'''))")&path=$(python3 -c "import urllib.parse; print(urllib.parse.quote('''$path'''))")" | python3 -c "import sys,json; print(json.load(sys.stdin)['href'])")
  curl -fL --retry 3 -o "$OUT/$name" "$href"
  echo "✓ $OUT/$name ($(du -h "$OUT/$name" | cut -f1))"
}

download "/fire-aoi/fire_monitoring_aoi_shapefile.zip" "fire_monitoring_aoi_shapefile.zip"
download "/fire-test-renamed.tar" "fire-test-renamed.tar"
download "/fire-train-renamed.tar" "fire-train-renamed.tar"
echo "Готово."
