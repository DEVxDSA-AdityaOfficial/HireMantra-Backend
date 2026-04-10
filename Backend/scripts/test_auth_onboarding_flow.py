"""
End-to-end API check: public onboarding register, then login OTP flow.

Prerequisites:
  - API running (e.g. uvicorn main:app --reload --host 0.0.0.0 --port 8000)
  - Run from the Backend directory so imports and .env resolve

Usage:
  cd Backend
  python -m scripts.test_auth_onboarding_flow

  MANUAL_OTP=1 python -m scripts.test_auth_onboarding_flow   # paste OTP after login request-otp
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

load_dotenv(_ROOT / ".env")


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _fetch_otp_from_db(email: str) -> str:
    from database.database import SessionLocal
    from database.models import Users

    normalized = email.strip().lower()
    db = SessionLocal()
    try:
        user = db.query(Users).filter(Users.email == normalized).first()
        if not user or not user.otp:
            raise RuntimeError(
                f"No OTP stored for {normalized}. Request OTP first or use MANUAL_OTP=1."
            )
        return str(user.otp).strip()
    finally:
        db.close()


def _prompt_otp(email: str) -> str:
    return input(f"Enter OTP sent to {email}: ").strip()


def _get_otp(email: str, manual: bool) -> str:
    if manual:
        return _prompt_otp(email)
    return _fetch_otp_from_db(email)


def _http_json(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    h = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if headers:
        h.update(headers)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        status = e.code
    if not raw.strip():
        return status, {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"Non-JSON response (HTTP {status}): {raw[:500]}") from None
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Expected JSON object, got {type(parsed)}")
    return status, parsed


def _expect_envelope(
    step: str, data: dict[str, Any], want_status: bool = True
) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise AssertionError(f"{step}: expected JSON object, got {type(data)}")
    if "status" not in data:
        raise AssertionError(f"{step}: missing 'status' in {data}")
    if data.get("status") is not want_status:
        raise AssertionError(
            f"{step}: expected status={want_status}, got {data!r}"
        )
    return data.get("data") or {}


def main() -> int:
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    manual_otp = _env_bool("MANUAL_OTP", False)
    skip_delete = _env_bool("SKIP_DELETE", False)

    email = os.getenv("TEST_EMAIL")
    if not email:
        email = f"hm_flow_{uuid.uuid4().hex[:12]}@example.com"

    print(f"BASE_URL={base_url}")
    print(f"TEST_EMAIL={email}")
    print(f"MANUAL_OTP={manual_otp}")
    print()

    def url(path: str) -> str:
        return f"{base_url}{path}"

    print("0) POST /api/auth/request-otp (before onboard → no OTP, is_exist 0)")
    status, pre = _http_json("POST", url("/api/auth/request-otp"), {"email": email})
    if status >= 400:
        raise RuntimeError(f"request-otp HTTP {status}: {pre}")
    if pre.get("status") is not False:
        raise AssertionError(f"expected status False before onboard, got {pre!r}")
    dpre = pre.get("data") or {}
    if dpre.get("is_exist") != 0:
        raise AssertionError(f"expected is_exist 0, got {pre!r}")

    print("1) POST /api/onboarding/register (public, includes email)")
    reg_body = {
        "email": email,
        "member_name": "Flow Test User",
        "organization_name": f"Flow Org {uuid.uuid4().hex[:8]}",
        "contact": "+15550100",
        "address": "1 Test Street",
        "team_size": "1-10",
        "website": "https://example.com",
        "password": "TestPass123!",
    }
    status, reg_json = _http_json(
        "POST",
        url("/api/onboarding/register"),
        reg_body,
    )
    if status >= 400:
        raise RuntimeError(f"onboarding/register HTTP {status}: {reg_json}")
    reg_data = _expect_envelope("onboarding/register", reg_json, want_status=True)
    if reg_data.get("is_exist") != 1 or not reg_data.get("access_token"):
        raise AssertionError(f"expected is_exist 1 + token, got {reg_data!r}")
    auth_headers = {"Authorization": f"Bearer {reg_data['access_token']}"}

    print("2) GET /api/onboarding/me")
    status, me_get = _http_json("GET", url("/api/onboarding/me"), None, auth_headers)
    if status >= 400:
        raise RuntimeError(f"onboarding/me GET HTTP {status}: {me_get}")
    _expect_envelope("onboarding/me GET", me_get, want_status=True)

    print("3) PATCH /api/onboarding/me")
    status, me_patch = _http_json(
        "PATCH",
        url("/api/onboarding/me"),
        {"member_name": "Flow Test User (updated)"},
        auth_headers,
    )
    if status >= 400:
        raise RuntimeError(f"onboarding/me PATCH HTTP {status}: {me_patch}")
    _expect_envelope("onboarding/me PATCH", me_patch, want_status=True)

    print("4) POST /api/auth/request-otp (login, is_exist 1)")
    status, login_otp_json = _http_json(
        "POST", url("/api/auth/request-otp"), {"email": email}
    )
    if status >= 400:
        raise RuntimeError(f"request-otp (login) HTTP {status}: {login_otp_json}")
    d_login = _expect_envelope("auth/request-otp (login)", login_otp_json, want_status=True)
    if d_login.get("is_exist") != 1:
        raise AssertionError(f"expected is_exist 1, got {d_login!r}")

    otp2 = _get_otp(email, manual_otp)
    print("5) POST /api/auth/verify-otp")
    status, verify2 = _http_json(
        "POST",
        url("/api/auth/verify-otp"),
        {"email": email, "otp": otp2},
    )
    if status >= 400:
        raise RuntimeError(f"verify-otp HTTP {status}: {verify2}")
    data2 = _expect_envelope("verify-otp (login)", verify2, want_status=True)
    if data2.get("is_exist") != 1:
        raise AssertionError(f"expected is_exist 1, got {data2!r}")
    token2 = data2.get("access_token")
    if not token2:
        raise AssertionError("verify-otp: missing access_token")
    auth_headers2 = {"Authorization": f"Bearer {token2}"}

    print("6) GET /api/onboarding/me (login token)")
    status, me_login = _http_json(
        "GET", url("/api/onboarding/me"), None, auth_headers2
    )
    if status >= 400:
        raise RuntimeError(f"onboarding/me GET HTTP {status}: {me_login}")
    _expect_envelope("onboarding/me GET (login token)", me_login, want_status=True)

    print("7) POST /api/auth/register/request-otp (alias)")
    status, dup = _http_json(
        "POST", url("/api/auth/register/request-otp"), {"email": email}
    )
    if status >= 400:
        raise RuntimeError(f"register/request-otp HTTP {status}: {dup}")
    d9 = _expect_envelope("register/request-otp", dup, want_status=True)
    if d9.get("is_exist") != 1:
        raise AssertionError(f"expected is_exist 1, got {d9!r}")

    if skip_delete:
        print("SKIP_DELETE=1 — skipping DELETE /api/onboarding/me")
    else:
        print("8) DELETE /api/onboarding/me")
        status, del_json = _http_json(
            "DELETE", url("/api/onboarding/me"), None, auth_headers2
        )
        if status >= 400:
            raise RuntimeError(f"onboarding/me DELETE HTTP {status}: {del_json}")
        _expect_envelope("onboarding/me DELETE", del_json, want_status=True)

        print("9) GET /api/onboarding/me (after delete)")
        status, gone = _http_json(
            "GET", url("/api/onboarding/me"), None, auth_headers2
        )
        if status >= 400:
            raise RuntimeError(f"onboarding/me after delete HTTP {status}: {gone}")
        _expect_envelope(
            "onboarding/me after delete",
            gone,
            want_status=False,
        )

    print()
    print("All steps completed successfully.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as e:
        print(f"FAILED: {e}", file=sys.stderr)
        raise SystemExit(1)
    except urllib.error.URLError as e:
        print(
            f"Connection error (is the API running at {os.getenv('BASE_URL', 'http://127.0.0.1:8000')}?): {e}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1)
