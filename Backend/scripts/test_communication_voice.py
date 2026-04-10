"""
Test the Communication API voice interview (Retell outbound) for a fixed phone number.

Prerequisites
-------------
- Server running (e.g. ``uvicorn main:app --reload``).
- ``RETELL_API_KEY``, ``RETELL_AGENT_ID``, ``RETELL_FROM_NUMBER`` set in ``.env``.
- A candidate in **your** org with ``screening_status == shortlisted`` (parser run or DB),
  or pass ``--candidate-id`` (fetched via GET ``/api/careers/applications/{id}``).
- Employer JWT (same as browser after login).

Environment
-----------
  HIREMANTRA_JWT         Required. Bearer token (without the word ``Bearer``).
  HIREMANTRA_API_BASE    Optional. Default ``http://127.0.0.1:8000``.

Examples
--------
  cd Backend
  export HIREMANTRA_JWT='<paste_access_token>'
  python -m scripts.test_communication_voice

  python -m scripts.test_communication_voice --phone 7987214753
  python -m scripts.test_communication_voice --jd-id <job_description_uuid>
  python -m scripts.test_communication_voice --candidate-id <candidate_uuid>
  python -m scripts.test_communication_voice --list-only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

# Default test number (India 10-digit; normalized to +91… in backend)
DEFAULT_TEST_PHONE = "7987214753"


def _load_dotenv_backend() -> None:
    try:
        from dotenv import load_dotenv

        env_path = Path(__file__).resolve().parent.parent / ".env"
        load_dotenv(env_path)
    except ImportError:
        pass


def _headers(token: str) -> dict[str, str]:
    t = token.strip()
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


def _get_json(
    client: httpx.Client, url: str, headers: dict, *, verbose: bool = False
) -> dict:
    r = client.get(url, headers=headers, timeout=60.0)
    if verbose:
        print(f"[verbose] GET {url} -> HTTP {r.status_code}", file=sys.stderr)
    try:
        return r.json()
    except Exception:
        print(r.text, file=sys.stderr)
        r.raise_for_status()
        raise


def _post_json(client: httpx.Client, url: str, headers: dict, body: dict) -> tuple[int, dict]:
    r = client.post(url, headers=headers, json=body, timeout=120.0)
    try:
        return r.status_code, r.json()
    except Exception:
        print(r.text, file=sys.stderr)
        return r.status_code, {}


def main() -> int:
    _load_dotenv_backend()
    p = argparse.ArgumentParser(description="Schedule communication voice test call via API")
    p.add_argument(
        "--base-url",
        default=os.getenv("HIREMANTRA_API_BASE", "http://127.0.0.1:8000").rstrip("/"),
    )
    p.add_argument(
        "--token",
        default=os.getenv("HIREMANTRA_JWT", ""),
        help="Or set HIREMANTRA_JWT",
    )
    p.add_argument("--phone", default=DEFAULT_TEST_PHONE, help="Callee (default 7987214753)")
    p.add_argument("--jd-id", default="", help="Filter applications to this job description UUID")
    p.add_argument("--candidate-id", default="", help="Skip discovery; use this candidate UUID")
    p.add_argument(
        "--invite-email",
        action="store_true",
        help="Also send interview invite email (needs candidate email or --invite-to)",
    )
    p.add_argument("--invite-to", default="", help="Email for invite when --invite-email")
    p.add_argument("--list-only", action="store_true", help="Only list applications and exit")
    p.add_argument(
        "--sync-session",
        default="",
        metavar="SESSION_ID",
        help="After scheduling, call sync on this session (use when call finished)",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print HTTP status for GET /applications",
    )
    args = p.parse_args()

    if not args.token:
        print(
            "Missing JWT. Set HIREMANTRA_JWT or pass --token "
            "(copy access_token from POST /api/auth/verify-otp or /api/onboarding/register).",
            file=sys.stderr,
        )
        return 1

    base = args.base_url
    h = _headers(args.token)

    with httpx.Client() as client:
        candidate_id = (args.candidate_id or "").strip()
        chosen = None

        # Load one candidate by id (works even when the list is empty — e.g. you copied UUID from DB).
        if candidate_id:
            one_url = f"{base}/api/careers/applications/{candidate_id}"
            one = _get_json(client, one_url, h, verbose=args.verbose)
            if not one.get("status"):
                print(json.dumps(one, indent=2), file=sys.stderr)
                print(
                    "\nHint: 404/forbidden means this candidate is not under your org, or id is wrong.",
                    file=sys.stderr,
                )
                return 1
            chosen = one.get("data") or {}
            if not chosen.get("id"):
                print("Unexpected response: missing data.id", file=sys.stderr)
                return 1
            if args.list_only:
                print(json.dumps(chosen, indent=2))
                return 0
        else:
            apps_url = f"{base}/api/careers/applications"
            if args.jd_id:
                apps_url = f"{apps_url}?jd_id={args.jd_id}"

            apps = _get_json(client, apps_url, h, verbose=args.verbose)

            if not apps.get("status"):
                print(json.dumps(apps, indent=2))
                return 1

            applications = (apps.get("data") or {}).get("applications") or []

            if args.list_only:
                print(json.dumps(applications, indent=2))
                print(f"\nTotal: {len(applications)} (filter jd_id={args.jd_id or 'any'})")
                return 0

            short = [a for a in applications if (a.get("screening_status") or "") == "shortlisted"]
            pool = short if short else applications
            if not pool:
                print(
                    f"No applications for this account (API base: {base}).\n"
                    "  • Create a job (broadcasting), then submit an application:\n"
                    "    POST /api/careers/apply with jd_id, name, contact, resume.\n"
                    "  • Or pass a known row: --candidate-id <uuid> (from DB or GET after you have one).\n"
                    "  • Use the same JWT user that owns the organization.\n"
                    "  • If the API is remote, set HIREMANTRA_API_BASE or --base-url.",
                    file=sys.stderr,
                )
                return 1
            if not short:
                print(
                    "No shortlisted candidates. Voice schedule requires screening_status=shortlisted.\n"
                    "  • Run parser on the application, or in MySQL:\n"
                    "    UPDATE candidates SET screening_status='shortlisted' WHERE id='<candidate_uuid>';\n"
                    "  • Or: python -m scripts.test_communication_voice --candidate-id <uuid>",
                    file=sys.stderr,
                )
                return 1
            chosen = short[0]

        st = (chosen.get("screening_status") or "").strip()
        if st != "shortlisted":
            print(
                f"Candidate {chosen.get('id')} has screening_status={st!r}, not 'shortlisted'. "
                "Voice schedule will be rejected by the API.\n"
                "  Fix: run resume parser for this candidate, or set shortlisted in DB, then retry.",
                file=sys.stderr,
            )
            return 1

        cid = chosen["id"]
        print(
            f"Using candidate {cid} | jd_id={chosen.get('jd_id')} | "
            f"status={chosen.get('screening_status')} | phone_override={args.phone}"
        )

        body: dict = {
            "to_number": args.phone,
            "send_interview_invite_email": bool(args.invite_email),
        }
        if args.invite_to:
            body["invite_to_email"] = args.invite_to

        sched_url = f"{base}/api/communication/candidates/{cid}/voice-interviews/schedule"
        code, out = _post_json(client, sched_url, h, body)
        print(json.dumps(out, indent=2))

        if not out.get("status"):
            return 1

        session_id = (out.get("data") or {}).get("session_id")
        if session_id:
            print(f"\nSession id: {session_id}")
            print(
                "After the call ends, sync transcript + score:\n"
                f'  curl -X POST -H "Authorization: Bearer $HIREMANTRA_JWT" '
                f'"{base}/api/communication/voice-interviews/{session_id}/sync"'
            )

        sync_sid = (args.sync_session or "").strip()
        if sync_sid:
            sync_url = f"{base}/api/communication/voice-interviews/{sync_sid}/sync"
            _, sync_out = _post_json(client, sync_url, h, {})
            print("\n--- sync ---")
            print(json.dumps(sync_out, indent=2))
            return 0 if sync_out.get("status") else 1

        return 0 if out.get("status") else 1


if __name__ == "__main__":
    raise SystemExit(main())
