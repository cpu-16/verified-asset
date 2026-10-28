"""Report payloads: what was checked, bound to exact photo hashes, with a digest.

The digest is SHA-256 over canonical JSON. It proves the report was not
changed after issue; it does NOT prove when a photo was taken or that the
server is honest.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone

from .adjudicate import Status, Verdict
from .catalog import RULES_VERSION, Claim

REPORT_DAYS = 30
LIMITS = ("Checked only as photographed. A report is not proof of ownership, authenticity, "
          "function, comprehensive condition or seller trustworthiness. Edits made outside "
          "Verified Asset (for example on Marketplace) cannot be detected.")


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(payload: dict) -> str:
    return hashlib.sha256(canonical(payload)).hexdigest()


def build_payload(*, listing_id: str, version: int, title: str, description: str,
                  claims: list[Claim], verdicts: list[Verdict], photos: dict[str, str],
                  check_id: str, observer: str, issued_at: datetime,
                  fresh_photo_ids: list[str] = (), capture_code: str = "") -> dict:
    """`photos` maps slot -> sha256 of the checked photo. `capture_code` only when it was seen."""
    by_id = {v.claim_id: v for v in verdicts}
    return {
        "listing_id": listing_id,
        "listing_version": version,
        "title": title,
        "description_sha256": hashlib.sha256(description.encode()).hexdigest(),
        "claims": [{**c.to_dict(), "verdict": by_id[c.id].to_dict()} for c in claims],
        "photos": dict(sorted(photos.items())),
        "fresh_capture_photo_ids": list(fresh_photo_ids),
        "capture_code": capture_code if fresh_photo_ids else "",
        "check_id": check_id,
        "observer": observer,
        "rules_version": RULES_VERSION,
        "issued_at": issued_at.isoformat(timespec="seconds"),
        "expires_at": (issued_at + timedelta(days=REPORT_DAYS)).isoformat(timespec="seconds"),
        "limits": LIMITS,
    }


def effective_state(state: str, expires_at: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    if state == "active" and datetime.fromisoformat(expires_at) <= now:
        return "expired"
    return state


def summary(payload: dict) -> dict:
    counts = {str(s): 0 for s in Status}
    for c in payload["claims"]:
        counts[c["verdict"]["status"]] += 1
    return counts
