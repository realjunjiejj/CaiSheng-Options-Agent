from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_docker_build_uses_lockfile_and_one_ingress_port():
    dockerfile = _read("Dockerfile")
    assert "COPY pyproject.toml uv.lock README.md" in dockerfile
    assert "uv sync --locked" in dockerfile
    assert "uv:latest" not in dockerfile
    assert dockerfile.count("python:3.12-slim@sha256:") == 2
    assert "uv:0.9.26@sha256:" in dockerfile
    assert "EXPOSE 8080" in dockerfile
    assert "EXPOSE 8080 8000" not in dockerfile
    assert "VOLAGENT_LEDGER_DB_PATH=/data" not in dockerfile


def test_cloud_run_deployment_splits_ui_and_private_mcp_without_gcs_sqlite():
    deploy = _read("deploy/deploy_cloud_run.sh")
    assert 'UI_SERVICE_NAME="${UI_SERVICE_NAME:-caisheng-ui}"' in deploy
    assert 'MCP_SERVICE_NAME="${MCP_SERVICE_NAME:-caisheng-mcp}"' in deploy
    assert "--allow-unauthenticated" in deploy
    assert "--no-allow-unauthenticated" in deploy
    assert "--set-secrets" in deploy
    assert "type=cloud-storage" not in deploy
    assert "execution_ledger.db" not in deploy
    assert "CAISHENG_PUBLIC_JUDGE_MODE=true" in deploy


def test_public_ui_deployment_is_credential_free_and_does_not_deploy_mcp():
    deploy = _read("deploy/deploy_public_ui.sh")

    assert 'UI_SERVICE_NAME="${UI_SERVICE_NAME:-caisheng-ui}"' in deploy
    assert "--allow-unauthenticated" in deploy
    assert "CAISHENG_PUBLIC_JUDGE_MODE=true" in deploy
    assert "VOLAGENT_ALLOW_ORDER_SUBMISSION=false" in deploy
    assert "--set-secrets" not in deploy
    assert "ALPACA_API_KEY" not in deploy
    assert "ALPACA_SECRET_KEY" not in deploy
    assert "MCP_SERVICE_NAME" not in deploy


def test_public_build_context_is_physical_allowlist_with_secret_and_state_guards():
    builder = _read("deploy/create_public_build_context.sh")

    assert "PUBLIC_ROOT_FILES=(" in builder
    assert 'copy_tree "src"' in builder
    assert 'copy_tree "config"' in builder
    assert 'copy_tree "data/replay"' in builder
    assert "data/runtime" not in builder
    assert "economic_evidence_receipt.json" not in builder
    assert "preflight_receipt.json" not in builder
    assert "reconciliation_receipt.json" not in builder
    assert "find \"${OUTPUT_DIR}\" -type l" in builder
    assert "manifest.sha256" in builder
    assert "refusing unsafe output directory" in builder


def test_cloud_entrypoint_never_starts_two_ingress_servers():
    entrypoint = _read("scripts/cloud_run_entrypoint.sh")
    assert "MCP_PID" not in entrypoint
    assert "run_streamable_http_server" in entrypoint
    assert "python -m volagent.cloud_runtime scan" in entrypoint
    assert "python -m volagent.cloud_runtime supervise" in entrypoint
    assert "assert_persistent_execution_host" in entrypoint


def test_scheduler_script_refuses_unsafe_cloud_run_execution_jobs():
    scheduler = _read("deploy/setup_scheduler_jobs.sh")
    assert "Cloud Run execution jobs are intentionally disabled" in scheduler
    assert "type=cloud-storage" not in scheduler
    assert "jobs create http" not in scheduler


def test_persistent_vm_monitor_is_systemd_managed_and_not_cron_polled():
    unit = _read("deploy/systemd/caisheng-monitor.service")
    cron = _read("deploy/persistent_runner_crontab.example")
    wrapper = _read("scripts/run_persistent_job.sh")

    assert "Restart=always" in unit
    assert "run_persistent_job.sh supervise" in unit
    assert "CAISHENG_ENV_FILE=/etc/caisheng/caisheng.env" in unit
    assert "*/5 9-16" not in cron
    assert '"supervise"' in wrapper


def test_private_operator_dashboard_is_loopback_only_and_shares_protected_runtime():
    unit = _read("deploy/systemd/caisheng-dashboard.service")
    wrapper = _read("scripts/run_persistent_job.sh")
    entrypoint = _read("scripts/cloud_run_entrypoint.sh")

    assert "CAISHENG_BIND_HOST=127.0.0.1" in unit
    assert "PORT=8080" in unit
    assert "run_persistent_job.sh dashboard" in unit
    assert "After=network-online.target caisheng-monitor.service" in unit
    assert "CAISHENG_ENV_FILE=/etc/caisheng/caisheng.env" in unit
    assert '"dashboard"' in wrapper
    assert 'cd "${APP_DIR}"' in wrapper
    assert "streamlit|dashboard)" in entrypoint
    assert '--server.address="${CAISHENG_BIND_HOST}"' in entrypoint


def test_persistent_runner_never_self_authorizes_before_scanning():
    cron = _read("deploy/persistent_runner_crontab.example")

    assert "CRON_TZ=" not in cron
    assert "host timezone must be America/New_York" in cron
    assert cron.count(">> /var/log/caisheng/scheduler.log 2>&1") == 3
    assert "competition-arm" not in cron
    first_scan = "20,50 10-14 * * 1-5 /opt/caisheng/scripts/run_persistent_job.sh scan"
    assert first_scan in cron


def test_operator_start_and_stop_controls_are_exposed_by_cli_and_runner():
    cli = _read("cli.py")
    wrapper = _read("scripts/run_persistent_job.sh")
    entrypoint = _read("scripts/cloud_run_entrypoint.sh")

    assert '"--competition-arm"' in cli
    assert '"--competition-disarm"' in cli
    assert '"--competition-status"' in cli
    assert '"competition-disarm"' in wrapper
    assert "competition-disarm)" in entrypoint


def test_vm_install_script_fails_closed_and_does_not_embed_secrets():
    installer = _read("deploy/install_vm_runner.sh")
    env_example = _read("deploy/caisheng.env.example")

    assert "set -euo pipefail" in installer
    assert 'systemctl enable "${UNIT_NAME}"' in installer
    assert 'systemctl start "${UNIT_NAME}"' not in installer
    assert "ALPACA_API_KEY=REPLACE_ME" in env_example
    assert "ALPACA_SECRET_KEY=REPLACE_ME" in env_example
