"""
Exercise Broadcasting (job description) APIs in order.

Requires a user with a completed organization (onboarding). The script either:
  - Uses JWT_TOKEN from the environment, or
  - Runs sign-up OTP + verify + onboarding/register (same pattern as test_auth_onboarding_flow).

API sequence:
  1) POST /api/broadcasting/generate-jd  (or DB stub if SKIP_GENERATE_JD=1)
  2) GET  /api/broadcasting/jd/{jd_id}
  3) PUT  /api/broadcasting/jd/{jd_id}
  4) DELETE /api/broadcasting/jd/{jd_id}
  5) GET  /api/broadcasting/jd/{jd_id}  (expect not found)

Prerequisites:
  - API running from Backend (uvicorn main:app ...)
  - Run: cd Backend && python -m scripts.test_broadcasting_flow

Environment:
  BASE_URL          default http://127.0.0.1:8000
  JWT_TOKEN         if set, skips sign-up (user must have completed onboarding)
  TEST_EMAIL        for auto sign-up (default: random hm_broadcast_*@example.com)
  MANUAL_OTP=1      paste OTP from email instead of reading from DB
  SKIP_GENERATE_JD=1  skip OpenAI: insert a stub JD via DB, then test GET/PUT/DELETE only
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime
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
    timeout: float = 60.0,
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
        with urllib.request.urlopen(req, timeout=timeout) as resp:
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


def _url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}{path}"


def _obtain_token_via_signup(base_url: str, email: str, manual_otp: bool) -> str:
    del manual_otp  # public register does not use OTP
    print("Sign-up: POST /api/onboarding/register (public, no JWT)")
    reg_body = {
        "email": email,
        "member_name": "Broadcast Test User",
        "organization_name": f"Broadcast Org {uuid.uuid4().hex[:8]}",
        "contact": "+15550200",
        "address": "2 Test Avenue",
        "team_size": "1-10",
        "website": "https://example.com",
        "password": "Abcd1234",
    }
    status, onboard_json = _http_json(
        "POST",
        _url(base_url, "/api/onboarding/register"),
        reg_body,
    )
    if status >= 400:
        raise RuntimeError(f"onboarding/register HTTP {status}: {onboard_json}")
    data = _expect_envelope("onboarding/register", onboard_json, want_status=True)
    token = data.get("access_token")
    if not token:
        raise AssertionError("onboarding/register: missing access_token")
    return str(token)


def _ensure_token(base_url: str, manual_otp: bool) -> str:
    existing = os.getenv("JWT_TOKEN", "").strip()
    if existing:
        print("Using JWT_TOKEN from environment")
        status, me = _http_json(
            "GET",
            _url(base_url, "/api/onboarding/me"),
            None,
            {"Authorization": f"Bearer {existing}"},
        )
        if status >= 400:
            raise RuntimeError(f"JWT_TOKEN invalid (onboarding/me HTTP {status}): {me}")
        _expect_envelope("onboarding/me (JWT_TOKEN check)", me, want_status=True)
        return existing

    email = os.getenv("TEST_EMAIL")
    if not email:
        email = f"hm_broadcast_{uuid.uuid4().hex[:12]}@example.com"
    print(f"Sign-up flow for {email}")
    return _obtain_token_via_signup(base_url, email, manual_otp)


def _user_id_from_token(token: str) -> str:
    from utils.jwt_utils import decode_access_token

    payload = decode_access_token(token)
    sub = payload.get("sub")
    if not sub:
        raise AssertionError("JWT missing sub")
    return str(sub)


def _insert_stub_jd(user_id: str) -> str:
    from database.database import SessionLocal
    from database.models import JobDescription, generate_uuid
    from utils.organization_utils import get_organization_for_owner

    db = SessionLocal()
    try:
        org = get_organization_for_owner(db, user_id)
        if not org:
            raise RuntimeError("No organization for user; complete onboarding first.")
        now = datetime.utcnow()
        jid = generate_uuid()
        row = JobDescription(
            id=jid,
            organization_id=org.id,
            created_by_user_id=user_id,
            hr_query="Stub HR query for API test",
            role="Stub Role",
            experience="Stub experience",
            requirements="Stub requirements",
            responsibilities="Stub responsibilities",
            qualifications="Stub qualifications",
            eligibility="Stub eligibility",
            application_link=None,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        return jid
    finally:
        db.close()


def main() -> int:
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    manual_otp = _env_bool("MANUAL_OTP", False)
    skip_generate = _env_bool("SKIP_GENERATE_JD", False)

    print(f"BASE_URL={base_url}")
    print(f"SKIP_GENERATE_JD={skip_generate}")
    print(f"MANUAL_OTP={manual_otp}")
    print()

    token = _ensure_token(base_url, manual_otp)
    auth = {"Authorization": f"Bearer {token}"}
    user_id = _user_id_from_token(token)

    if skip_generate:
        print("1) SKIP_GENERATE_JD: insert stub job_descriptions row via DB")
        jd_id = _insert_stub_jd(user_id)
        print(f"    jd_id={jd_id}")
    else:
        print("1) POST /api/broadcasting/generate-jd (OpenAI; may take a while)")
        status, gen_json = _http_json(
            "POST",
            _url(base_url, "/api/broadcasting/generate-jd"),
            {
                "query": "Hire a senior backend engineer with Python, FastAPI, and PostgreSQL experience."
            },
            auth,
            timeout=180.0,
        )
        if status >= 400:
            raise RuntimeError(f"generate-jd HTTP {status}: {gen_json}")
        data = _expect_envelope("generate-jd", gen_json, want_status=True)
        jd_id = data.get("jd_id")
        if not jd_id:
            raise AssertionError("generate-jd: missing jd_id in data")

    print("2) GET /api/broadcasting/jd/{jd_id}")
    status, get_json = _http_json(
        "GET",
        _url(base_url, f"/api/broadcasting/jd/{jd_id}"),
        None,
        auth,
    )
    if status >= 400:
        raise RuntimeError(f"get jd HTTP {status}: {get_json}")
    _expect_envelope("get jd", get_json, want_status=True)

    print("3) PUT /api/broadcasting/jd/{jd_id}")
    status, put_json = _http_json(
        "PUT",
        _url(base_url, f"/api/broadcasting/jd/{jd_id}"),
        {"role": "Updated role title (API test)"},
        auth,
    )
    if status >= 400:
        raise RuntimeError(f"put jd HTTP {status}: {put_json}")
    _expect_envelope("put jd", put_json, want_status=True)

    print("4) DELETE /api/broadcasting/jd/{jd_id}")
    status, del_json = _http_json(
        "DELETE",
        _url(base_url, f"/api/broadcasting/jd/{jd_id}"),
        None,
        auth,
    )
    if status >= 400:
        raise RuntimeError(f"delete jd HTTP {status}: {del_json}")
    _expect_envelope("delete jd", del_json, want_status=True)

    print("5) GET /api/broadcasting/jd/{jd_id} (expect not found)")
    status, gone_json = _http_json(
        "GET",
        _url(base_url, f"/api/broadcasting/jd/{jd_id}"),
        None,
        auth,
    )
    if status >= 400:
        raise RuntimeError(f"get jd after delete HTTP {status}: {gone_json}")
    _expect_envelope("get jd after delete", gone_json, want_status=False)

    print()
    print("Broadcasting API sequence completed successfully.")
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
