from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthRateLimitResult:
    allowed: bool
    retry_after: int = 0
    scope: str = ""


def _digest(value: str) -> str:
    secret = (settings.SECRET_KEY or "makonbook").encode("utf-8", errors="ignore")
    return hmac.new(secret, value.encode("utf-8", errors="ignore"), hashlib.sha256).hexdigest()


def _client_ip(request) -> str:
    return (request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR") or "unknown").strip()[:128]


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default)).strip()))
    except (TypeError, ValueError):
        return default


def _consume(scope: str, raw_key: str, *, limit: int, window_seconds: int) -> AuthRateLimitResult:
    if not raw_key or limit <= 0 or window_seconds <= 0:
        return AuthRateLimitResult(True)

    now = int(time.time())
    window_id = now // window_seconds
    retry_after = max(1, window_seconds - (now % window_seconds))
    key = f"auth:v43:{scope}:{window_id}:{_digest(f'{scope}:{raw_key}')}"

    try:
        cache.add(key, 0, timeout=window_seconds + 5)
        hits = cache.incr(key)
    except Exception:
        logger.warning("Authentication rate-limit backend unavailable; allowing request.", exc_info=True)
        return AuthRateLimitResult(True)

    if hits > limit:
        return AuthRateLimitResult(False, retry_after=retry_after, scope=scope)
    return AuthRateLimitResult(True)


def check_auth_rate_limit(request, *, action: str, identifier: str = "") -> AuthRateLimitResult:
    action = (action or "").strip().lower()
    identifier = (identifier or "").strip().casefold()
    ip = _client_ip(request)

    configs = {
        "login": (
            ("login_ip", ip, _env_int("AUTH_LOGIN_IP_MAX", 40), _env_int("AUTH_LOGIN_WINDOW_SECONDS", 600)),
            ("login_identifier", identifier, _env_int("AUTH_LOGIN_IDENTIFIER_MAX", 10), _env_int("AUTH_LOGIN_WINDOW_SECONDS", 600)),
        ),
        "forgot_password": (
            ("forgot_ip", ip, _env_int("AUTH_FORGOT_IP_MAX", 15), _env_int("AUTH_FORGOT_WINDOW_SECONDS", 900)),
            ("forgot_identifier", identifier, _env_int("AUTH_FORGOT_IDENTIFIER_MAX", 3), _env_int("AUTH_FORGOT_WINDOW_SECONDS", 900)),
        ),
        "reset_password": (
            ("reset_ip", ip, _env_int("AUTH_RESET_IP_MAX", 30), _env_int("AUTH_RESET_WINDOW_SECONDS", 900)),
            ("reset_identifier", identifier, _env_int("AUTH_RESET_IDENTIFIER_MAX", 10), _env_int("AUTH_RESET_WINDOW_SECONDS", 900)),
        ),
        "temporary_password": (
            ("temp_ip", ip, _env_int("AUTH_TEMP_PASSWORD_IP_MAX", 20), _env_int("AUTH_TEMP_PASSWORD_WINDOW_SECONDS", 900)),
            ("temp_user", identifier, _env_int("AUTH_TEMP_PASSWORD_USER_MAX", 5), _env_int("AUTH_TEMP_PASSWORD_WINDOW_SECONDS", 900)),
        ),
    }

    for scope, raw_key, limit, window_seconds in configs.get(action, ()):
        result = _consume(scope, raw_key, limit=limit, window_seconds=window_seconds)
        if not result.allowed:
            return result
    return AuthRateLimitResult(True)
