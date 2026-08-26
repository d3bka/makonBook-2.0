from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
import uuid
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache

from .normalization import normalize_phone


class SmsDeliveryError(RuntimeError):
    """Safe, user-displayable SMS delivery failure.

    Provider credentials, bearer tokens and raw response bodies must never be
    included in this exception because callers persist the text in audit logs.
    """


class _SmsHttpError(RuntimeError):
    def __init__(self, status_code: int):
        super().__init__(f"HTTP {status_code}")
        self.status_code = int(status_code)


@dataclass(frozen=True)
class SmsSendResult:
    provider: str
    message_id: str = ""
    status: str = "accepted"


def _timeout_seconds() -> int:
    return max(3, int(getattr(settings, "MAKONBOOK_SMS_TIMEOUT_SECONDS", 15)))


def _read_json(response) -> dict[str, Any]:
    raw = response.read()
    if not raw:
        return {}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SmsDeliveryError("SMS provider returned an invalid response.") from exc
    if not isinstance(payload, dict):
        raise SmsDeliveryError("SMS provider returned an unexpected response.")
    return payload


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    request_headers = {"Content-Type": "application/json", "Accept": "application/json"}
    request_headers.update(headers or {})
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=request_headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=_timeout_seconds()) as response:
            status = int(getattr(response, "status", 200))
            if status < 200 or status >= 300:
                raise _SmsHttpError(status)
            return _read_json(response)
    except HTTPError as exc:
        raise _SmsHttpError(exc.code) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise SmsDeliveryError("SMS provider is unavailable.") from exc


def _encode_multipart_form(payload: dict[str, Any]) -> tuple[bytes, str]:
    """Encode simple text fields as multipart/form-data for Eskiz endpoints."""
    boundary = f"----MakonBookEskiz{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for key, value in payload.items():
        if value is None:
            continue
        chunks.extend([
            f"--{boundary}\r\n".encode("ascii"),
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"),
            str(value).encode("utf-8"),
            b"\r\n",
        ])
    chunks.append(f"--{boundary}--\r\n".encode("ascii"))
    return b"".join(chunks), boundary


def _post_form(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    body, boundary = _encode_multipart_form(payload)
    request_headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept": "application/json",
    }
    request_headers.update(headers or {})
    request = Request(
        url,
        data=body,
        headers=request_headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=_timeout_seconds()) as response:
            status = int(getattr(response, "status", 200))
            if status < 200 or status >= 300:
                raise _SmsHttpError(status)
            return _read_json(response)
    except HTTPError as exc:
        raise _SmsHttpError(exc.code) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise SmsDeliveryError("SMS provider is unavailable.") from exc


def _eskiz_cache_key() -> str:
    email = str(getattr(settings, "ESKIZ_EMAIL", "") or "").strip().casefold()
    suffix = hashlib.sha256(email.encode("utf-8")).hexdigest()[:16] if email else "unset"
    return f"makonbook:sms:eskiz:token:{suffix}"


def _eskiz_authenticate(*, force_refresh: bool = False) -> str:
    email = str(getattr(settings, "ESKIZ_EMAIL", "") or "").strip()
    password = str(getattr(settings, "ESKIZ_PASSWORD", "") or "")
    auth_url = str(getattr(settings, "ESKIZ_AUTH_URL", "") or "").strip()

    if not email or not password:
        raise SmsDeliveryError("Eskiz credentials are not configured.")
    if not auth_url:
        raise SmsDeliveryError("ESKIZ_AUTH_URL is not configured.")

    key = _eskiz_cache_key()
    if not force_refresh:
        cached = cache.get(key)
        if cached:
            return str(cached)

    try:
        payload = _post_form(auth_url, {"email": email, "password": password})
    except _SmsHttpError as exc:
        if exc.status_code in {400, 401, 403, 422}:
            raise SmsDeliveryError("Eskiz authentication was rejected. Check ESKIZ_EMAIL and ESKIZ_PASSWORD.") from exc
        if exc.status_code == 429:
            raise SmsDeliveryError("Eskiz authentication is rate-limited. Try again later.") from exc
        raise SmsDeliveryError(f"Eskiz authentication returned HTTP {exc.status_code}.") from exc

    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    token = str(data.get("token") or payload.get("token") or "").strip()
    if not token:
        raise SmsDeliveryError("Eskiz authentication succeeded but no token was returned.")

    ttl = max(60, int(getattr(settings, "ESKIZ_TOKEN_CACHE_SECONDS", 21600)))
    cache.set(key, token, ttl)
    return token


def _eskiz_phone(phone: str) -> str:
    normalized = normalize_phone(phone)
    if not normalized:
        raise SmsDeliveryError("SMS recipient phone number is invalid.")
    return normalized.lstrip("+")


