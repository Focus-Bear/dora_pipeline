#!/usr/bin/env bash
# upload-to-r2.sh — Upload DORA data files to Cloudflare R2 via Wrangler
#
# Usage:
#   bash scripts/upload-to-r2.sh [--dry-run]
#
# Required environment variables:
#   CLOUDFLARE_API_TOKEN   — CF API token with R2 write permission
#   CLOUDFLARE_ACCOUNT_ID  — Cloudflare account ID
#   R2_BUCKET_NAME         — R2 bucket name (e.g. dora-pipeline-data)
#
# Optional:
#   DRY_RUN=1              — Print commands without executing (or pass --dry-run flag)

set -euo pipefail

DRY_RUN="${DRY_RUN:-0}"
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

# Validate required env vars
for var in CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID R2_BUCKET_NAME; do
  if [[ -z "${!var:-}" ]]; then
    echo "ERROR: $var is not set" >&2
    exit 1
  fi
done

DATA_FILES=(
  dora.json
  dora.sqlite
  repo_summary.csv
  repo_summary_7d.csv
  repo_summary_30d.csv
)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=== R2 Upload Script ==="
echo "Bucket: ${R2_BUCKET_NAME}"
echo "Dry run: ${DRY_RUN}"
echo ""

upload_file() {
  local file="$1"
  local key="${2:-$(basename "$file")}"
  local full_path="${REPO_ROOT}/${file}"

  if [[ ! -f "$full_path" ]]; then
    echo "⚠️  Skipping ${file} (not found)"
    return 0
  fi

  # Determine content type
  local content_type_arg=""
  case "$file" in
    *.json) content_type_arg="--content-type application/json" ;;
    *.csv)  content_type_arg="--content-type text/csv" ;;
  esac

  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[DRY RUN] wrangler r2 object put \"${R2_BUCKET_NAME}/${key}\" --file=\"${full_path}\" ${content_type_arg} --remote"
  else
    echo "⬆️  Uploading ${file} → r2://${R2_BUCKET_NAME}/${key}"
    # shellcheck disable=SC2086
    wrangler r2 object put "${R2_BUCKET_NAME}/${key}" --file="${full_path}" ${content_type_arg} --remote
    echo "✅ Done: ${key}"
  fi
}

for data_file in "${DATA_FILES[@]}"; do
  upload_file "$data_file"
done

echo ""
if [[ "$DRY_RUN" == "1" ]]; then
  echo "=== Dry run complete. No files were uploaded. ==="
else
  echo "=== Upload complete ==="
fi
