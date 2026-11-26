"""Access key authentication, trusted-proxy IP resolution, and rate-limit keying."""

from __future__ import annotations

import hashlib
import hmac

from fastapi import Depends, HTTPException, Request, status

from app.config import Settings, get_settings


def hash_api_key(raw_key: str) -> str:
    """Return SHA-256 hex digest of an API access key."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class ApiKeyRegistry:
    """Stores only hashed API keys in memory."""

    def __init__(self, raw_keys: tuple[str, ...]) -> None:
        self._hashed_keys: frozenset[str] = frozenset(
            hash_api_key(k) for k in raw_keys if k.strip()
        )

    @property
    def is_configured(self) -> bool:
        """Return True if at least one access key is configured."""
        return len(self._hashed_keys) > 0

    def verify(self, candidate: str | None) -> bool:
        """Constant-time verification against stored key hashes."""
        if not candidate or not self._hashed_keys:
            return False
        cand_hash = hash_api_key(candidate.strip())
        return any(hmac.compare_digest(cand_hash, stored) for stored in self._hashed_keys)


def get_client_ip(request: Request, trusted_proxies: tuple[str, ...]) -> str:
    """Resolve client IP, trusting X-Forwarded-For only from configured proxy IPs."""
    direct_ip = request.client.host if request.client else "127.0.0.1"
    if direct_ip in trusted_proxies:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            first_hop = forwarded.split(",")[0].strip()
            if first_hop:
                return first_hop
    return direct_ip


def get_rate_limit_key(request: Request) -> str:
    """Build per-IP + per-key rate-limit bucket key."""
    settings: Settings = getattr(request.app.state, "settings", get_settings())
    ip = get_client_ip(request, settings.trusted_proxies)
    raw_key = request.headers.get("x-kavach-key") or request.cookies.get("kavach_key") or ""
    if raw_key:
        return f"{ip}:{hash_api_key(raw_key)[:12]}"
    return ip


def require_api_key(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> str:
    """FastAPI dependency enforcing X-Kavach-Key header or kavach_key cookie."""
    registry: ApiKeyRegistry | None = getattr(request.app.state, "key_registry", None)
    if registry is None:
        registry = ApiKeyRegistry(settings.api_keys)

    candidate = request.headers.get("x-kavach-key") or request.cookies.get("kavach_key")
    if not registry.verify(candidate):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing access key.",
        )
    return hash_api_key(candidate or "")[:12]