def _eskiz_response_result(payload: dict[str, Any]) -> SmsSendResult:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    message_id = str(
        payload.get("id")
        or payload.get("message_id")
        or data.get("id")
        or data.get("message_id")
        or ""
    ).strip()
    status = str(payload.get("status") or data.get("status") or "accepted").strip().lower()

    # Eskiz currently returns statuses such as "waiting" after a successful
    # queue operation. Treat explicit error-like statuses as a provider failure
    # even if an HTTP proxy returned 2xx.
    if status in {"error", "failed", "failure", "rejected"}:
        raise SmsDeliveryError("Eskiz rejected the SMS request.")

    return SmsSendResult(provider="eskiz", message_id=message_id, status=status or "accepted")


def _send_eskiz(phone: str, message: str) -> SmsSendResult:
    send_url = str(getattr(settings, "ESKIZ_SEND_URL", "") or "").strip()
    sender = str(getattr(settings, "ESKIZ_SENDER", "4546") or "").strip()
    if not send_url:
        raise SmsDeliveryError("ESKIZ_SEND_URL is not configured.")
    if not sender:
        raise SmsDeliveryError("ESKIZ_SENDER is not configured.")
    if not str(message or "").strip():
        raise SmsDeliveryError("SMS message is empty.")

    recipient = _eskiz_phone(phone)

    for attempt in range(2):
        token = _eskiz_authenticate(force_refresh=attempt > 0)
        try:
            send_payload = {
                "mobile_phone": recipient,
                "message": str(message),
                "from": sender,
            }
            callback_url = str(getattr(settings, "ESKIZ_CALLBACK_URL", "") or "").strip()
            if callback_url:
                send_payload["callback_url"] = callback_url
            payload = _post_form(
                send_url,
                send_payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            return _eskiz_response_result(payload)
        except _SmsHttpError as exc:
            if exc.status_code == 401 and attempt == 0:
                cache.delete(_eskiz_cache_key())
                continue
            if exc.status_code in {400, 403, 404, 422}:
                raise SmsDeliveryError(
                    "Eskiz rejected the SMS request. Check the phone, sender and approved SMS template."
                ) from exc
            if exc.status_code == 429:
                raise SmsDeliveryError("Eskiz SMS sending is rate-limited. Try again later.") from exc
            raise SmsDeliveryError(f"Eskiz SMS gateway returned HTTP {exc.status_code}.") from exc

    raise SmsDeliveryError("Eskiz authentication failed after token refresh.")


def _send_generic_http(phone: str, message: str) -> SmsSendResult:
    api_url = str(getattr(settings, "MAKONBOOK_SMS_API_URL", "") or "").strip()
    if not api_url:
        raise SmsDeliveryError("MAKONBOOK_SMS_API_URL is not configured.")

    payload = {
        "phone": phone,
        "message": message,
        "sender": getattr(settings, "MAKONBOOK_SMS_SENDER", "MakonBook"),
    }
    headers: dict[str, str] = {}
    api_token = str(getattr(settings, "MAKONBOOK_SMS_API_TOKEN", "") or "").strip()
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"

    try:
        response = _post_json(api_url, payload, headers=headers)
    except _SmsHttpError as exc:
        raise SmsDeliveryError(f"SMS gateway returned HTTP {exc.status_code}.") from exc

    message_id = str(response.get("id") or response.get("message_id") or "").strip()
    status = str(response.get("status") or "accepted").strip().lower()
    return SmsSendResult(provider="generic_http", message_id=message_id, status=status or "accepted")


def validate_sms_configuration() -> tuple[bool, str]:
    """Validate provider settings without sending a message or logging in."""
    provider = str(getattr(settings, "MAKONBOOK_SMS_PROVIDER", "") or "").strip().lower()
    if provider in {"", "disabled", "none"}:
        return False, "SMS provider is disabled."
    if provider == "generic_http":
        if not str(getattr(settings, "MAKONBOOK_SMS_API_URL", "") or "").strip():
            return False, "MAKONBOOK_SMS_API_URL is not configured."
        return True, "generic_http configuration is ready."
    if provider == "eskiz":
        missing = [
            name
            for name in ("ESKIZ_EMAIL", "ESKIZ_PASSWORD", "ESKIZ_SENDER", "ESKIZ_AUTH_URL", "ESKIZ_SEND_URL")
            if not str(getattr(settings, name, "") or "").strip()
        ]
        if missing:
            return False, f"Eskiz configuration is incomplete: {', '.join(missing)}."
        return True, "Eskiz configuration is ready."
    return False, f"Unsupported SMS provider: {provider}."


def send_sms(phone: str, message: str) -> SmsSendResult:
    """Send SMS through the configured provider.

    Supported providers:
      - disabled / none: safe no-send mode
      - generic_http: legacy JSON adapter
      - eskiz: native Eskiz.uz token-based API adapter
    """
    provider = str(getattr(settings, "MAKONBOOK_SMS_PROVIDER", "") or "").strip().lower()
    if provider in {"", "disabled", "none"}:
        raise SmsDeliveryError("SMS provider is disabled.")
    if provider == "generic_http":
        return _send_generic_http(phone, message)
    if provider == "eskiz":
        return _send_eskiz(phone, message)
    raise SmsDeliveryError(f"Unsupported SMS provider: {provider}")
