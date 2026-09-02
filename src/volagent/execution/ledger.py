from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any
import uuid
from zoneinfo import ZoneInfo

from volagent.domain.enums import ExecutionStatus
from volagent.errors import ExecutionError


def get_default_ledger_path() -> Path:
    """Resolve writable runtime database path outside source directory."""
    env_path = os.getenv("VOLAGENT_LEDGER_DB_PATH")
    if env_path:
        p = Path(env_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    app_dir = Path.home() / ".volagent"
    try:
        app_dir.mkdir(parents=True, exist_ok=True)
        return app_dir / "execution_ledger.db"
    except Exception:
        return get_fallback_ledger_path()


def get_fallback_ledger_path() -> Path:
    """Return a per-user writable fallback instead of a shared global DB."""
    fallback_dir = Path(tempfile.gettempdir()) / f"volagent-{os.getuid()}"
    fallback_dir.mkdir(parents=True, exist_ok=True)
    return fallback_dir / "execution_ledger.db"


LEDGER_DB_PATH = get_default_ledger_path()

# Canonical Legal State Transitions Map
LEGAL_TRANSITIONS: dict[str, set[str]] = {
    ExecutionStatus.PREVIEWED.value: {
        ExecutionStatus.APPROVED.value,
        ExecutionStatus.REJECTED.value,
        ExecutionStatus.CANCELED.value,
    },
    ExecutionStatus.APPROVED.value: {
        ExecutionStatus.INTENT_PERSISTED.value,
        ExecutionStatus.REJECTED.value,
        ExecutionStatus.CANCELED.value,
    },
    ExecutionStatus.INTENT_PERSISTED.value: {
        ExecutionStatus.SUBMITTING.value,
        ExecutionStatus.CANCELED.value,
    },
    ExecutionStatus.SUBMITTING.value: {
        ExecutionStatus.ACCEPTED.value,
        ExecutionStatus.UNKNOWN.value,
        ExecutionStatus.REJECTED.value,
        ExecutionStatus.PARTIALLY_FILLED.value,
        ExecutionStatus.FILLED.value,
        ExecutionStatus.CANCELED.value,
        ExecutionStatus.SIMULATED.value,
    },
    ExecutionStatus.UNKNOWN.value: {
        ExecutionStatus.ACCEPTED.value,
        ExecutionStatus.PARTIALLY_FILLED.value,
        ExecutionStatus.FILLED.value,
        ExecutionStatus.CANCELED.value,
        ExecutionStatus.REJECTED.value,
        ExecutionStatus.FAILED.value,
        ExecutionStatus.UNKNOWN.value,  # Idempotent recovery ping
    },
    ExecutionStatus.ACCEPTED.value: {
        ExecutionStatus.PARTIALLY_FILLED.value,
        ExecutionStatus.FILLED.value,
        ExecutionStatus.CANCELED.value,
        ExecutionStatus.REJECTED.value,
        ExecutionStatus.CLOSED.value,
    },
    ExecutionStatus.PARTIALLY_FILLED.value: {
        ExecutionStatus.PARTIALLY_FILLED.value,
        ExecutionStatus.FILLED.value,
        ExecutionStatus.CANCELED.value,
        ExecutionStatus.CLOSED.value,
    },
    ExecutionStatus.FILLED.value: {
        ExecutionStatus.CLOSED.value,
    },
    ExecutionStatus.SIMULATED.value: {
        ExecutionStatus.CLOSED.value,
    },
    ExecutionStatus.CANCELED.value: set(),
    ExecutionStatus.REJECTED.value: set(),
    ExecutionStatus.CLOSED.value: set(),
    ExecutionStatus.FAILED.value: set(),
}


class ExecutionLedger:
    """Thread-safe, atomic SQLite ledger enforcing legal transitions, append-only event auditing, logical exposure deduplication, and persistent halt."""

    def __init__(self, db_path: Path | str | None = None):
        explicit_path = db_path is not None or bool(os.getenv("VOLAGENT_LEDGER_DB_PATH"))
        self.db_path = Path(db_path) if db_path else get_default_ledger_path()
        try:
            self._init_db()
        except sqlite3.OperationalError:
            if explicit_path:
                raise
            self.db_path = get_fallback_ledger_path()
            self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS execution_ledger (
                    fingerprint TEXT PRIMARY KEY,
                    logical_exposure_key TEXT NOT NULL,
                    economic_fingerprint TEXT NOT NULL,
                    client_order_id TEXT UNIQUE NOT NULL,
                    approval_token TEXT UNIQUE NOT NULL,
                    strategy_id TEXT,
                    decision_id TEXT,
                    event_id TEXT,
                    model_version TEXT,
                    mandate_version TEXT,
                    decision_time_bucket TEXT,
                    status TEXT NOT NULL,
                    broker_target TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    limit_price REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    submitted_at TEXT,
                    broker_order_id TEXT,
                    filled_at TEXT,
                    filled_quantity INTEGER DEFAULT 0,
                    average_price REAL,
                    raw_broker_response TEXT,
                    error_message TEXT,
                    full_order_plan TEXT,
                    recovery_attempt_count INTEGER DEFAULT 0,
                    first_recovery_attempt_at TEXT,
                    last_recovery_attempt_at TEXT,
                    next_recovery_attempt_at TEXT,
                    recovery_deadline TEXT,
                    last_recovery_error TEXT,
                    last_recovery_evidence_id TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS execution_transition_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_fingerprint TEXT NOT NULL,
                    client_order_id TEXT NOT NULL,
                    approval_token TEXT NOT NULL,
                    from_status TEXT NOT NULL,
                    to_status TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    reason TEXT,
                    evidence_id TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS reconciliation_reports (
                    reconciliation_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    matched_orders_count INTEGER NOT NULL,
                    matched_positions_count INTEGER NOT NULL,
                    report_payload TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS runtime_halt_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    is_halted INTEGER NOT NULL DEFAULT 0,
                    reason TEXT,
                    halted_at TEXT,
                    evidence_id TEXT
                )
            """)
            conn.execute("INSERT OR IGNORE INTO runtime_halt_state (id, is_halted) VALUES (1, 0);")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS competition_metadata (
                    competition_id TEXT PRIMARY KEY,
                    starting_nav REAL NOT NULL,
                    strategy_version TEXT NOT NULL,
                    mandate_version TEXT NOT NULL,
                    start_timestamp TEXT NOT NULL,
                    paper_account_id TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    equity REAL NOT NULL,
                    cash REAL NOT NULL,
                    buying_power REAL NOT NULL,
                    initial_nav REAL NOT NULL,
                    high_water_equity REAL NOT NULL,
                    daily_realized_pl REAL NOT NULL,
                    daily_unrealized_pl REAL NOT NULL,
                    open_strategies_count INTEGER NOT NULL,
                    new_entries_today_count INTEGER NOT NULL,
                    reserved_risk_dollars REAL NOT NULL,
                    sector_reserved_risk TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    is_stale INTEGER NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS closed_trades (
                    trade_id TEXT PRIMARY KEY,

                    strategy_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    entry_order_id TEXT NOT NULL,
                    exit_order_id TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    gross_realized_pnl_dollars REAL NOT NULL,
                    fees_and_slippage REAL NOT NULL,
                    net_realized_pnl_dollars REAL NOT NULL,
                    realized_return_pct REAL NOT NULL,
                    max_loss_budget REAL NOT NULL,
                    risk_utilization_pct REAL NOT NULL,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT NOT NULL,
                    holding_hours REAL NOT NULL,
                    pre_event_expected_move REAL NOT NULL,
                    pre_event_implied_move REAL NOT NULL,
                    actual_post_event_move REAL NOT NULL,
                    outcome_label TEXT NOT NULL,
                    raw_payload TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS decision_records (
                    decision_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    status TEXT NOT NULL,
                    selected_action TEXT NOT NULL,
                    selected_strategy_id TEXT,
                    quantity INTEGER NOT NULL,
                    generated_at TEXT NOT NULL,
                    artifact_hash TEXT NOT NULL,
                    raw_payload TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS shadow_book_records (
                    shadow_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    selected_action TEXT NOT NULL,
                    selected_strategy_pnl REAL NOT NULL,
                    actual_post_event_move REAL NOT NULL,
                    actual_iv_crush_points REAL NOT NULL,
                    recorded_at TEXT NOT NULL,
                    raw_payload TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS benchmark_intents (
                    intent_id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL,
                    decision_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    decision_time TEXT NOT NULL,
                    exit_time TEXT NOT NULL,
                    receipt_hash TEXT NOT NULL,
                    raw_payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS benchmark_outcomes (
                    outcome_id TEXT PRIMARY KEY,
                    intent_id TEXT UNIQUE NOT NULL,
                    opportunity_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    settled_at TEXT NOT NULL,
                    receipt_hash TEXT NOT NULL,
                    raw_payload TEXT NOT NULL,
                    FOREIGN KEY(intent_id) REFERENCES benchmark_intents(intent_id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS mcp_audit_events (
                    event_id TEXT PRIMARY KEY,
                    tool_name TEXT NOT NULL,
                    decision_id TEXT,
                    sanitized_arguments TEXT NOT NULL,
                    result_status TEXT NOT NULL,
                    called_at TEXT NOT NULL,
                    raw_response TEXT NOT NULL
                )
            """)





            # Schema migration check
            existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(execution_ledger);").fetchall()}
            migrations = {
                "logical_exposure_key": "TEXT DEFAULT ''",
                "economic_fingerprint": "TEXT DEFAULT ''",
                "decision_id": "TEXT",
                "event_id": "TEXT",
                "model_version": "TEXT",
                "mandate_version": "TEXT",
                "decision_time_bucket": "TEXT",
                "full_order_plan": "TEXT",
                "recovery_attempt_count": "INTEGER DEFAULT 0",
                "first_recovery_attempt_at": "TEXT",
                "last_recovery_attempt_at": "TEXT",
                "next_recovery_attempt_at": "TEXT",
                "recovery_deadline": "TEXT",
                "last_recovery_error": "TEXT",
                "last_recovery_evidence_id": "TEXT",
            }
            for col, col_def in migrations.items():
                if col not in existing_cols:
                    conn.execute(f"ALTER TABLE execution_ledger ADD COLUMN {col} {col_def};")

            conn.execute("CREATE INDEX IF NOT EXISTS idx_logical_exp ON execution_ledger (logical_exposure_key);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_economic_fp ON execution_ledger (economic_fingerprint);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_client_order_id ON execution_ledger (client_order_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON execution_ledger (status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_fp ON execution_transition_events (order_fingerprint);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_benchmark_exit ON benchmark_intents (exit_time);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_benchmark_symbol ON benchmark_intents (symbol);")
            conn.commit()

    def _record_transition_event(
        self,
        conn: sqlite3.Connection,
        order_fingerprint: str,
        client_order_id: str,
        approval_token: str,
        from_status: str,
        to_status: str,
        actor: str,
        reason: str | None = None,
        evidence_id: str | None = None,
    ) -> None:
        """Insert immutable append-only transition event."""
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute("""
            INSERT INTO execution_transition_events
            (order_fingerprint, client_order_id, approval_token, from_status, to_status, timestamp, actor, reason, evidence_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (order_fingerprint, client_order_id, approval_token, from_status, to_status, now_iso, actor, reason, evidence_id))

    def _validate_transition(self, from_status: str, to_status: str) -> None:
        """Enforce canonical transition invariants."""
        allowed = LEGAL_TRANSITIONS.get(from_status, set())
        if to_status not in allowed:
            raise ExecutionError(
                f"Illegal state transition requested: '{from_status}' -> '{to_status}'. Allowed target states from '{from_status}': {sorted(list(allowed))}."
            )

    def is_system_halted(self) -> tuple[bool, str | None]:
        """Check if persistent halt flag is active."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT is_halted, reason FROM runtime_halt_state WHERE id = 1").fetchone()
            if row and row["is_halted"]:
                return True, row["reason"]
            return False, None

    def trip_system_halt(self, reason: str, evidence_id: str | None = None) -> None:
        """Activate persistent system-wide halt."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE runtime_halt_state
                SET is_halted = 1, reason = ?, halted_at = ?, evidence_id = ?
                WHERE id = 1
            """, (reason, now_iso, evidence_id))
            conn.commit()

    def clear_system_halt(self, actor: str, reason: str) -> None:
        """Clear persistent system-wide halt (operator action)."""
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE runtime_halt_state
                SET is_halted = 0, reason = NULL, halted_at = NULL, evidence_id = NULL
                WHERE id = 1
            """)
            conn.commit()

    def has_active_exposure_for_key(self, logical_exposure_key: str) -> bool:
        """Check if an active order intent or open position already exists for the logical exposure key."""
        if not logical_exposure_key:
            return False
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            query = """
                SELECT status, expires_at FROM execution_ledger
                WHERE logical_exposure_key = ?
                  AND (
                    status IN ('submitting', 'accepted', 'partially_filled', 'filled', 'unknown')
                    OR (status IN ('previewed', 'approved', 'intent_persisted') AND expires_at >= ?)
                  )
                LIMIT 1
            """
            row = conn.execute(query, (logical_exposure_key, now_iso)).fetchone()
            return row is not None

    def get_active_preview_by_logical_key(self, logical_exposure_key: str) -> dict[str, Any] | None:
        """Retrieve existing active preview matching logical exposure key (for UI idempotent display)."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            query = """
                SELECT * FROM execution_ledger
                WHERE logical_exposure_key = ?
                  AND status = 'previewed'
                  AND expires_at >= ?
                ORDER BY created_at DESC
                LIMIT 1
            """
            row = conn.execute(query, (logical_exposure_key, now_iso)).fetchone()
            return dict(row) if row else None

    def register_preview(
        self,
        fingerprint: str,
        logical_exposure_key: str,
        client_order_id: str,
        approval_token: str,
        broker_target: str,
        symbol: str,
        quantity: int,
        limit_price: float,
        expires_at: datetime,
        economic_fingerprint: str = "",
        strategy_id: str | None = None,

        decision_id: str = "dec-default",
        event_id: str = "evt-default",
        model_version: str = "caisheng-1.0.0",
        mandate_version: str = "caisheng-mandate-v1",
        decision_time_bucket: str = "",
        full_order_plan: dict[str, Any] | str | None = None,
        is_close_order: bool = False,
    ) -> None:
        """Register a previewed order plan inside a single atomic transaction."""
        plan_json = json.dumps(full_order_plan) if isinstance(full_order_plan, dict) else (full_order_plan or "")
        # Auto-detect closing order from token, client_order_id, or plan legs

        is_close = is_close_order or "tok-close" in approval_token or "close" in client_order_id or "to_close" in plan_json.lower()

        halted, halt_reason = self.is_system_halted()
        if halted and not is_close:
            raise ExecutionError(f"Cannot register preview: System is currently HALTED. Reason: {halt_reason}")

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        exp_iso = expires_at.isoformat()
        log_key = logical_exposure_key or economic_fingerprint or fingerprint
        ec_fp = economic_fingerprint or fingerprint

        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")

            # Check duplicate logical exposure within active window
            dup_query = """
                SELECT status, expires_at FROM execution_ledger
                WHERE logical_exposure_key = ?
                  AND (
                    status IN ('submitting', 'accepted', 'partially_filled', 'filled', 'unknown')
                    OR (status IN ('previewed', 'approved', 'intent_persisted') AND expires_at >= ?)
                  )
                LIMIT 1
            """
            dup_row = conn.execute(dup_query, (log_key, now_iso)).fetchone()
            if dup_row:
                conn.rollback()
                raise ExecutionError(
                    f"Duplicate logical exposure prevented! An active order intent or open position already exists for exposure key '{log_key}' (status: {dup_row['status']})."
                )

            # Check if fingerprint already exists
            existing = conn.execute("SELECT status FROM execution_ledger WHERE fingerprint = ?", (fingerprint,)).fetchone()
            if existing:
                conn.rollback()
                raise ExecutionError(f"Order plan with fingerprint '{fingerprint}' already exists in ledger (status: {existing['status']}).")

            deadline_iso = (now + timedelta(minutes=15)).isoformat()

            conn.execute("""
                INSERT INTO execution_ledger
                (fingerprint, logical_exposure_key, economic_fingerprint, client_order_id, approval_token,
                 strategy_id, decision_id, event_id, model_version, mandate_version, decision_time_bucket,
                 status, broker_target, symbol, quantity, limit_price, created_at, expires_at, full_order_plan, recovery_deadline)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (fingerprint, log_key, ec_fp, client_order_id, approval_token,
                  strategy_id, decision_id, event_id, model_version, mandate_version, decision_time_bucket,
                  ExecutionStatus.PREVIEWED.value, broker_target, symbol, quantity, limit_price, now_iso, exp_iso, plan_json, deadline_iso))

            self._record_transition_event(
                conn,
                order_fingerprint=fingerprint,
                client_order_id=client_order_id,
                approval_token=approval_token,
                from_status="none",
                to_status=ExecutionStatus.PREVIEWED.value,
                actor="order_gateway",
                reason="Order preview registered",
                evidence_id=decision_id,
            )
            conn.commit()

    def approve_order(self, approval_token: str, actor: str = "operator") -> bool:
        """Approve an order token. Enforces PREVIEWED -> APPROVED."""
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            row = conn.execute("SELECT fingerprint, client_order_id, status FROM execution_ledger WHERE approval_token = ?", (approval_token,)).fetchone()
            if not row:
                conn.rollback()
                raise ExecutionError(f"Approval token '{approval_token}' not found in ledger.")

            current_status = row["status"]
            self._validate_transition(current_status, ExecutionStatus.APPROVED.value)

            conn.execute("""
                UPDATE execution_ledger
                SET status = ?
                WHERE approval_token = ? AND status = ?
            """, (ExecutionStatus.APPROVED.value, approval_token, ExecutionStatus.PREVIEWED.value))

            self._record_transition_event(
                conn,
                order_fingerprint=row["fingerprint"],
                client_order_id=row["client_order_id"],
                approval_token=approval_token,
                from_status=current_status,
                to_status=ExecutionStatus.APPROVED.value,
                actor=actor,
                reason="Order approved",
            )
            conn.commit()
            return True

    def record_approval(self, approval_token: str, approver: str = "operator") -> bool:
        """Alias for approve_order for compatibility."""
        return self.approve_order(approval_token, actor=approver)

    def persist_order_intent(self, approval_token: str, full_order_plan: dict[str, Any] | str | None = None, actor: str = "order_gateway") -> bool:

        """Persist full immutable order intent immediately before broker dispatch. Enforces APPROVED -> INTENT_PERSISTED."""
        plan_json = json.dumps(full_order_plan) if isinstance(full_order_plan, dict) else full_order_plan

        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            row = conn.execute("SELECT fingerprint, client_order_id, status, full_order_plan FROM execution_ledger WHERE approval_token = ?", (approval_token,)).fetchone()
            if not row:
                conn.rollback()
                raise ExecutionError(f"Approval token '{approval_token}' not found in ledger.")

            current_status = row["status"]
            self._validate_transition(current_status, ExecutionStatus.INTENT_PERSISTED.value)

            updated_plan = plan_json if plan_json else row["full_order_plan"]
            conn.execute("""
                UPDATE execution_ledger
                SET status = ?, full_order_plan = COALESCE(?, full_order_plan)
                WHERE approval_token = ?
            """, (ExecutionStatus.INTENT_PERSISTED.value, updated_plan, approval_token))

            self._record_transition_event(
                conn,
                order_fingerprint=row["fingerprint"],
                client_order_id=row["client_order_id"],
                approval_token=approval_token,
                from_status=current_status,
                to_status=ExecutionStatus.INTENT_PERSISTED.value,
                actor=actor,
                reason="Full order intent committed prior to dispatch",
            )
            conn.commit()
            return True

    def consume_approval_and_lock(self, approval_token: str, fingerprint: str, actor: str = "broker_dispatch") -> bool:
        """Atomic compare-and-set to consume approval token. Enforces INTENT_PERSISTED -> SUBMITTING."""
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            row = conn.execute("SELECT expires_at, status, client_order_id FROM execution_ledger WHERE approval_token = ? AND fingerprint = ?",
                               (approval_token, fingerprint)).fetchone()
            if not row:
                conn.rollback()
                raise ExecutionError("Approval token or fingerprint not found in ledger.")

            current_status = row["status"]
            self._validate_transition(current_status, ExecutionStatus.SUBMITTING.value)

            exp_dt = datetime.fromisoformat(row["expires_at"])
            if now > exp_dt:
                conn.execute("UPDATE execution_ledger SET status = ? WHERE approval_token = ?", (ExecutionStatus.REJECTED.value, approval_token))
                self._record_transition_event(
                    conn,
                    order_fingerprint=fingerprint,
                    client_order_id=row["client_order_id"],
                    approval_token=approval_token,
                    from_status=current_status,
                    to_status=ExecutionStatus.REJECTED.value,
                    actor="system_expiry",
                    reason="Approval token expired",
                )
                conn.commit()
                raise ExecutionError("Approval token has expired.")

            cursor = conn.execute("""
                UPDATE execution_ledger
                SET status = ?, submitted_at = ?
                WHERE approval_token = ? AND fingerprint = ? AND status = ?
            """, (ExecutionStatus.SUBMITTING.value, now_iso, approval_token, fingerprint, ExecutionStatus.INTENT_PERSISTED.value))

            self._record_transition_event(
                conn,
                order_fingerprint=fingerprint,
                client_order_id=row["client_order_id"],
                approval_token=approval_token,
                from_status=current_status,
                to_status=ExecutionStatus.SUBMITTING.value,
                actor=actor,
                reason="Locked for broker dispatch",
            )
            conn.commit()
            if cursor.rowcount == 0:
                raise ExecutionError("Approval token has already been consumed or locked by another concurrent submission.")
            return True

    def mark_unknown(self, approval_token: str, error_message: str | None = None, actor: str = "timeout_handler") -> None:
        """Mark status as UNKNOWN when broker call times out or encounters network ambiguity."""
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        deadline_iso = (now + timedelta(minutes=15)).isoformat()

        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            row = conn.execute("SELECT fingerprint, client_order_id, status FROM execution_ledger WHERE approval_token = ?", (approval_token,)).fetchone()
            if not row:
                conn.rollback()
                raise ExecutionError(f"Approval token '{approval_token}' not found in ledger.")

            curr = row["status"]
            self._validate_transition(curr, ExecutionStatus.UNKNOWN.value)

            conn.execute("""
                UPDATE execution_ledger
                SET status = ?, error_message = ?, first_recovery_attempt_at = COALESCE(first_recovery_attempt_at, ?),
                    last_recovery_attempt_at = ?, next_recovery_attempt_at = ?, recovery_deadline = COALESCE(recovery_deadline, ?)
                WHERE approval_token = ?
            """, (ExecutionStatus.UNKNOWN.value, error_message, now_iso, now_iso, now_iso, deadline_iso, approval_token))


            self._record_transition_event(
                conn,
                order_fingerprint=row["fingerprint"],
                client_order_id=row["client_order_id"],
                approval_token=approval_token,
                from_status=curr,
                to_status=ExecutionStatus.UNKNOWN.value,
                actor=actor,
                reason=f"Submission ambiguous: {error_message}",
            )
            conn.commit()

    def record_broker_result(
        self,
        approval_token: str,
        status: ExecutionStatus,
        broker_order_id: str | None = None,
        raw_response: dict[str, Any] | None = None,
        filled_quantity: int = 0,
        average_price: float | None = None,
        error_message: str | None = None,
        actor: str = "broker_adapter",
    ) -> None:
        """Record broker response and update ledger state with transition validation."""
        raw_json = json.dumps(raw_response) if raw_response is not None else None
        now = datetime.now(timezone.utc).isoformat() if status in (ExecutionStatus.FILLED, ExecutionStatus.PARTIALLY_FILLED, ExecutionStatus.CLOSED) else None

        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            row = conn.execute("SELECT fingerprint, client_order_id, status FROM execution_ledger WHERE approval_token = ?", (approval_token,)).fetchone()
            if not row:
                conn.rollback()
                raise ExecutionError(f"Approval token '{approval_token}' not found in ledger.")

            curr = row["status"]
            self._validate_transition(curr, status.value)

            conn.execute("""
                UPDATE execution_ledger
                SET status = ?, broker_order_id = COALESCE(?, broker_order_id),
                    raw_broker_response = COALESCE(?, raw_broker_response),
                    filled_quantity = ?, average_price = ?,
                    filled_at = COALESCE(?, filled_at),
                    error_message = ?
                WHERE approval_token = ?
            """, (status.value, broker_order_id, raw_json, filled_quantity, average_price, now, error_message, approval_token))

            self._record_transition_event(
                conn,
                order_fingerprint=row["fingerprint"],
                client_order_id=row["client_order_id"],
                approval_token=approval_token,
                from_status=curr,
                to_status=status.value,
                actor=actor,
                reason=error_message or "Broker response recorded",
                evidence_id=broker_order_id,
            )
            conn.commit()

    def update_status_by_client_order_id(
        self,
        client_order_id: str,
        status: ExecutionStatus,
        broker_order_id: str | None = None,
        raw_response: dict[str, Any] | None = None,
        filled_quantity: int = 0,
        average_price: float | None = None,
        error_message: str | None = None,
        actor: str = "reconciliation_engine",
        evidence_id: str | None = None,
    ) -> bool:
        """Update order state during broker reconciliation by client_order_id with transition validation."""
        raw_json = json.dumps(raw_response) if raw_response is not None else None
        now = datetime.now(timezone.utc).isoformat() if status in (ExecutionStatus.FILLED, ExecutionStatus.PARTIALLY_FILLED, ExecutionStatus.CLOSED) else None

        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            row = conn.execute("SELECT fingerprint, approval_token, status FROM execution_ledger WHERE client_order_id = ?", (client_order_id,)).fetchone()
            if not row:
                conn.rollback()
                raise ExecutionError(f"Client order ID '{client_order_id}' not found in ledger.")

            curr = row["status"]
            # If status unchanged, update metadata without invalid transition error
            if curr != status.value:
                self._validate_transition(curr, status.value)

            conn.execute("""
                UPDATE execution_ledger
                SET status = ?, broker_order_id = COALESCE(?, broker_order_id),
                    raw_broker_response = COALESCE(?, raw_broker_response),
                    filled_quantity = ?, average_price = ?,
                    filled_at = COALESCE(?, filled_at),
                    error_message = ?
                WHERE client_order_id = ?
            """, (status.value, broker_order_id, raw_json, filled_quantity, average_price, now, error_message, client_order_id))

            self._record_transition_event(
                conn,
                order_fingerprint=row["fingerprint"],
                client_order_id=client_order_id,
                approval_token=row["approval_token"],
                from_status=curr,
                to_status=status.value,
                actor=actor,
                reason=error_message or "Reconciliation status update",
                evidence_id=evidence_id or broker_order_id,
            )
            conn.commit()
            return True

    def record_recovery_attempt(
        self,
        client_order_id: str,
        error_message: str | None = None,
        evidence_id: str | None = None,
        next_delay_seconds: int = 15,
    ) -> None:
        """Record an UNKNOWN order recovery lookup attempt."""
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        next_iso = (now + timedelta(seconds=next_delay_seconds)).isoformat()

        with self._get_connection() as conn:
            conn.execute("""
                UPDATE execution_ledger
                SET recovery_attempt_count = recovery_attempt_count + 1,
                    last_recovery_attempt_at = ?,
                    next_recovery_attempt_at = ?,
                    last_recovery_error = ?,
                    last_recovery_evidence_id = ?
                WHERE client_order_id = ?
            """, (now_iso, next_iso, error_message, evidence_id, client_order_id))
            conn.commit()

    def get_order_by_client_order_id(self, client_order_id: str) -> dict[str, Any] | None:
        """Retrieve order ledger record by client_order_id."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM execution_ledger WHERE client_order_id = ?", (client_order_id,)).fetchone()
            return dict(row) if row else None

    def get_order_by_approval_token(self, approval_token: str) -> dict[str, Any] | None:
        """Retrieve order ledger record by approval_token."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM execution_ledger WHERE approval_token = ?", (approval_token,)).fetchone()
            return dict(row) if row else None

    def get_order_by_fingerprint(self, fingerprint: str) -> dict[str, Any] | None:
        """Retrieve order ledger record by execution fingerprint."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM execution_ledger WHERE fingerprint = ?", (fingerprint,)).fetchone()
            return dict(row) if row else None


    def list_active_orders(self) -> list[dict[str, Any]]:
        """List all currently active orders requiring monitoring or reconciliation."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            query = """
                SELECT * FROM execution_ledger
                WHERE status IN ('submitting', 'accepted', 'partially_filled', 'unknown')
                   OR (status IN ('previewed', 'approved', 'intent_persisted') AND expires_at >= ?)
                ORDER BY created_at DESC
            """
            rows = conn.execute(query, (now_iso,)).fetchall()
            return [dict(r) for r in rows]

    def list_open_positions(self) -> list[dict[str, Any]]:
        """List all filled/partially filled strategies representing open positions in the ledger."""
        with self._get_connection() as conn:
            query = "SELECT * FROM execution_ledger WHERE status IN ('filled', 'partially_filled') ORDER BY created_at DESC"
            rows = conn.execute(query).fetchall()
            return [dict(r) for r in rows]

    def list_filled_close_orders(self) -> list[dict[str, Any]]:
        """List filled close intents that still require durable trade finalization."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM execution_ledger WHERE status = 'filled' ORDER BY created_at ASC"
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                plan = json.loads(item.get("full_order_plan") or "{}")
            except (TypeError, json.JSONDecodeError):
                continue
            if plan.get("original_entry_intent_id"):
                result.append(item)
        return result

    def has_closed_trade_for_exit_order(self, exit_order_id: str) -> bool:
        """Return whether accounting already contains this close intent."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM closed_trades WHERE exit_order_id = ? LIMIT 1",
                (exit_order_id,),
            ).fetchone()
            return row is not None

    def get_due_unknown_orders(self, max_count: int = 10) -> list[dict[str, Any]]:
        """List UNKNOWN orders that are due for reconciliation lookup."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            query = """
                SELECT * FROM execution_ledger
                WHERE status = 'unknown'
                  AND (next_recovery_attempt_at IS NULL OR next_recovery_attempt_at <= ?)
                ORDER BY created_at ASC
                LIMIT ?
            """
            rows = conn.execute(query, (now_iso, max_count)).fetchall()
            return [dict(r) for r in rows]

    def get_transition_history(self, order_fingerprint: str) -> list[dict[str, Any]]:
        """Retrieve full append-only transition event history for an order."""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM execution_transition_events
                WHERE order_fingerprint = ?
                ORDER BY id ASC
            """, (order_fingerprint,)).fetchall()
            return [dict(r) for r in rows]

    def persist_reconciliation_report(self, report_id: str, status: str, matched_orders: int, matched_positions: int, report_dict: dict[str, Any]) -> None:
        """Persist structured reconciliation report."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO reconciliation_reports
                (reconciliation_id, status, timestamp, matched_orders_count, matched_positions_count, report_payload)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (report_id, status, now_iso, matched_orders, matched_positions, json.dumps(report_dict)))
            conn.commit()

    def get_or_init_competition_metadata(
        self,
        starting_nav: Any = 100000.0,
        strategy_version: str = "caisheng-1.0.0",
        mandate_version: str = "caisheng-mandate-v1",
        paper_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Fetch existing competition metadata or initialize immutable starting record."""
        nav_val = 100000.0
        if isinstance(starting_nav, (int, float)):
            nav_val = float(starting_nav)
        elif hasattr(starting_nav, "competition_initial_nav"):
            nav_val = float(getattr(starting_nav, "competition_initial_nav", 100000.0))
            strategy_version = getattr(starting_nav, "strategy_version", strategy_version)
            mandate_version = getattr(starting_nav, "mandate_version", mandate_version)
        elif isinstance(starting_nav, dict):
            nav_val = float(starting_nav.get("competition_initial_nav", starting_nav.get("initial_nav", 100000.0)))

        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM competition_metadata WHERE competition_id = 'caisheng-options-alpha-2026'").fetchone()
            if row:
                stored_account = row["paper_account_id"]
                if paper_account_id and stored_account and stored_account != paper_account_id:
                    raise ExecutionError(
                        "Competition ledger is bound to a different Alpaca paper account."
                    )
                if paper_account_id and not stored_account:
                    conn.execute(
                        "UPDATE competition_metadata SET paper_account_id = ? "
                        "WHERE competition_id = 'caisheng-options-alpha-2026'",
                        (paper_account_id,),
                    )
                    conn.commit()
                    row = conn.execute(
                        "SELECT * FROM competition_metadata "
                        "WHERE competition_id = 'caisheng-options-alpha-2026'"
                    ).fetchone()
                return dict(row)
            conn.execute("""
                INSERT INTO competition_metadata
                (competition_id, starting_nav, strategy_version, mandate_version, start_timestamp, paper_account_id)
                VALUES ('caisheng-options-alpha-2026', ?, ?, ?, ?, ?)
            """, (nav_val, strategy_version, mandate_version, now_iso, paper_account_id))
            conn.commit()
            new_row = conn.execute("SELECT * FROM competition_metadata WHERE competition_id = 'caisheng-options-alpha-2026'").fetchone()
            return dict(new_row)


    def record_portfolio_snapshot(self, snapshot: Any) -> None:
        """Persist point-in-time portfolio snapshot."""
        now_iso = getattr(snapshot, "timestamp", datetime.now(timezone.utc)).isoformat() if hasattr(snapshot, "timestamp") else datetime.now(timezone.utc).isoformat()
        sector_risk_json = json.dumps(getattr(snapshot, "sector_reserved_risk", {}))
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO portfolio_snapshots
                (equity, cash, buying_power, initial_nav, high_water_equity, daily_realized_pl, daily_unrealized_pl,
                 open_strategies_count, new_entries_today_count, reserved_risk_dollars, sector_reserved_risk, timestamp, is_stale)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                float(getattr(snapshot, "equity", 0.0)),
                float(getattr(snapshot, "cash", 0.0)),
                float(getattr(snapshot, "buying_power", 0.0)),
                float(getattr(snapshot, "initial_nav", 100000.0)),
                float(getattr(snapshot, "high_water_equity", 100000.0)),
                float(getattr(snapshot, "daily_realized_pl", 0.0)),
                float(getattr(snapshot, "daily_unrealized_pl", 0.0)),
                int(getattr(snapshot, "open_strategies_count", 0)),
                int(getattr(snapshot, "new_entries_today_count", 0)),
                float(getattr(snapshot, "reserved_risk_dollars", 0.0)),
                sector_risk_json,
                now_iso,
                1 if getattr(snapshot, "is_stale", False) else 0,
            ))
            conn.commit()

    def get_latest_portfolio_snapshot(self) -> dict[str, Any] | None:
        """Fetch most recent portfolio snapshot."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM portfolio_snapshots ORDER BY id DESC LIMIT 1").fetchone()
            if not row:
                return None
            res = dict(row)
            try:
                res["sector_reserved_risk"] = json.loads(res.get("sector_reserved_risk", "{}"))
            except Exception:
                res["sector_reserved_risk"] = {}
            return res

    def get_open_strategies_count(self) -> int:
        """Count currently active filled and partially filled strategies."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT COUNT(DISTINCT strategy_id) as cnt FROM execution_ledger WHERE status IN ('filled', 'partially_filled')").fetchone()
            return int(row["cnt"]) if row else 0

    def get_new_entries_today_count(self, today_date_str: str | None = None) -> int:
        """Count new entries initiated today."""
        if not today_date_str:
            today_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._get_connection() as conn:
            row = conn.execute("""
                SELECT COUNT(*) as cnt FROM execution_ledger
                WHERE created_at LIKE ? AND status NOT IN ('rejected', 'canceled')
            """, (f"{today_date_str}%",)).fetchone()
            return int(row["cnt"]) if row else 0

    def get_portfolio_reserved_risk(self) -> tuple[float, dict[str, float]]:
        """Calculate total reserved risk and sector breakdown from active and open orders."""
        now_iso = datetime.now(timezone.utc).isoformat()
        total_risk = 0.0
        sector_risk: dict[str, float] = {}

        from volagent.quant.portfolio_gate import get_symbol_sector

        with self._get_connection() as conn:
            query = """
                SELECT symbol, full_order_plan FROM execution_ledger
                WHERE status IN ('submitting', 'accepted', 'partially_filled', 'filled', 'unknown')
                   OR (status IN ('previewed', 'approved', 'intent_persisted') AND expires_at >= ?)
            """
            rows = conn.execute(query, (now_iso,)).fetchall()
            for r in rows:
                sym = r["symbol"]
                sector = get_symbol_sector(sym)
                plan_json = r["full_order_plan"]
                loss = 0.0
                if plan_json:
                    try:
                        plan_dict = json.loads(plan_json)
                        loss = float(plan_dict.get("max_loss_dollars", 0.0))
                    except Exception:
                        pass
                total_risk += loss
                sector_risk[sector] = sector_risk.get(sector, 0.0) + loss

        return total_risk, sector_risk

    def record_closed_trade(self, trade_record: Any) -> None:
        """Persist immutable closed trade record in SQLite."""
        raw_payload = json.dumps(trade_record.model_dump(mode="json") if hasattr(trade_record, "model_dump") else trade_record)
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO closed_trades
                (trade_id, strategy_id, symbol, decision, event_id, entry_order_id, exit_order_id,
                 quantity, entry_price, exit_price, gross_realized_pnl_dollars, fees_and_slippage,
                 net_realized_pnl_dollars, realized_return_pct, max_loss_budget, risk_utilization_pct,
                 opened_at, closed_at, holding_hours, pre_event_expected_move, pre_event_implied_move,
                 actual_post_event_move, outcome_label, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                getattr(trade_record, "trade_id", str(uuid.uuid4())),
                getattr(trade_record, "strategy_id", "strat-unknown"),
                getattr(trade_record, "symbol", "UNKNOWN"),
                str(getattr(trade_record, "decision", "long_straddle")),
                getattr(trade_record, "event_id", "evt-unknown"),
                getattr(trade_record, "entry_order_id", ""),
                getattr(trade_record, "exit_order_id", ""),
                int(getattr(trade_record, "quantity", 1)),
                float(getattr(trade_record, "entry_price", 0.0)),
                float(getattr(trade_record, "exit_price", 0.0)),
                float(getattr(trade_record, "gross_realized_pnl_dollars", 0.0)),
                float(getattr(trade_record, "fees_and_slippage", 0.0)),
                float(getattr(trade_record, "net_realized_pnl_dollars", 0.0)),
                float(getattr(trade_record, "realized_return_pct", 0.0)),
                float(getattr(trade_record, "max_loss_budget", 0.0)),
                float(getattr(trade_record, "risk_utilization_pct", 0.0)),
                getattr(trade_record, "opened_at", datetime.now(timezone.utc)).isoformat() if hasattr(getattr(trade_record, "opened_at", None), "isoformat") else str(getattr(trade_record, "opened_at", "")),
                getattr(trade_record, "closed_at", datetime.now(timezone.utc)).isoformat() if hasattr(getattr(trade_record, "closed_at", None), "isoformat") else str(getattr(trade_record, "closed_at", "")),
                float(getattr(trade_record, "holding_hours", 0.0)),
                float(getattr(trade_record, "pre_event_expected_move", 0.0)),
                float(getattr(trade_record, "pre_event_implied_move", 0.0)),
                float(getattr(trade_record, "actual_post_event_move", 0.0)),
                str(getattr(trade_record, "outcome_label", "UNKNOWN")),
                raw_payload,
            ))
            conn.commit()

    def list_closed_trades(self) -> list[dict[str, Any]]:
        """List all closed trades ordered by closed timestamp."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM closed_trades ORDER BY closed_at DESC").fetchall()
            return [dict(r) for r in rows]

    def get_daily_realized_pnl(self, market_day: str | None = None) -> float:
        """Sum net realized P&L for an America/New_York market day."""
        market_tz = ZoneInfo("America/New_York")
        target_day = market_day or datetime.now(timezone.utc).astimezone(market_tz).date().isoformat()
        total = 0.0
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT closed_at, net_realized_pnl_dollars FROM closed_trades"
            ).fetchall()
        for row in rows:
            try:
                closed_at = datetime.fromisoformat(str(row["closed_at"]).replace("Z", "+00:00"))
                if closed_at.tzinfo is None:
                    closed_at = closed_at.replace(tzinfo=timezone.utc)
                if closed_at.astimezone(market_tz).date().isoformat() == target_day:
                    total += float(row["net_realized_pnl_dollars"])
            except (TypeError, ValueError):
                continue
        return total

    def record_decision_record(self, record: Any) -> None:
        """Persist authoritative DecisionRecord in SQLite."""
        raw_payload = json.dumps(record.model_dump(mode="json") if hasattr(record, "model_dump") else record)
        snap = getattr(record, "snapshot", None)
        if isinstance(snap, dict):
            sym = snap.get("symbol", "UNKNOWN")
        elif hasattr(snap, "symbol"):
            sym = getattr(snap, "symbol", "UNKNOWN")
        else:
            sym = "UNKNOWN"

        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO decision_records
                (decision_id, run_id, symbol, status, selected_action, selected_strategy_id, quantity, generated_at, artifact_hash, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                getattr(record, "decision_id", ""),
                getattr(record, "run_id", ""),
                sym,
                getattr(record, "status", "APPROVED"),
                getattr(record, "selected_action", "NO_TRADE"),
                getattr(record, "selected_strategy_id", None),
                int(getattr(record, "quantity", 0)),
                getattr(record, "generated_at", datetime.now(timezone.utc).isoformat()),
                getattr(record, "artifact_hash", ""),
                raw_payload,
            ))
            conn.commit()


    def list_decision_records(self) -> list[dict[str, Any]]:
        """List all decision records ordered by generated_at descending."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM decision_records ORDER BY generated_at DESC").fetchall()
            return [dict(r) for r in rows]

    def get_decision_record(self, decision_id: str) -> dict[str, Any] | None:
        """Retrieve one authoritative decision record by immutable ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM decision_records WHERE decision_id = ?", (decision_id,)
            ).fetchone()
            return dict(row) if row else None

    def record_shadow_book_record(self, record: Any) -> None:
        """Persist immutable ShadowBookRecord in SQLite."""
        raw_payload = json.dumps(record.model_dump(mode="json") if hasattr(record, "model_dump") else record)
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO shadow_book_records
                (shadow_id, event_id, symbol, selected_action, selected_strategy_pnl, actual_post_event_move, actual_iv_crush_points, recorded_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                getattr(record, "shadow_id", ""),
                getattr(record, "event_id", ""),
                getattr(record, "symbol", ""),
                getattr(record, "selected_action", "NO_TRADE"),
                float(getattr(record, "selected_strategy_pnl", 0.0)),
                float(getattr(record, "actual_post_event_move", 0.0)),
                float(getattr(record, "actual_iv_crush_points", 0.0)),
                getattr(record, "recorded_at", datetime.now(timezone.utc).isoformat()),
                raw_payload,
            ))
            conn.commit()

    def list_shadow_book_records(self) -> list[dict[str, Any]]:
        """List all shadow book records ordered by recorded_at descending."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM shadow_book_records ORDER BY recorded_at DESC").fetchall()
            return [dict(r) for r in rows]

    def record_benchmark_intent(self, record: Any) -> None:
        """Append one immutable, pre-outcome benchmark intent idempotently."""
        payload = record.model_dump(mode="json") if hasattr(record, "model_dump") else record
        raw_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        intent_id = str(payload.get("intent_id", ""))
        if not intent_id:
            raise ExecutionError("benchmark intent requires intent_id")
        with self._get_connection() as conn:
            existing = conn.execute(
                "SELECT raw_payload FROM benchmark_intents WHERE intent_id = ?", (intent_id,)
            ).fetchone()
            if existing:
                if existing["raw_payload"] == raw_payload:
                    return
                raise ExecutionError(f"immutable benchmark intent conflict for {intent_id}")
            compute_hash = getattr(record, "compute_hash", None)
            if callable(compute_hash) and payload.get("receipt_hash") != compute_hash():
                raise ExecutionError(f"invalid benchmark intent hash for {intent_id}")
            conn.execute(
                """
                INSERT INTO benchmark_intents
                (intent_id, opportunity_id, decision_id, symbol, decision_time, exit_time, receipt_hash, raw_payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    intent_id,
                    str(payload.get("opportunity_id", "")),
                    str(payload.get("decision_id", "")),
                    str(payload.get("symbol", "")),
                    str(payload.get("decision_time", "")),
                    str(payload.get("exit_time", "")),
                    str(payload.get("receipt_hash", "")),
                    raw_payload,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()

    def get_benchmark_intent(self, intent_id: str) -> dict[str, Any] | None:
        """Retrieve one locked benchmark intent."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM benchmark_intents WHERE intent_id = ?", (intent_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_benchmark_intents(self, *, pending_only: bool = False) -> list[dict[str, Any]]:
        """List locked intents, optionally excluding those already settled."""
        query = "SELECT i.* FROM benchmark_intents i"
        if pending_only:
            query += " LEFT JOIN benchmark_outcomes o ON o.intent_id = i.intent_id WHERE o.intent_id IS NULL"
        query += " ORDER BY i.decision_time DESC"
        with self._get_connection() as conn:
            rows = conn.execute(query).fetchall()
            return [dict(row) for row in rows]

    def record_benchmark_outcome(self, record: Any) -> None:
        """Append one immutable settlement receipt idempotently."""
        payload = record.model_dump(mode="json") if hasattr(record, "model_dump") else record
        raw_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        outcome_id = str(payload.get("outcome_id", ""))
        intent_id = str(payload.get("intent_id", ""))
        if not outcome_id or not intent_id:
            raise ExecutionError("benchmark outcome requires outcome_id and intent_id")
        with self._get_connection() as conn:
            locked = conn.execute(
                "SELECT 1 FROM benchmark_intents WHERE intent_id = ?", (intent_id,)
            ).fetchone()
            if not locked:
                raise ExecutionError(f"benchmark outcome has no locked intent {intent_id}")
            existing = conn.execute(
                "SELECT raw_payload FROM benchmark_outcomes WHERE intent_id = ? OR outcome_id = ?",
                (intent_id, outcome_id),
            ).fetchone()
            if existing:
                if existing["raw_payload"] == raw_payload:
                    return
                raise ExecutionError(f"immutable benchmark outcome conflict for {intent_id}")
            compute_hash = getattr(record, "compute_hash", None)
            if callable(compute_hash) and payload.get("receipt_hash") != compute_hash():
                raise ExecutionError(f"invalid benchmark outcome hash for {outcome_id}")
            conn.execute(
                """
                INSERT INTO benchmark_outcomes
                (outcome_id, intent_id, opportunity_id, symbol, settled_at, receipt_hash, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    outcome_id,
                    intent_id,
                    str(payload.get("opportunity_id", "")),
                    str(payload.get("symbol", "")),
                    str(payload.get("settled_at", "")),
                    str(payload.get("receipt_hash", "")),
                    raw_payload,
                ),
            )
            conn.commit()

    def list_benchmark_outcomes(self) -> list[dict[str, Any]]:
        """List immutable shadow settlements newest first."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM benchmark_outcomes ORDER BY settled_at DESC"
            ).fetchall()
            return [dict(row) for row in rows]

    def record_mcp_audit_event(
        self,
        event_id: str,
        tool_name: str,
        sanitized_arguments: dict[str, Any] | str,
        result_status: str,
        raw_response: dict[str, Any] | str,
        decision_id: str | None = None,
    ) -> None:
        """Persist sanitized MCP tool invocation audit event."""
        sanitized_args_str = json.dumps(sanitized_arguments) if isinstance(sanitized_arguments, dict) else str(sanitized_arguments)
        raw_resp_str = json.dumps(raw_response) if isinstance(raw_response, dict) else str(raw_response)
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO mcp_audit_events
                (event_id, tool_name, decision_id, sanitized_arguments, result_status, called_at, raw_response)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                event_id,
                tool_name,
                decision_id,
                sanitized_args_str,
                result_status,
                datetime.now(timezone.utc).isoformat(),
                raw_resp_str,
            ))
            conn.commit()

    def list_mcp_audit_events(self) -> list[dict[str, Any]]:
        """List all MCP audit events ordered by called_at descending."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM mcp_audit_events ORDER BY called_at DESC").fetchall()
            return [dict(r) for r in rows]
