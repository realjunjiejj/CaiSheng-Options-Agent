"""SQLite transactional ledger for order idempotency and approval state transitions."""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any

from volagent.domain.enums import ExecutionStatus
from volagent.errors import ExecutionError

LEDGER_DB_PATH = Path(__file__).resolve().parent.parent.parent / "execution_ledger.db"


class ExecutionLedger:
    """Thread-safe, atomic SQLite ledger enforcing one-time approval consumption and idempotency."""

    def __init__(self, db_path: Path = LEDGER_DB_PATH):
        self.db_path = db_path
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
                    client_order_id TEXT UNIQUE NOT NULL,
                    approval_token TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL,
                    broker_target TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    limit_price REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    submitted_at TEXT,
                    broker_order_id TEXT
                )
            """)
            conn.commit()

    def register_preview(
        self,
        fingerprint: str,
        client_order_id: str,
        approval_token: str,
        broker_target: str,
        symbol: str,
        quantity: int,
        limit_price: float,
        expires_at: datetime,
    ) -> None:
        """Register a previewed order plan."""
        now = datetime.now(timezone.utc).isoformat()
        exp = expires_at.isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO execution_ledger 
                (fingerprint, client_order_id, approval_token, status, broker_target, symbol, quantity, limit_price, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (fingerprint, client_order_id, approval_token, ExecutionStatus.PREVIEWED.value, broker_target, symbol, quantity, limit_price, now, exp))
            conn.commit()

    def approve_order(self, approval_token: str) -> bool:
        """Approve an order token."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                UPDATE execution_ledger
                SET status = ?
                WHERE approval_token = ? AND status = ?
            """, (ExecutionStatus.APPROVED.value, approval_token, ExecutionStatus.PREVIEWED.value))
            conn.commit()
            return cursor.rowcount > 0

    def consume_approval_and_lock(self, approval_token: str, fingerprint: str) -> bool:
        """Atomic compare-and-set to consume approval token immediately prior to broker submission."""
        now = datetime.now(timezone.utc)
        with self._get_connection() as conn:
            row = conn.execute("SELECT expires_at, status FROM execution_ledger WHERE approval_token = ? AND fingerprint = ?", 
                               (approval_token, fingerprint)).fetchone()
            if not row:
                raise ExecutionError("Approval token or fingerprint not found in ledger.")

            if row["status"] != ExecutionStatus.APPROVED.value:
                raise ExecutionError(f"Cannot submit order with status '{row['status']}'. Must be 'approved'.")

            exp_dt = datetime.fromisoformat(row["expires_at"])
            if now > exp_dt:
                conn.execute("UPDATE execution_ledger SET status = ? WHERE approval_token = ?", (ExecutionStatus.REJECTED.value, approval_token))
                conn.commit()
                raise ExecutionError("Approval token has expired.")

            # Atomic lock
            cursor = conn.execute("""
                UPDATE execution_ledger
                SET status = ?, submitted_at = ?
                WHERE approval_token = ? AND fingerprint = ? AND status = ?
            """, (ExecutionStatus.SUBMITTING.value, now.isoformat(), approval_token, fingerprint, ExecutionStatus.APPROVED.value))
            conn.commit()
            if cursor.rowcount == 0:
                raise ExecutionError("Approval token has already been consumed or locked by another concurrent submission.")
            return True

    def record_broker_result(self, approval_token: str, status: ExecutionStatus, broker_order_id: str | None = None) -> None:
        """Record final broker response."""
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE execution_ledger
                SET status = ?, broker_order_id = ?
                WHERE approval_token = ?
            """, (status.value, broker_order_id, approval_token))
            conn.commit()
