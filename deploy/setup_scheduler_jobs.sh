#!/usr/bin/env bash
set -euo pipefail

echo "Cloud Run execution jobs are intentionally disabled."
echo "CaiSheng's authoritative ledger is SQLite and requires one persistent host."
echo "Cloud Storage FUSE is not a safe database backend, so this script will not"
echo "create scanner, monitor, reconciliation, or order-execution Cloud Run jobs."
echo "Use deploy/persistent_runner_crontab.example on one persistent VM, or implement"
echo "and verify a transactional"
echo "network database backend before enabling serverless execution."
exit 2
