#!/usr/bin/env bash
set -euo pipefail

# CaiSheng unified container and persistent-host entrypoint.

PORT="${PORT:-8080}"
DATA_DIR="${DATA_DIR:-/tmp/caisheng}"
CAISHENG_BIND_HOST="${CAISHENG_BIND_HOST:-0.0.0.0}"
MODE="${1:-streamlit}"

echo "🚀 Starting CaiSheng (Options Alpha) [mode=${MODE}, port=${PORT}]"
mkdir -p "${DATA_DIR}"

assert_persistent_execution_host() {
  if [[ -n "${K_SERVICE:-}" || -n "${CLOUD_RUN_JOB:-}" || -n "${CLOUD_RUN_EXECUTION:-}" ]]; then
    echo "ERROR: authoritative SQLite lifecycle commands are disabled on Cloud Run."
    echo "Run this mode on the single persistent execution host."
    exit 2
  fi
}

case "${MODE}" in
  streamlit|dashboard)
    if [[ "${MODE}" == "dashboard" ]]; then
      assert_persistent_execution_host
    fi
    echo "📈 Launching CaiSheng cockpit on ${CAISHENG_BIND_HOST}:${PORT}..."
    exec streamlit run app.py \
      --server.port="${PORT}" \
      --server.address="${CAISHENG_BIND_HOST}" \
      --server.headless=true
    ;;

  mcp|http|streamable-http)
    echo "⚡ Launching MCP Streamable HTTP service on port ${PORT}..."
    exec python -c "from volagent.data.alpaca_mcp import AlpacaMCPService; AlpacaMCPService().run_streamable_http_server(host='0.0.0.0', port=${PORT})"
    ;;

  sse)
    echo "⚡ Launching legacy MCP SSE service on port ${PORT}..."
    exec python -c "from volagent.data.alpaca_mcp import AlpacaMCPService; AlpacaMCPService().run_sse_server(host='0.0.0.0', port=${PORT})"
    ;;

  preflight)
    assert_persistent_execution_host
    echo "✈️ Running preflight receipt..."
    exec python cli.py --preflight
    ;;

  reconcile)
    assert_persistent_execution_host
    echo "⚖️ Running daily reconciliation receipt..."
    exec python cli.py --reconcile
    ;;

  competition-arm)
    assert_persistent_execution_host
    echo "🔒 Arming time-limited paper-only competition mode..."
    exec python cli.py --competition-arm --competition-config config/competition.yaml
    ;;

  competition-disarm)
    assert_persistent_execution_host
    echo "🛑 Revoking new-entry authorization; position monitoring remains active..."
    exec python cli.py --competition-disarm --competition-config config/competition.yaml
    ;;

  competition-status)
    assert_persistent_execution_host
    exec python cli.py --competition-status --competition-config config/competition.yaml
    ;;

  scan|lifecycle)
    assert_persistent_execution_host
    echo "🔄 Running persistent-host lifecycle event scan..."
    exec python -m volagent.cloud_runtime scan
    ;;

  monitor)
    assert_persistent_execution_host
    echo "👁️ Running persistent-host order and position monitor..."
    exec python -m volagent.cloud_runtime monitor
    ;;

  supervise)
    assert_persistent_execution_host
    echo "🛡️ Starting continuous persistent-host risk monitor..."
    exec python -m volagent.cloud_runtime supervise
    ;;

  test)
    echo "❌ Tests are intentionally excluded from the production image."
    exit 2
    ;;

  *)
    echo "⚙️ Executing custom command: $*"
    exec "$@"
    ;;
esac
