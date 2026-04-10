"""
HTTP tests for **Communication** APIs (employer JWT).

Endpoints (prefix ``/api/communication``)::

  POST   /candidates/{id}/emails/shortlist
  POST   /candidates/{id}/emails/rejection
  POST   /candidates/{id}/voice-interviews/schedule
  POST   /voice-interviews/{session_id}/sync
  GET    /voice-interviews?candidate_id=optional
  GET    /voice-interviews/{session_id}

Environment
-----------
  HIREMANTRA_JWT         Required (access token, no ``Bearer`` prefix in value).
  HIREMANTRA_API_BASE    Optional; default ``http://127.0.0.1:8000``.

Examples
--------
  cd Backend
  export HIREMANTRA_JWT='<token>'

  # List your applications (pick a candidate_id + screening_status)
  python -m scripts.test_communication_api --only list-apps

  # First shortlisted candidate (auto)
  python -m scripts.test_communication_api --only shortlist --auto-pick shortlisted \\
    --to-email tester@example.com

  # Explicit candidate
  python -m scripts.test_communication_api --only shortlist --candidate-id <uuid> \\
    --to-email tester@example.com

  python -m scripts.test_communication_api --only rejection --auto-pick rejected \\
    --to-email tester@example.com

  python -m scripts.test_communication_api --only schedule --auto-pick shortlisted \\
    --phone 7987214753

  python -m scripts.test_communication_api --only list-voice
  python -m scripts.test_communication_api --only get-voice --session-id <uuid>
  python -m scripts.test_communication_api --only sync --session-id <uuid>

  # Shortlist email then schedule voice (Retell must be configured on server)
  python -m scripts.test_communication_api --only pipeline --auto-pick shortlisted \\
    --to-email you@example.com --phone 7987214753
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx


def _load_dotenv_backend() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except ImportError:
        pass


def _headers(token: str) -> dict[str, str]:
    t = token.strip()
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


def _hint_wrong_jd(out: dict) -> None:
    msg = str(out.get("message") or "")
    if "does not belong" in msg or "not found" in msg.lower():
        print("\nTip: use --list-apps and a candidate under your org.", file=sys.stderr)


def _response_json(r: httpx.Response, *, verbose: bool = False) -> dict:
    """
    Parse API JSON; never raise JSONDecodeError.
    Empty or HTML bodies become a clear error dict (wrong base URL, crashed worker, etc.).
    """
    if verbose:
        ct = r.headers.get("content-type", "")
        print(f"[verbose] HTTP {r.status_code} content-type={ct!r}", file=sys.stderr)
    raw = r.text or ""
    stripped = raw.strip()
    if not stripped:
        return {
            "status": False,
            "message": (
                f"Empty HTTP body (status {r.status_code}). "
                "Check HIREMANTRA_API_BASE, that uvicorn is running, and server logs "
                "(worker may have crashed mid-request)."
            ),
            "data": None,
        }
    try:
        return r.json()
    except json.JSONDecodeError:
        preview = stripped[:1200]
        return {
            "status": False,
            "message": (
                f"Response is not JSON (HTTP {r.status_code}). "
                "Wrong port/host, proxy error page, or server returned HTML."
            ),
            "data": {"body_preview": preview},
        }


def _get_applications(client: httpx.Client, base: str, h: dict, verbose: bool) -> list[dict]:
    r = client.get(f"{base}/api/careers/applications", headers=h, timeout=60.0)
    out = _response_json(r, verbose=verbose)
    if not out.get("status"):
        print(json.dumps(out, indent=2), file=sys.stderr)
        return []
    return (out.get("data") or {}).get("applications") or []


def _pick_candidate(
    apps: list[dict], want: str
) -> tuple[str | None, dict | None]:
    """want: shortlisted | rejected | any"""
    if want == "any" and apps:
        return apps[0]["id"], apps[0]
    for row in apps:
        st = (row.get("screening_status") or "").strip()
        if st == want:
            return row["id"], row
    return None, None


def main() -> int:
    _load_dotenv_backend()
    p = argparse.ArgumentParser(description="Test /api/communication/* with JWT")
    p.add_argument(
        "--base-url",
        default=os.getenv("HIREMANTRA_API_BASE", "http://127.0.0.1:8000").rstrip("/"),
    )
    p.add_argument("--token", default=os.getenv("HIREMANTRA_JWT", ""))
    p.add_argument("--candidate-id", default="", help="Target application UUID")
    p.add_argument(
        "--auto-pick",
        choices=("shortlisted", "rejected", "any"),
        default="",
        help="Pick first application with this screening_status (from GET applications)",
    )
    p.add_argument(
        "--only",
        choices=(
            "list-apps",
            "shortlist",
            "rejection",
            "schedule",
            "list-voice",
            "get-voice",
            "sync",
            "pipeline",
        ),
        required=True,
    )
    p.add_argument("--to-email", default="", help="shortlist / rejection / invite")
    p.add_argument("--extra-note", default="", help="shortlist / rejection body note")
    p.add_argument("--phone", default="", help="schedule: to_number override")
    p.add_argument(
        "--invite-email",
        action="store_true",
        help="schedule: send_interview_invite_email (needs --invite-to or candidate email)",
    )
    p.add_argument("--invite-to", default="")
    p.add_argument("--invite-extra-note", default="")
    p.add_argument("--session-id", default="", help="get-voice / sync")
    p.add_argument(
        "--voice-candidate-filter",
        default="",
        help="list-voice: query candidate_id",
    )
    p.add_argument("-v", "--verbose", action="store_true")

    args = p.parse_args()

    if not args.token:
        print("Set HIREMANTRA_JWT or --token", file=sys.stderr)
        return 1

    base = args.base_url
    h = _headers(args.token)

    long_timeout = httpx.Timeout(connect=30.0, read=720.0, write=30.0, pool=30.0)
    short_timeout = httpx.Timeout(60.0)

    def _resolve_candidate_id(client: httpx.Client) -> tuple[str | None, dict | None]:
        cid = (args.candidate_id or "").strip()
        if cid:
            return cid, None
        if not args.auto_pick:
            return None, None
        apps = _get_applications(client, base, h, args.verbose)
        pick, row = _pick_candidate(apps, args.auto_pick)
        if not pick:
            print(
                f"No application with screening_status={args.auto_pick!r}. "
                "Use seed_communication_demo or parser.",
                file=sys.stderr,
            )
            return None, None
        if args.verbose and row:
            print(f"Picked candidate {pick} status={row.get('screening_status')}", file=sys.stderr)
        return pick, row

    with httpx.Client(timeout=long_timeout) as client:
        if args.only == "list-apps":
            apps = _get_applications(client, base, h, args.verbose)
            print(json.dumps({"count": len(apps), "applications": apps}, indent=2))
            return 0

        need_cand = args.only in (
            "shortlist",
            "rejection",
            "schedule",
            "pipeline",
        )
        cand_id, _ = _resolve_candidate_id(client) if need_cand else ("", None)
        if need_cand:
            if not cand_id:
                cand_id = (args.candidate_id or "").strip()
            if not cand_id:
                print(
                    "Pass --candidate-id or --auto-pick shortlisted|rejected|any",
                    file=sys.stderr,
                )
                return 1

        if args.only == "shortlist":
            url = f"{base}/api/communication/candidates/{cand_id}/emails/shortlist"
            body: dict = {}
            if args.to_email.strip():
                body["to_email"] = args.to_email.strip()
            if args.extra_note.strip():
                body["extra_note"] = args.extra_note.strip()
            if args.verbose:
                print(f"POST {url}\n{json.dumps(body)}", file=sys.stderr)
            r = client.post(url, headers=h, json=body, timeout=short_timeout)
            out = _response_json(r, verbose=args.verbose)
            print(json.dumps(out, indent=2))
            if not out.get("status"):
                _hint_wrong_jd(out)
            return 0 if out.get("status") else 1

        if args.only == "rejection":
            url = f"{base}/api/communication/candidates/{cand_id}/emails/rejection"
            body = {}
            if args.to_email.strip():
                body["to_email"] = args.to_email.strip()
            if args.extra_note.strip():
                body["extra_note"] = args.extra_note.strip()
            if args.verbose:
                print(f"POST {url}\n{json.dumps(body)}", file=sys.stderr)
            r = client.post(url, headers=h, json=body, timeout=short_timeout)
            out = _response_json(r, verbose=args.verbose)
            print(json.dumps(out, indent=2))
            if not out.get("status"):
                _hint_wrong_jd(out)
            return 0 if out.get("status") else 1

        if args.only == "schedule":
            url = f"{base}/api/communication/candidates/{cand_id}/voice-interviews/schedule"
            body = {
                "send_interview_invite_email": bool(args.invite_email),
            }
            if args.phone.strip():
                body["to_number"] = args.phone.strip()
            if args.invite_to.strip():
                body["invite_to_email"] = args.invite_to.strip()
            if args.invite_extra_note.strip():
                body["invite_extra_note"] = args.invite_extra_note.strip()
            if args.verbose:
                print(f"POST {url}\n{json.dumps(body)}", file=sys.stderr)
            r = client.post(url, headers=h, json=body)
            out = _response_json(r, verbose=args.verbose)
            print(json.dumps(out, indent=2))
            if not out.get("status"):
                _hint_wrong_jd(out)
            return 0 if out.get("status") else 1

        if args.only == "pipeline":
            # 1 shortlist
            url1 = f"{base}/api/communication/candidates/{cand_id}/emails/shortlist"
            b1: dict = {}
            if args.to_email.strip():
                b1["to_email"] = args.to_email.strip()
            if args.extra_note.strip():
                b1["extra_note"] = args.extra_note.strip()
            if args.verbose:
                print(f"POST {url1}\n{json.dumps(b1)}", file=sys.stderr)
            r1 = client.post(url1, headers=h, json=b1, timeout=short_timeout)
            o1 = _response_json(r1, verbose=args.verbose)
            print("=== shortlist ===")
            print(json.dumps(o1, indent=2))
            if not o1.get("status"):
                return 1
            url2 = f"{base}/api/communication/candidates/{cand_id}/voice-interviews/schedule"
            b2 = {"send_interview_invite_email": bool(args.invite_email)}
            if args.phone.strip():
                b2["to_number"] = args.phone.strip()
            if args.invite_to.strip():
                b2["invite_to_email"] = args.invite_to.strip()
            if args.invite_extra_note.strip():
                b2["invite_extra_note"] = args.invite_extra_note.strip()
            if args.verbose:
                print(f"POST {url2}\n{json.dumps(b2)}", file=sys.stderr)
            r2 = client.post(url2, headers=h, json=b2)
            o2 = _response_json(r2, verbose=args.verbose)
            print("=== schedule voice ===")
            print(json.dumps(o2, indent=2))
            sid = (o2.get("data") or {}).get("session_id")
            if sid:
                print(
                    f"\nAfter call ends: python -m scripts.test_communication_api "
                    f"--only sync --session-id {sid}",
                    file=sys.stderr,
                )
            return 0 if o2.get("status") else 1

        if args.only == "list-voice":
            url = f"{base}/api/communication/voice-interviews"
            if args.voice_candidate_filter.strip():
                url = f"{url}?candidate_id={args.voice_candidate_filter.strip()}"
            r = client.get(url, headers=h, timeout=short_timeout)
            out = _response_json(r, verbose=args.verbose)
            print(json.dumps(out, indent=2))
            return 0 if out.get("status") else 1

        if args.only == "get-voice":
            sid = (args.session_id or "").strip()
            if not sid:
                print("--session-id required", file=sys.stderr)
                return 1
            url = f"{base}/api/communication/voice-interviews/{sid}"
            r = client.get(url, headers=h, timeout=short_timeout)
            out = _response_json(r, verbose=args.verbose)
            print(json.dumps(out, indent=2))
            return 0 if out.get("status") else 1

        if args.only == "sync":
            sid = (args.session_id or "").strip()
            if not sid:
                print("--session-id required", file=sys.stderr)
                return 1
            url = f"{base}/api/communication/voice-interviews/{sid}/sync"
            if args.verbose:
                print(f"POST {url}", file=sys.stderr)
            r = client.post(url, headers=h, json={}, timeout=long_timeout)
            out = _response_json(r, verbose=args.verbose)
            print(json.dumps(out, indent=2))
            return 0 if out.get("status") else 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
