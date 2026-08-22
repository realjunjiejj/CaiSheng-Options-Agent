"""Provenance tracking and canonical hashing for VolAgent Alpha."""

from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from pydantic import BaseModel, ConfigDict

from volagent.domain.enums import DataMode


class Provenance(BaseModel):
    """Tracks origin, timestamps, and cryptographic hash of external data."""
    model_config = ConfigDict(extra="ignore")

    source_name: str
    source_uri: str | None = None
    retrieved_at: datetime
    observed_at: datetime
    effective_at: datetime | None = None
    content_hash: str
    data_mode: DataMode

    @classmethod
    def from_synthetic(cls, source_name: str = "synthetic_fixture") -> "Provenance":
        now = datetime(2026, 8, 22, 0, 0, 0, tzinfo=timezone.utc)
        return cls(
            source_name=source_name,
            source_uri=f"file://data/replay/{source_name}",
            retrieved_at=now,
            observed_at=now,
            content_hash=hashlib.sha256(source_name.encode()).hexdigest(),
            data_mode=DataMode.REPLAY_SYNTHETIC,
        )


def compute_sha256(content: str | bytes) -> str:
    """Compute hex SHA-256 hash of string or bytes."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def to_canonical_json(obj: Any) -> str:
    """Serialize object to canonical, deterministic JSON string."""
    def default_serializer(o: Any) -> Any:
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, BaseModel):
            return o.model_dump(mode="json")
        if hasattr(o, "value"):
            return o.value
        raise TypeError(f"Object of type {type(o)} is not JSON serializable")

    return json.dumps(obj, default=default_serializer, sort_keys=True, separators=(",", ":"))


def compute_canonical_hash(obj: Any) -> str:
    """Compute SHA-256 hash of an object in canonical JSON format."""
    canonical_str = to_canonical_json(obj)
    return compute_sha256(canonical_str)
