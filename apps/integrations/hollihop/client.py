from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import date, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)


class HollihopError(RuntimeError):
    pass


class HollihopConfigurationError(HollihopError):
    pass


class HollihopAPIError(HollihopError):
    pass


class HollihopClient:
    """Small server-side Hollihop API v2 client.

    Read methods are sent as POST form bodies so authkey never appears in the
    URL/access logs. Hollihop documents both GET and POST for read methods.
    """

    def __init__(self, *, api_url=None, auth_key=None, timeout=None):
        self.api_url = (api_url or settings.HOLLIHOP_API_URL).rstrip("/")
        self.auth_key = auth_key or settings.HOLLIHOP_AUTH_KEY
        self.timeout = int(timeout or settings.HOLLIHOP_TIMEOUT_SECONDS)
        self.max_retries = int(settings.HOLLIHOP_MAX_RETRIES)
        self.min_interval = float(settings.HOLLIHOP_MIN_REQUEST_INTERVAL)
        self._last_request_at = 0.0
        if not self.api_url or not self.auth_key:
            raise HollihopConfigurationError("HOLLIHOP_API_URL and HOLLIHOP_AUTH_KEY are required.")
        parsed = urlparse(self.api_url)
        # The configured URL must be the API v2 *base*, never a concrete
        # function such as /AddStudyRequest. Otherwise appending GetStudents
        # could accidentally hit a write endpoint on a misconfigured server.
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.query
            or parsed.fragment
            or parsed.path.rstrip("/").casefold()[-7:] != "/api/v2"
        ):
            raise HollihopConfigurationError(
                "HOLLIHOP_API_URL must be the API v2 base URL and end with /Api/V2 "
                "(for example https://school.t8s.ru/Api/V2). Do not include a function name."
            )

    def _throttle(self):
        remaining = self.min_interval - (time.monotonic() - self._last_request_at)
        if remaining > 0:
            time.sleep(remaining)

    def _request(self, function: str, params: dict | None = None) -> dict:
        data = {"authkey": self.auth_key}
        for key, value in (params or {}).items():
            if value is None or value == "":
                continue
            if isinstance(value, bool):
                value = "true" if value else "false"
            elif isinstance(value, (date, datetime)):
                value = value.isoformat()
            data[key] = value
        encoded = urlencode(data, doseq=True).encode("utf-8")
        request = Request(
            f"{self.api_url}/{function}",
            data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            method="POST",
        )
        last_error = None
        for attempt in range(self.max_retries + 1):
            self._throttle()
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    self._last_request_at = time.monotonic()
                    raw = response.read().decode("utf-8", errors="replace")
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise HollihopAPIError("Hollihop returned a non-object JSON response.")
                api_error = payload.get("Error") or payload.get("error")
                if api_error:
                    message = str(api_error)[:500]
                    # Hollihop documents a hard burst limit of 600 requests per
                    # 30 seconds. Treat its textual limit error like HTTP 429 so
                    # transient bursts are retried with backoff instead of
                    # aborting the whole synchronization immediately.
                    if "requests limit is exceeded" in message.casefold():
                        last_error = HollihopAPIError(message)
                        if attempt >= self.max_retries:
                            raise last_error
                        time.sleep(min(8.0, 1.0 * (2 ** attempt)))
                        continue
                    raise HollihopAPIError(message)
                return payload
            except HTTPError as exc:
                self._last_request_at = time.monotonic()
                body = ""
                try:
                    body = exc.read().decode("utf-8", errors="replace")[:500]
                except Exception:
                    pass
                last_error = HollihopAPIError(f"Hollihop HTTP {exc.code}: {body or exc.reason}")
                if exc.code not in {429, 500, 502, 503, 504} or attempt >= self.max_retries:
                    raise last_error
            except (URLError, TimeoutError, json.JSONDecodeError) as exc:
                self._last_request_at = time.monotonic()
                last_error = HollihopAPIError(f"Hollihop request failed: {type(exc).__name__}")
                if attempt >= self.max_retries:
                    raise last_error
            time.sleep(min(4.0, 0.5 * (2 ** attempt)))
        raise last_error or HollihopAPIError("Hollihop request failed.")

    def _paginate(self, function: str, result_key: str, params: dict | None = None) -> list[dict]:
        params = dict(params or {})
        take = min(int(params.pop("take", settings.HOLLIHOP_PAGE_SIZE)), 10000)
        skip = int(params.pop("skip", 0))
        max_pages = int(getattr(settings, "HOLLIHOP_MAX_PAGES", 100))
        result: list[dict] = []
        seen_full_page_fingerprints: set[str] = set()

        for page_number in range(1, max_pages + 1):
            payload = self._request(function, {**params, "skip": skip, "take": take})
            page = payload.get(result_key) or []
            if not isinstance(page, list):
                raise HollihopAPIError(f"Expected {result_key} to be a list.")

            if len(page) == take:
                # A broken upstream `skip` implementation can otherwise return
                # the same full page forever. Hollihop explicitly warns that
                # uncontrolled repeated API calls can block the account, so
                # fail closed before issuing another identical request.
                serialized = json.dumps(page, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
                fingerprint = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
                if fingerprint in seen_full_page_fingerprints:
                    raise HollihopAPIError(
                        f"Hollihop pagination repeated the same full {result_key} page; aborted to protect the API account."
                    )
                seen_full_page_fingerprints.add(fingerprint)

            result.extend(page)
            if len(page) < take:
                return result
            skip += take

        raise HollihopAPIError(
            f"Hollihop pagination exceeded the safety limit of {max_pages} pages for {function}."
        )

    def get_students(self, *, client_id=None, last_updated_from=None) -> list[dict]:
        return self._paginate(
            "GetStudents",
            "Students",
            {"clientId": client_id, "lastUpdatedFrom": last_updated_from},
        )

    def get_employees(self, *, employee_id=None, corporative=None) -> list[dict]:
        """Return Hollihop employees (GetEmployees excludes teachers)."""
        return self._paginate(
            "GetEmployees",
            "Employees",
            {"id": employee_id, "corporative": corporative},
        )

    def get_teachers(self, *, teacher_id=None) -> list[dict]:
        return self._paginate("GetTeachers", "Teachers", {"id": teacher_id})

    def get_ed_units(
        self,
        *,
        edunit_id=None,
        corporative=None,
        statuses=None,
        last_updated_from=None,
        learning_types=None,
        teacher_id=None,
    ) -> list[dict]:
        if learning_types is None:
            learning_types = getattr(settings, "HOLLIHOP_ALLOWED_LEARNING_TYPES", ())
        if isinstance(learning_types, (list, tuple, set, frozenset)):
            learning_types = ",".join(str(value).strip() for value in learning_types if str(value).strip())
        return self._paginate(
            "GetEdUnits",
            "EdUnits",
            {
                "id": edunit_id,
                "types": "Group,MiniGroup",
                "corporative": corporative,
                "statuses": statuses,
                "lastUpdatedFrom": last_updated_from,
                # GetEdUnits officially supports the `learningTypes` filter.
                # This reduces payload size; sync.py applies the same rule again
                # locally so a server-side filtering regression cannot leak
                # ONLINE / IV ONLINE / IV OFFLINE groups into MakonBook.
                "learningTypes": learning_types,
                "teacherId": teacher_id,
            },
        )

    def get_ed_unit_students(
        self,
        *,
        edunit_id=None,
        student_client_id=None,
        corporative=None,
        date_from=None,
        date_to=None,
        query_days=False,
    ) -> list[dict]:
        return self._paginate(
            "GetEdUnitStudents",
            "EdUnitStudents",
            {
                "edUnitId": edunit_id,
                "studentClientId": student_client_id,
                "edUnitTypes": "Group,MiniGroup",
                "edUnitCorporative": corporative,
                "dateFrom": date_from,
                "dateTo": date_to,
                "queryDays": query_days,
            },
        )
