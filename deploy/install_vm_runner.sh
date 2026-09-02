#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/caisheng"
SERVICE_USER="caisheng"
SERVICE_GROUP="caisheng"
ENV_DIR="/etc/caisheng"
STATE_DIR="/var/lib/caisheng"
LOG_DIR="/var/log/caisheng"
UNIT_NAME="caisheng-monitor.service"
DASHBOARD_UNIT_NAME="caisheng-dashboard.service"

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: run this installer as root on the dedicated runner VM."
  exit 2
fi
if [[ ! -x "${APP_DIR}/.venv/bin/python" ]]; then
  echo "ERROR: locked Python environment is missing at ${APP_DIR}/.venv."
  exit 2
fi
if [[ ! -x "${APP_DIR}/scripts/run_persistent_job.sh" ]]; then
  echo "ERROR: CaiSheng must be installed at ${APP_DIR}."
  exit 2
fi
if ! command -v systemctl >/dev/null 2>&1; then
  echo "ERROR: systemd is required on the persistent runner VM."
  exit 2
fi

if ! getent group "${SERVICE_GROUP}" >/dev/null; then
  groupadd --system "${SERVICE_GROUP}"
fi
if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd \
    --system \
    --gid "${SERVICE_GROUP}" \
    --home-dir "${STATE_DIR}" \
    --shell /usr/sbin/nologin \
    "${SERVICE_USER}"
fi

install -d -o root -g "${SERVICE_GROUP}" -m 0750 "${ENV_DIR}"
install -d -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" -m 0750 "${STATE_DIR}" "${LOG_DIR}"
install -d -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" -m 0750 \
  "${APP_DIR}/data/runtime" "${APP_DIR}/data/evaluation"

if [[ ! -e "${ENV_DIR}/caisheng.env" ]]; then
  install -o root -g "${SERVICE_GROUP}" -m 0640 \
    "${APP_DIR}/deploy/caisheng.env.example" \
    "${ENV_DIR}/caisheng.env"
  echo "Created ${ENV_DIR}/caisheng.env from the safe preview template."
else
  echo "Preserving existing ${ENV_DIR}/caisheng.env."
fi

install -o root -g root -m 0644 \
  "${APP_DIR}/deploy/systemd/${UNIT_NAME}" \
  "/etc/systemd/system/${UNIT_NAME}"
install -o root -g root -m 0644 \
  "${APP_DIR}/deploy/systemd/${DASHBOARD_UNIT_NAME}" \
  "/etc/systemd/system/${DASHBOARD_UNIT_NAME}"

systemctl daemon-reload
systemctl enable "${UNIT_NAME}"
systemctl enable "${DASHBOARD_UNIT_NAME}"

echo "CaiSheng monitor installed but intentionally not started."
echo "1. Edit ${ENV_DIR}/caisheng.env and replace both REPLACE_ME values."
echo "2. Run: sudo -u ${SERVICE_USER} CAISHENG_ENV_FILE=${ENV_DIR}/caisheng.env ${APP_DIR}/scripts/run_persistent_job.sh preflight"
echo "3. Run reconciliation and inspect the fresh-account receipt."
echo "4. Start only in preview mode: systemctl start ${UNIT_NAME}"
echo "5. Start the private dashboard: systemctl start ${DASHBOARD_UNIT_NAME}"
echo "6. Access it with an SSH tunnel; never expose port 8080 publicly."
