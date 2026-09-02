#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${1:-}"

case "${OUTPUT_DIR}" in
  ""|"/"|"."|"${PROJECT_ROOT}"|"${PROJECT_ROOT}/"*)
    echo "ERROR: refusing unsafe output directory: ${OUTPUT_DIR:-<empty>}"
    exit 1
    ;;
esac

if [[ -e "${OUTPUT_DIR}" ]] && [[ -n "$(find "${OUTPUT_DIR}" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
  echo "ERROR: output directory must not exist or must be empty: ${OUTPUT_DIR}"
  exit 1
fi

command -v rsync >/dev/null 2>&1 || {
  echo "ERROR: rsync is required to create the physical public allowlist."
  exit 1
}
command -v rg >/dev/null 2>&1 || {
  echo "ERROR: ripgrep is required for the public-context safety scan."
  exit 1
}

mkdir -p "${OUTPUT_DIR}"

PUBLIC_ROOT_FILES=(
  ".dockerignore"
  "Dockerfile"
  "README.md"
  "app.py"
  "cli.py"
  "pyproject.toml"
  "uv.lock"
)

for relative_path in "${PUBLIC_ROOT_FILES[@]}"; do
  cp "${PROJECT_ROOT}/${relative_path}" "${OUTPUT_DIR}/${relative_path}"
done

copy_tree() {
  local relative_path="$1"
  mkdir -p "${OUTPUT_DIR}/${relative_path}"
  rsync -a \
    --exclude='.DS_Store' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='*.egg-info/' \
    --exclude='*.db' \
    --exclude='*.db-shm' \
    --exclude='*.db-wal' \
    "${PROJECT_ROOT}/${relative_path}/" \
    "${OUTPUT_DIR}/${relative_path}/"
}

copy_tree "src"
copy_tree "config"
copy_tree "data/replay"

mkdir -p "${OUTPUT_DIR}/data/evaluation" "${OUTPUT_DIR}/docs" "${OUTPUT_DIR}/scripts"
for filename in oos_evaluation_results.json oos_evaluation_summary.csv oos_universe_manifest.json; do
  cp "${PROJECT_ROOT}/data/evaluation/${filename}" "${OUTPUT_DIR}/data/evaluation/${filename}"
done
cp "${PROJECT_ROOT}/docs/ONE_PAGE_WRITEUP.md" "${OUTPUT_DIR}/docs/ONE_PAGE_WRITEUP.md"
cp "${PROJECT_ROOT}/docs/ALPACA_TECHNOLOGY_LOCKBOX.md" "${OUTPUT_DIR}/docs/ALPACA_TECHNOLOGY_LOCKBOX.md"
cp "${PROJECT_ROOT}/scripts/cloud_run_entrypoint.sh" "${OUTPUT_DIR}/scripts/cloud_run_entrypoint.sh"
chmod 0755 "${OUTPUT_DIR}/scripts/cloud_run_entrypoint.sh"

if [[ -n "$(find "${OUTPUT_DIR}" -type l -print -quit)" ]]; then
  echo "ERROR: public build context contains a symbolic link."
  exit 1
fi

if find "${OUTPUT_DIR}" -type f \( \
  -name '.env' -o -name '.env.*' -o -name '*.db' -o -name '*.db-shm' -o -name '*.db-wal' \
\) -print -quit | grep -q .; then
  echo "ERROR: public build context contains a forbidden credential or state file."
  exit 1
fi

if rg -n --hidden \
  -e '-----BEGIN [A-Z ]*PRIVATE KEY-----' \
  -e 'AKIA[0-9A-Z]{16}' \
  -e 'sk-[A-Za-z0-9_-]{20,}' \
  "${OUTPUT_DIR}" >/dev/null; then
  echo "ERROR: public build context matched a high-confidence secret pattern."
  exit 1
fi

(
  cd "${OUTPUT_DIR}"
  find . -type f ! -name manifest.sha256 -print0 \
    | LC_ALL=C sort -z \
    | xargs -0 shasum -a 256
) > "${OUTPUT_DIR}/manifest.sha256"

echo "PUBLIC_BUILD_CONTEXT=${OUTPUT_DIR}"
echo "FILE_COUNT=$(find "${OUTPUT_DIR}" -type f | wc -l | tr -d ' ')"
echo "MANIFEST_SHA256=$(shasum -a 256 "${OUTPUT_DIR}/manifest.sha256" | awk '{print $1}')"
