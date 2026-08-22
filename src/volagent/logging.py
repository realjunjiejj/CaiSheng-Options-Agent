"""Structured logging setup with comprehensive secret redaction."""

import re
from typing import Any
import structlog

# Secret patterns with capture group for the secret value or prefix
SECRET_PATTERNS = [
    re.compile(r"(PK[A-Z0-9]{16,})", re.IGNORECASE),
    re.compile(r"(sk-[a-zA-Z0-9]{20,})", re.IGNORECASE),
    re.compile(r"(AIza[0-9A-Za-z-_]{35})", re.IGNORECASE),
    re.compile(r"(AKIA[0-9A-Z]{16})", re.IGNORECASE),
    re.compile(r"(ALPACA[_\s]*SECRET[_\s]*KEY\s*[:=]\s*)([^\s,]+)", re.IGNORECASE),
    re.compile(r"(API[_\s]*KEY\s*[:=]\s*)([^\s,]+)", re.IGNORECASE),
]

SENSITIVE_KEYS = {"api_key", "secret_key", "alpaca_secret_key", "openai_api_key", "gemini_api_key", "password", "token"}


def mask_string(val: str) -> str:
    """Mask sensitive string content."""
    res = val
    # Generic patterns
    res = re.sub(r"(PK[A-Z0-9]{4})[A-Z0-9]+", r"\1***REDACTED***", res)
    res = re.sub(r"(sk-[a-zA-Z0-9]{4})[a-zA-Z0-9]+", r"\1***REDACTED***", res)
    res = re.sub(r"(AIza[0-9A-Za-z-_]{4})[0-9A-Za-z-_]+", r"\1***REDACTED***", res)
    return res


def redact_secrets(val: Any) -> Any:
    """Recursively redact secrets from strings, dictionaries, lists, and tuples."""
    if isinstance(val, str):
        return mask_string(val)
    elif isinstance(val, dict):
        new_dict = {}
        for k, v in val.items():
            if str(k).lower() in SENSITIVE_KEYS:
                new_dict[k] = "***REDACTED***"
            else:
                new_dict[k] = redact_secrets(v)
        return new_dict
    elif isinstance(val, list):
        return [redact_secrets(item) for item in val]
    elif isinstance(val, tuple):
        return tuple(redact_secrets(item) for item in val)
    return val


def secret_redactor_processor(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Structlog processor to redact secrets from event dictionary."""
    return redact_secrets(event_dict)


def setup_logging(log_level: str = "INFO") -> None:
    """Initialize structured JSON/Console logging with secret redaction processor."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            secret_redactor_processor,  # Active secret redactor inserted!
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
