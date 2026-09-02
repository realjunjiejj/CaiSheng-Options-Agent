#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-}"
ENV_FILE="${CAISHENG_ENV_FILE:-/etc/caisheng/caisheng.env}"

if [[ "${MODE}" != "dashboard" && "${MODE}" != "scan" && "${MODE}" != "monitor" && "${MODE}" != "supervise" && "${MODE}" != "reconcile" && "${MODE}" != "preflight" && "${MODE}" != "competition-arm" && "${MODE}" != "competition-disarm" && "${MODE}" != "competition-status" ]]; then
  echo "ERROR: expected dashboard, scan, monitor, supervise, reconcile, preflight, competition-arm, competition-disarm, or competition-status."
  exit 2
fi
if [[ ! -r "${ENV_FILE}" ]]; then
  echo "ERROR: protected environment file is not readable: ${ENV_FILE}"
  exit 2
fi

# The environment file is administrator-controlled and must be mode 0600.
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
export PATH="${APP_DIR}/.venv/bin:${PATH}"
cd "${APP_DIR}"
exec "${SCRIPT_DIR}/cloud_run_entrypoint.sh" "${MODE}"
