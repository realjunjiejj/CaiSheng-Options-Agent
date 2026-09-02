# CaiSheng Cloud Deployment

This deployment deliberately separates the judge-facing presentation plane from
the order-execution plane.

## Architecture

```text
Judges ──public HTTPS──> caisheng-ui (Cloud Run, Streamlit, replay/read-only)

Operators/agents ──authenticated HTTPS──> caisheng-mcp
                                         (Cloud Run, /mcp, paper account reads)

Persistent runner host ──> Alpaca Paper Trading API
        │
        ├── durable local SQLite ledger
        ├── private loopback operator dashboard (SSH tunnel only)
        ├── 15:30 ET confirmed-AMC scan
        ├── continuous 20-second order/position monitoring
        └── 16:15 ET reconciliation
```

Cloud Run routes one ingress port per service. UI and MCP are therefore separate
services built from the same immutable image. The public UI receives no Alpaca
credentials. MCP is private, requires Google IAM authentication, and keeps order
submission disabled.

The authoritative SQLite ledger is **not** mounted through Cloud Storage FUSE.
Cloud Storage FUSE does not provide the locking and patch semantics required by
SQLite. Until CaiSheng has a verified transactional network-database backend,
autonomous execution must run on one persistent host.

## Prerequisites

Enable the required services:

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  iam.googleapis.com \
  secretmanager.googleapis.com
```

Create paper-trading secrets if they do not already exist:

```bash
printf '%s' 'YOUR_PAPER_API_KEY' | \
  gcloud secrets create caisheng_alpaca_api_key --data-file=-
printf '%s' 'YOUR_PAPER_SECRET_KEY' | \
  gcloud secrets create caisheng_alpaca_secret_key --data-file=-
```

Never put credentials in the image, repository, shell history, or public UI.

## Build and deploy Cloud Run services

Use an immutable Git SHA tag:

```bash
export PROJECT_ID='YOUR_PROJECT_ID'
export REGION='us-central1'
export TAG="$(git rev-parse --short=12 HEAD)"
export MCP_INVOKER_MEMBER='user:YOUR_GOOGLE_ACCOUNT@example.com'

./deploy/build_and_push.sh
./deploy/deploy_cloud_run.sh
```

The deployment creates:

- `caisheng-ui`: public Streamlit judge cockpit, replay/read-only.
- `caisheng-mcp`: private Streamable HTTP MCP endpoint at `/mcp`.

The MCP runtime receives Alpaca paper credentials through Secret Manager. It
does not receive permission to submit orders.

## Invoke the private MCP service

Fetch the URL and an identity token:

```bash
MCP_URL="$(gcloud run services describe caisheng-mcp \
  --region="${REGION}" --format='value(status.url)')"
TOKEN="$(gcloud auth print-identity-token)"

curl -i "${MCP_URL}/healthz" \
  -H "Authorization: Bearer ${TOKEN}"
```

Your remote MCP client must support an `Authorization: Bearer <Google identity
token>` header. Do not make the service unauthenticated to accommodate a client
that cannot authenticate; use an authenticated local proxy instead.

Legacy SSE remains available as a separate container mode for local compatibility:

```bash
docker run --rm -p 8000:8080 caisheng-local sse
```

Streamable HTTP `/mcp` is the supported Cloud Run transport.

## Local container verification

```bash
docker build -t caisheng-local .

# UI
docker run --rm -p 8080:8080 caisheng-local streamlit

# MCP; provide paper credentials only to this private local process
docker run --rm -p 8000:8080 \
  -e ALPACA_API_KEY \
  -e ALPACA_SECRET_KEY \
  caisheng-local streamable-http
```

Expected health endpoints:

- UI: `http://localhost:8080/_stcore/health`
- MCP: `http://localhost:8000/healthz`
- MCP protocol: `http://localhost:8000/mcp`

## Persistent execution runner

Install the repository and its locked environment on one VM or other host with a
persistent filesystem. Put runtime configuration in a root-owned environment
file, not in Git:

```dotenv
ALPACA_API_KEY=paper-key
ALPACA_SECRET_KEY=paper-secret
ALPACA_PAPER_TRADE=true
VOLAGENT_DATA_MODE=live
VOLAGENT_LEDGER_DB_PATH=/var/lib/caisheng/execution_ledger.db
CAISHENG_RUNTIME_LOCK_PATH=/var/lib/caisheng/runtime.lock
CAISHENG_SUPERVISOR_LOCK_PATH=/var/lib/caisheng/monitor-supervisor.lock
CAISHENG_HEARTBEAT_PATH=/var/lib/caisheng/monitor-heartbeat.json
CAISHENG_OPERATOR_AUDIT_PATH=/var/lib/caisheng/operator-actions.jsonl
CAISHENG_MONITOR_INTERVAL_SECONDS=20
CAISHENG_MONITOR_CYCLE_TIMEOUT_SECONDS=60
CAISHENG_EXECUTION_MODE=preview
VOLAGENT_ALLOW_ORDER_SUBMISSION=false
VOLAGENT_REQUIRE_HUMAN_APPROVAL=true
CAISHENG_EVENT_CALENDAR_PATH=/etc/caisheng/earnings_calendar.json
```

