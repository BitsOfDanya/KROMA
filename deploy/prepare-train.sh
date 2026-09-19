#!/usr/bin/env bash
# Install the official TRAIN rasters once in storage shared by all releases.
set -Eeuo pipefail

shared_root="${KROMA_SHARED_ROOT:-/opt/kroma/shared}"
train_root="${shared_root}/train"
bs_sample="bs/sentinel2_pre/BS_tr_000001_Sentinel-2_pre.tif"
af_sample="af/viirs/AF_tr_000001_VIIRS_I1-I5.tif"

if [[ -s "${train_root}/${bs_sample}" && -s "${train_root}/${af_sample}" ]]; then
  echo "Official TRAIN rasters are already installed."
  exit 0
fi

mkdir -p "$shared_root"
staging="$(mktemp -d "${shared_root}/train-install.XXXXXX")"
trap 'rm -rf "$staging"' EXIT

if [[ -n "${KROMA_TRAIN_SOURCE_ARCHIVE:-}" ]]; then
  echo "Extracting official TRAIN from local archive."
  tar -xf "$KROMA_TRAIN_SOURCE_ARCHIVE" -C "$staging" --strip-components=1 --no-same-owner
else
  available_kb="$(df -Pk "$shared_root" | awk 'NR == 2 {print $4}')"
  if (( available_kb < 3145728 )); then
    echo "Official TRAIN needs at least 3 GiB free in ${shared_root}." >&2
    exit 1
  fi
  public_key="https://disk.yandex.ru/d/-rpmevTflbXZQg"
  for attempt in 1 2 3; do
    echo "Downloading official TRAIN archive (attempt ${attempt}/3)."
    href="$({
      curl -fsS --retry 12 --retry-all-errors --retry-delay 5 --get \
        --data-urlencode "public_key=${public_key}" \
        --data-urlencode 'path=/fire-train-renamed.tar' \
        'https://cloud-api.yandex.net/v1/disk/public/resources/download'
    } | python3 -c 'import json,sys; print(json.load(sys.stdin)["href"])')"
    if curl -fLsS --max-time 1800 "$href" \
      | tar -xf - -C "$staging" --strip-components=1 --no-same-owner; then
      break
    fi
    rm -rf "$staging"
    mkdir -p "$staging"
    if (( attempt == 3 )); then
      echo "Could not download the official TRAIN archive." >&2
      exit 1
    fi
    sleep 10
  done
fi

if [[ ! -s "${staging}/${bs_sample}" || ! -s "${staging}/${af_sample}" ]]; then
  echo "Official TRAIN archive has an unexpected layout or is incomplete." >&2
  exit 1
fi

if [[ -d "$train_root" ]]; then
  rmdir "$train_root" 2>/dev/null || {
    echo "${train_root} contains incomplete data; move it before installation." >&2
    exit 1
  }
fi
mv "$staging" "$train_root"
trap - EXIT
echo "Official TRAIN rasters installed in ${train_root}."
