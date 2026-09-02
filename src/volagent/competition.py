"""Time-limited, account-bound authorization for autonomous paper competition orders."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import math
from pathlib import Path
from typing import Any

from volagent.config import PROJECT_ROOT, VolAgentSettings
from volagent.errors import ConfigurationError


SCHEMA_VERSION = "caisheng.competition_arm.v1"


def _lease_path(path: str | Path) -> Path:
    target = Path(path)
    return target if target.is_absolute() else PROJECT_ROOT / target


def _canonical_hash(payload: dict[str, Any]) -> str:
    """Hash JSON-ready controls without importing the domain/provenance graph."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def competition_config_hash(settings: VolAgentSettings) -> str:
    """Hash only decision, risk, execution, and competition controls—never credentials."""
    payload = {
        "data_mode": settings.volagent_data_mode,
        "paper_trade": settings.alpaca_paper_trade,
        "forecast": settings.forecast.model_dump(mode="json"),
        "risk": settings.risk.model_dump(mode="json"),
        "mandate": settings.mandate.model_dump(mode="json"),
        "execution": settings.execution.model_dump(mode="json"),
        "competition": settings.competition.model_dump(mode="json"),
    }
    return _canonical_hash(payload)


def _account_fingerprint(paper_account_id: str) -> str:
    if not paper_account_id.strip():
        raise ConfigurationError("Competition arming requires a verified paper account ID.")
    return _canonical_hash({"paper_account_id": paper_account_id.strip()})


def _lease_hash(payload: dict[str, Any], secret: str) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "lease_hash"}
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), default=str)
    return hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def _sanitized(payload: dict[str, Any], *, status: str, authorized: bool, reason: str) -> dict[str, Any]:
    return {
        "schema_version": payload.get("schema_version", SCHEMA_VERSION),
        "status": status,
        "submission_authorized": authorized,
        "reason": reason,
        "issued_at": payload.get("issued_at"),
        "expires_at": payload.get("expires_at"),
        "revoked_at": payload.get("revoked_at"),
        "starting_nav": payload.get("starting_nav"),
        "current_equity_at_arm": payload.get("current_equity_at_arm"),
        "risk_limits": payload.get("risk_limits", {}),
        "paper_only": payload.get("paper_only", True),
        "lease_hash": payload.get("lease_hash", ""),
    }


def issue_competition_lease(
    *,
    path: str | Path,
    settings: VolAgentSettings,
    paper_account_id: str,
    starting_nav: float,
    current_equity: float,
    now: datetime | None = None,
    duration: timedelta | None = None,
) -> dict[str, Any]:
    """Issue an atomic paper-only authorization receipt without submitting an order."""
    issued_at = now or datetime.now(timezone.utc)
    if issued_at.tzinfo is None:
        issued_at = issued_at.replace(tzinfo=timezone.utc)
    duration = duration or timedelta(hours=settings.competition.arm_duration_hours)
    maximum_duration = timedelta(hours=settings.competition.arm_duration_hours)
    if duration <= timedelta(0) or duration > maximum_duration:
        raise ConfigurationError(
            f"Competition authorization duration must be greater than zero and no more than {settings.competition.arm_duration_hours} hours."
        )
    if not settings.competition.enabled:
        raise ConfigurationError("Competition mode is not enabled in this configuration.")
    if settings.volagent_data_mode != "live":
        raise ConfigurationError("Competition arming requires live market-data mode.")
    if not settings.execution.paper_only or not settings.alpaca_paper_trade:
        raise ConfigurationError("Competition arming is restricted to the Alpaca paper endpoint.")
    if not settings.execution.allow_order_submission:
        raise ConfigurationError("Competition configuration has order submission disabled.")
    if settings.execution.require_human_approval:
        raise ConfigurationError("Autonomous competition arming requires human approval to be disabled.")
    if not math.isclose(float(starting_nav), 100_000.0, abs_tol=0.01):
        raise ConfigurationError("Competition starting NAV must be exactly $100,000.")
    if not math.isfinite(float(current_equity)) or float(current_equity) <= 0.0:
        raise ConfigurationError("Competition arming requires a fresh positive account equity.")
    if not settings.alpaca_secret_key:
        raise ConfigurationError("Competition arming requires the Alpaca paper secret for receipt authentication.")

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "issued_at": issued_at.astimezone(timezone.utc).isoformat(),
        "expires_at": (issued_at + duration).astimezone(timezone.utc).isoformat(),
        "account_fingerprint": _account_fingerprint(paper_account_id),
        "config_hash": competition_config_hash(settings),
        "starting_nav": float(starting_nav),
        "current_equity_at_arm": float(current_equity),
        "paper_only": True,
        "risk_limits": {
            "recommended_loss_per_trade": 100_000.0 * settings.risk.recommended_risk_nav_pct,
            "hard_loss_per_trade": 100_000.0 * settings.risk.hard_max_risk_nav_pct,
            "max_open_strategies": settings.mandate.max_open_strategies,
            "max_new_entries_per_day": settings.mandate.max_new_entries_per_day,
            "daily_loss_halt": settings.mandate.daily_loss_halt_dollars,
            "drawdown_halt_pct": settings.mandate.drawdown_halt_pct,
        },
    }
    payload["lease_hash"] = _lease_hash(payload, settings.alpaca_secret_key)
    target = _lease_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(target)
    return _sanitized(payload, status="ARMED", authorized=True, reason="Time-limited paper authorization active")


