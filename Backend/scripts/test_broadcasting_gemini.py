"""
Exercise the Broadcasting Gemini APIs (post structure + media).

  POST /api/broadcasting/jd/{jd_id}/broadcast-post-structure
  POST /api/broadcasting/jd/{jd_id}/broadcast-media

Environment
-----------
  HIREMANTRA_JWT         Required. Access token (no ``Bearer`` prefix).
  HIREMANTRA_API_BASE    Optional. Default ``http://127.0.0.1:8000``.

Examples
--------
  cd Backend
  export HIREMANTRA_JWT='<token>'
  export GOOGLE_API_KEY='<gemini key>'   # server .env — script only hits HTTP

  # Both endpoints (structure first, then image — fast default)
  python -m scripts.test_broadcasting_gemini --jd-id <uuid> --only both

  # Post structure only (LinkedIn + Unstop JSON)
  python -m scripts.test_broadcasting_gemini --jd-id <uuid> --only structure

  # Image only
  python -m scripts.test_broadcasting_gemini --jd-id <uuid> --only media --content-type image

  # Video (slow; long HTTP request — bump client/proxy timeouts)
  python -m scripts.test_broadcasting_gemini --jd-id <uuid> --only media \\
    --content-type video --aspect-ratio 9:16 --max-wait-seconds 900

  # Image then video in one run (image first, then Veo — can take many minutes)
  python -m scripts.test_broadcasting_gemini --jd-id 7bccffd6-5180-4ed2-b2af-5bb2256edd61 \\
    --only image-and-video --aspect-ratio 9:16 --max-wait-seconds 900

  # Media prompt uses creative brief from structure step
  python -m scripts.test_broadcasting_gemini --jd-id <uuid> --only media \\
    --content-type image --use-structure-brief

  # List JDs for your org (fixes "does not belong to your organization")
  python -m scripts.test_broadcasting_gemini --list-jds
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


def _hint_wrong_jd(out: dict, base: str) -> None:
    msg = str(out.get("message") or "")
    if "does not belong to your organization" in msg or msg == "Forbidden":
        print(
            f"\nTip: that jd_id is not under this JWT's org. List yours:\n"
            f"  python -m scripts.test_broadcasting_gemini --list-jds\n"
            f"Or: GET {base}/api/broadcasting/job-descriptions",
            file=sys.stderr,
        )


def _headers(token: str) -> dict[str, str]:
    t = token.strip()
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


def main() -> int:
    _load_dotenv_backend()
    p = argparse.ArgumentParser(
        description="Test broadcast-post-structure and broadcast-media APIs",
    )
    p.add_argument(
        "--base-url",
        default=os.getenv("HIREMANTRA_API_BASE", "http://127.0.0.1:8000").rstrip("/"),
    )
    p.add_argument(
        "--token",
        default=os.getenv("HIREMANTRA_JWT", ""),
        help="Or set HIREMANTRA_JWT",
    )
    p.add_argument(
        "--jd-id",
        default="",
        help="Job description UUID (must belong to your org). Required unless --list-jds.",
    )
    p.add_argument(
        "--list-jds",
        action="store_true",
        help="GET /api/broadcasting/job-descriptions and print jd_id values for your token",
    )
    p.add_argument(
        "--only",
        choices=("structure", "media", "both", "image-and-video"),
        default="both",
        help=(
            "structure | media | both | image-and-video "
            "(both = structure then one media via --content-type; "
            "image-and-video = image + video, no structure step)"
        ),
    )
    p.add_argument(
        "--content-type",
        choices=("image", "video"),
        default="image",
        help="For media / both (default image to avoid long Veo runs)",
    )
    p.add_argument(
        "--aspect-ratio",
        default="9:16",
        help="Video only (e.g. 9:16, 16:9, 1:1)",
    )
    p.add_argument("--extra-context", default="", help="Extra line for media prompt")
    p.add_argument(
        "--use-structure-brief",
        action="store_true",
        help="Media: call structure first on server for creative_brief_for_media",
    )
    p.add_argument(
        "--max-wait-seconds",
        type=float,
        default=600.0,
        help="Video: server poll budget",
    )
    p.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=10.0,
        help="Video: poll interval sent to API",
    )
    p.add_argument(
        "--channels",
        nargs="*",
        default=["linkedin", "unstop"],
        help="Channels for post-structure body",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    if not args.token:
        print(
            "Set HIREMANTRA_JWT or pass --token (access_token from login/register).",
            file=sys.stderr,
        )
        return 1

    base = args.base_url
    h = _headers(args.token)

    if args.list_jds:
        url = f"{base}/api/broadcasting/job-descriptions"
        with httpx.Client(timeout=60.0) as client:
            r = client.get(url, headers=h)
            try:
                out = r.json()
            except Exception:
                print(r.text, file=sys.stderr)
                return 1
        print("=== job-descriptions (your org) ===")
        print(json.dumps(out, indent=2))
        if out.get("status"):
            rows = (out.get("data") or {}).get("job_descriptions") or []
            if rows:
                print("\njd_id values:", file=sys.stderr)
                for row in rows:
                    rid = row.get("jd_id") or row.get("id")
                    role = (row.get("role") or "")[:60]
                    print(f"  {rid}  —  {role!r}", file=sys.stderr)
            else:
                print(
                    "\nNo job descriptions yet. POST /api/broadcasting/generate-jd first.",
                    file=sys.stderr,
                )
        return 0 if out.get("status") else 1

    jd_id = (args.jd_id or "").strip()
    if not jd_id:
        print(
            "Pass --jd-id <uuid> or use --list-jds to see your org's job descriptions.",
            file=sys.stderr,
        )
        return 1

    run_structure = args.only in ("structure", "both")
    run_media = args.only in ("media", "both", "image-and-video")
    media_kinds: list[str]
    if args.only == "image-and-video":
        media_kinds = ["image", "video"]
    elif run_media:
        media_kinds = [args.content_type]
    else:
        media_kinds = []

    needs_long_read = run_media and (
        args.content_type == "video" or args.only == "image-and-video"
    )
    timeout = httpx.Timeout(
        connect=30.0,
        read=max(120.0, args.max_wait_seconds + 120.0) if needs_long_read else 120.0,
        write=30.0,
        pool=30.0,
    )

    def _post_media(client: httpx.Client, content_type: str) -> int:
        url = f"{base}/api/broadcasting/jd/{jd_id}/broadcast-media"
        body: dict = {
            "content_type": content_type,
            "aspect_ratio": args.aspect_ratio,
            "use_structure_creative_brief": bool(args.use_structure_brief),
            "max_wait_seconds": args.max_wait_seconds,
            "poll_interval_seconds": args.poll_interval_seconds,
        }
        if args.extra_context.strip():
            body["extra_context"] = args.extra_context.strip()
        if args.verbose:
            print(f"POST {url}\n{json.dumps(body)}", file=sys.stderr)
        r = client.post(url, headers=h, json=body)
        try:
            out = r.json()
        except Exception:
            print(r.text, file=sys.stderr)
            return 1
        print(f"=== broadcast-media ({content_type}) ===")
        print(json.dumps(out, indent=2))
        if not out.get("status"):
            _hint_wrong_jd(out, base)
            return 1
        rel = (out.get("data") or {}).get("relative_path")
        if rel:
            root = Path(__file__).resolve().parent.parent
            abs_path = root / rel
            print(f"\nFile on server disk (if local): {abs_path}", file=sys.stderr)
        return 0

    with httpx.Client(timeout=timeout) as client:
        if run_structure:
            url = f"{base}/api/broadcasting/jd/{jd_id}/broadcast-post-structure"
            body = {"channels": list(args.channels)}
            if args.verbose:
                print(f"POST {url}\n{json.dumps(body)}", file=sys.stderr)
            r = client.post(url, headers=h, json=body)
            try:
                out = r.json()
            except Exception:
                print(r.text, file=sys.stderr)
                return 1
            print("=== broadcast-post-structure ===")
            print(json.dumps(out, indent=2))
            if not out.get("status"):
                _hint_wrong_jd(out, base)
                return 1

        for kind in media_kinds:
            code = _post_media(client, kind)
            if code != 0:
                return code

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
