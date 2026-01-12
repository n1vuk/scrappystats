import secrets
import time
from typing import Any

_PENDING: dict[str, dict[str, Any]] = {}
_TTL_SECONDS = 300


def _now() -> float:
    return time.time()


def _cleanup_expired() -> None:
    if not _PENDING:
        return
    cutoff = _now() - _TTL_SECONDS
    expired = [key for key, data in _PENDING.items() if data.get("ts", 0) < cutoff]
    for key in expired:
        _PENDING.pop(key, None)


def create_pending(payload: dict, subcommand: str, options: list[dict]) -> str:
    _cleanup_expired()
    nonce = secrets.token_urlsafe(8)
    _PENDING[nonce] = {
        "ts": _now(),
        "subcommand": subcommand,
        "options": options,
        "guild_id": payload.get("guild_id"),
        "user_id": _extract_user_id(payload),
    }
    return nonce


def pop_pending(nonce: str) -> dict | None:
    _cleanup_expired()
    return _PENDING.pop(nonce, None)


def _extract_user_id(payload: dict) -> str | None:
    member = payload.get("member") or {}
    user = member.get("user") or payload.get("user") or {}
    return user.get("id")