def revoke_competition_lease(
    *,
    path: str | Path,
    settings: VolAgentSettings,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Atomically revoke new-entry authority without stopping position monitoring."""
    if not settings.alpaca_secret_key:
        raise ConfigurationError(
            "Competition disarming requires the Alpaca paper secret for receipt authentication."
        )

    target = _lease_path(path)
    previous_lease_hash = ""
    if target.exists():
        try:
            previous_payload = json.loads(target.read_text())
            previous_lease_hash = str(previous_payload.get("lease_hash", ""))
        except (OSError, json.JSONDecodeError):
            previous_lease_hash = "unreadable"

    revoked_at = now or datetime.now(timezone.utc)
    if revoked_at.tzinfo is None:
        revoked_at = revoked_at.replace(tzinfo=timezone.utc)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "revoked": True,
        "revoked_at": revoked_at.astimezone(timezone.utc).isoformat(),
        "paper_only": True,
        "previous_lease_hash": previous_lease_hash,
    }
    payload["lease_hash"] = _lease_hash(payload, settings.alpaca_secret_key)

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(target)
    return _sanitized(
        payload,
        status="DISARMED",
        authorized=False,
        reason="Operator revoked new-entry authorization",
    )


def read_competition_status(
    *,
    path: str | Path,
    settings: VolAgentSettings,
    paper_account_id: str | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate lease integrity, account binding, config binding, and expiration."""
    target = _lease_path(path)
    if not target.exists():
        return _sanitized({}, status="DISARMED", authorized=False, reason="No competition authorization receipt")
    try:
        payload = json.loads(target.read_text())
    except (OSError, json.JSONDecodeError):
        return _sanitized({}, status="BLOCKED", authorized=False, reason="Competition authorization receipt is unreadable")

    if not settings.alpaca_secret_key:
        return _sanitized(payload, status="BLOCKED", authorized=False, reason="Competition receipt authentication key is unavailable")
    expected_hash = _lease_hash(payload, settings.alpaca_secret_key)
    if payload.get("schema_version") != SCHEMA_VERSION or not hmac.compare_digest(
        str(payload.get("lease_hash", "")), expected_hash
    ):
        return _sanitized(payload, status="BLOCKED", authorized=False, reason="Competition authorization integrity check failed")
    if payload.get("revoked") is True:
        return _sanitized(
            payload,
            status="DISARMED",
            authorized=False,
            reason="Operator revoked new-entry authorization",
        )
    if not paper_account_id or payload.get("account_fingerprint") != _account_fingerprint(paper_account_id):
        return _sanitized(payload, status="BLOCKED", authorized=False, reason="Paper account binding mismatch")
    if payload.get("config_hash") != competition_config_hash(settings):
        return _sanitized(payload, status="BLOCKED", authorized=False, reason="Competition configuration changed after arming")
    if not settings.competition.enabled or not settings.execution.allow_order_submission:
        return _sanitized(payload, status="BLOCKED", authorized=False, reason="Competition submission switch is disabled")
    if settings.execution.require_human_approval or not settings.execution.paper_only or not settings.alpaca_paper_trade:
        return _sanitized(payload, status="BLOCKED", authorized=False, reason="Paper-only autonomous execution invariants failed")

    checked_at = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    try:
        expires_at = datetime.fromisoformat(str(payload["expires_at"]))
    except (KeyError, ValueError):
        return _sanitized(payload, status="BLOCKED", authorized=False, reason="Competition authorization expiration is invalid")
    if checked_at.astimezone(timezone.utc) >= expires_at.astimezone(timezone.utc):
        return _sanitized(payload, status="EXPIRED", authorized=False, reason="Competition authorization expired")
    return _sanitized(payload, status="ARMED", authorized=True, reason="Time-limited paper authorization active")


def competition_submission_permitted(
    *,
    settings: VolAgentSettings,
    status: dict[str, Any],
    is_live_mode: bool,
) -> bool:
    """Return the single entry-submission decision used by the lifecycle."""
    return bool(
        is_live_mode
        and settings.execution.paper_only
        and settings.alpaca_paper_trade
        and settings.execution.allow_order_submission
        and not settings.execution.require_human_approval
        and (
            not settings.competition.lease_required
            or status.get("submission_authorized") is True
        )
    )