The calendar file must contain at least one confirmed AMC event with source
provenance:

```json
{
  "earnings_calendar": [
    {
      "symbol": "AAPL",
      "event_date": "2026-09-01",
      "timing": "amc",
      "confirmed": true,
      "source_url": "https://authoritative-source.example/events/aapl"
    }
  ]
}
```

The dedicated `caisheng` service user must be able to read this file. Protect it
with owner `root`, group `caisheng`, and mode `0640`; no other identity receives
access.

### Minimal VM installation

Use a non-Spot Debian VM with automatic restart enabled. Install the reviewed
repository at `/opt/caisheng`, create the locked virtual environment there, and
then run:

```bash
sudo /opt/caisheng/deploy/install_vm_runner.sh
sudoedit /etc/caisheng/caisheng.env
```

Set and verify the dedicated VM's system timezone before installing the example
crontab. Debian cron evaluates the schedule in the host timezone:

```bash
sudo timedatectl set-timezone America/New_York
timedatectl show --property=Timezone --value
```

The installer creates the unprivileged service user and durable directories,
installs `caisheng-monitor.service` and `caisheng-dashboard.service`, and enables
both for boot. It intentionally does **not** start either service and never
overwrites an existing environment file.

Run preflight and a preview cycle through the same protected environment-loading
wrapper used by the service and cron:

```bash
CAISHENG_ENV_FILE=/etc/caisheng/caisheng.env ./scripts/run_persistent_job.sh preflight
CAISHENG_ENV_FILE=/etc/caisheng/caisheng.env ./scripts/run_persistent_job.sh scan
```

After inspection, start the continuous monitor in preview mode:

```bash
sudo systemctl start caisheng-monitor.service
sudo systemctl status caisheng-monitor.service --no-pager
sudo journalctl -u caisheng-monitor.service -n 100 --no-pager
```

Start the operator dashboard on the VM. The systemd unit binds Streamlit only to
`127.0.0.1:8080`; do not add a public firewall rule for this port:

```bash
sudo systemctl start caisheng-dashboard.service
sudo systemctl status caisheng-dashboard.service --no-pager
```

Open the dashboard from an operator workstation through an authenticated Google
Cloud SSH tunnel:

```bash
gcloud compute ssh caisheng-runner \
  --project=YOUR_PROJECT_ID \
  --zone=us-central1-a \
  -- -N -L 8080:127.0.0.1:8080
```

Then browse to `http://127.0.0.1:8080`. The private dashboard uses the same
protected environment, durable ledger, signed competition lease, monitor
heartbeat, and canonical execution gateway as the runner. `Start Autonomous
Session` authorizes entries for a bounded lease but submits no order by itself.
`Run Live Scan Now` executes exactly one guarded lifecycle scan. `Stop New
Entries` revokes the lease while monitoring continues. `Emergency Halt` requires
an exact second confirmation, persists the halt, revokes the lease, and requests
cancellation of governed working entry orders without silently flattening open
positions. Every action is written to a signed hash-chained operator receipt.

Operator-armed autonomy keeps the monitor and scheduled analysis online while
requiring an explicit start command for new paper entries:

```bash
./scripts/run_persistent_job.sh competition-arm
./scripts/run_persistent_job.sh competition-status
./scripts/run_persistent_job.sh competition-disarm
```

Disarming revokes new-entry authority atomically. It does not stop monitoring or
risk-reducing exits for positions that already exist. The scheduler never renews
the authorization itself.

The service runs a monitor-only cycle every 20 seconds, publishes
`/var/lib/caisheng/monitor-heartbeat.json` atomically, and restarts after a
failure. A cycle failure trips the persistent halt to block new entries. The
monitor itself remains runnable during a halt so it can perform risk-reducing
exits. Each broker-monitoring cycle has a 60-second watchdog; a stuck Alpaca
request writes an error heartbeat, preserves the halt, and exits so systemd can
restart the supervisor instead of reporting a silently hung process.

Only after the dashboard proves a pristine $100,000 account, preflight binds the
new account to the new ledger, reconciliation is clean, restart tests pass, and
one human-approved lifecycle succeeds should all three flags be set together:

```dotenv
CAISHENG_EXECUTION_MODE=autonomous
VOLAGENT_ALLOW_ORDER_SUBMISSION=true
VOLAGENT_REQUIRE_HUMAN_APPROVAL=false
```

Paper-only enforcement remains non-bypassable in application configuration.

An example cron schedule for scans and reconciliation is provided in
`deploy/persistent_runner_crontab.example`. Monitoring is deliberately excluded
from cron because the systemd service owns continuous supervision. The lifecycle
runner uses Alpaca's exchange calendar and fails closed on holidays, early
closes, unavailable broker data, missing event data, or lifecycle errors.

## Why Cloud Run execution jobs are disabled

`deploy/setup_scheduler_jobs.sh` intentionally exits with an error. This prevents
an operator from recreating the previous unsafe topology where multiple Cloud Run
instances and jobs modified one SQLite file through Cloud Storage FUSE.

Re-enable serverless execution only after implementing and integration-testing a
transactional network database backend, distributed idempotency, concurrent
writer behavior, restart recovery, and two-way Alpaca reconciliation.
