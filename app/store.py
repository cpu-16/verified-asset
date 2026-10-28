"""SQLite persistence. Issued reports and listing versions are never mutated,
only their state changes; every transition is written to an append-only event log.

ponytail: one SQLite file in WAL mode and blobs on local disk; move to Postgres
and object storage when one box is not enough.
"""
from contextlib import closing, contextmanager
import fcntl
import hashlib
import json
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .catalog import Claim

CODE_ALPHABET = "ACDEFGHJKMNPQRTUVWXY34679"  # no look-alikes (0/O, 1/I/L, 2/Z, 5/S, 8/B)

SCHEMA = """
CREATE TABLE IF NOT EXISTS model_cache (
  key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS paid_checks (
  listing_id TEXT NOT NULL, day TEXT NOT NULL, count INTEGER NOT NULL,
  PRIMARY KEY (listing_id, day));
CREATE TABLE IF NOT EXISTS listings (
  id TEXT PRIMARY KEY, seller_key TEXT NOT NULL, capture_code TEXT NOT NULL, source_url TEXT,
  sample INTEGER DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS versions (
  id INTEGER PRIMARY KEY, listing_id TEXT NOT NULL REFERENCES listings(id), version INTEGER NOT NULL,
  title TEXT NOT NULL, description TEXT NOT NULL, claims TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE (listing_id, version));
CREATE TABLE IF NOT EXISTS photos (
  id TEXT PRIMARY KEY, listing_id TEXT NOT NULL REFERENCES listings(id), slot TEXT NOT NULL,
  sha256 TEXT NOT NULL, received_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS checks (
  id TEXT PRIMARY KEY, version_id INTEGER NOT NULL REFERENCES versions(id), photos TEXT NOT NULL,
  observer TEXT NOT NULL, ok INTEGER NOT NULL, error TEXT, observations TEXT, verdicts TEXT,
  latency_ms INTEGER, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reports (
  token TEXT PRIMARY KEY, listing_id TEXT NOT NULL REFERENCES listings(id),
  version_id INTEGER NOT NULL REFERENCES versions(id), check_id TEXT NOT NULL REFERENCES checks(id),
  payload TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'active',
  issued_at TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY, listing_id TEXT, kind TEXT NOT NULL, detail TEXT, at TEXT NOT NULL);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.blobs = data_dir / "blobs"
        self.blobs.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    @property
    def db(self) -> sqlite3.Connection:
        """One connection per thread: the server's worker threads must never share one."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.data_dir / "verified-asset.db", timeout=10,
                                   isolation_level=None)  # autocommit; explicit BEGIN for multi-step writes
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    def cached(self, key: list, call):
        """Persist successful results; concurrent misses share one call."""
        digest = hashlib.sha256(json.dumps(key).encode()).hexdigest()
        with file_lock(self.data_dir / "cache-locks" / digest[:2]):
            with closing(sqlite3.connect(self.data_dir / "verified-asset.db",
                                         isolation_level=None)) as db:
                row = db.execute("SELECT value FROM model_cache WHERE key=?", (digest,)).fetchone()
                if row is not None:
                    return json.loads(row[0])
                value = call()
                db.execute("INSERT INTO model_cache VALUES (?,?)", (digest, json.dumps(value)))
                return value

    def claim_paid_check(self, listing_id: str, day: str, limit: int) -> bool:
        with closing(sqlite3.connect(self.data_dir / "verified-asset.db",
                                     isolation_level=None)) as db:
            return db.execute(
                "INSERT INTO paid_checks SELECT ?,?,1 WHERE ? > 0 "
                "ON CONFLICT(listing_id,day) DO UPDATE SET count=count+1 WHERE count < ? "
                "RETURNING count", (listing_id, day, limit, limit)).fetchone() is not None

    def log(self, listing_id: str | None, kind: str, **detail):
        self.db.execute("INSERT INTO events (listing_id, kind, detail, at) VALUES (?,?,?,?)",
                        (listing_id, kind, json.dumps(detail), now()))

    # listings and versions -------------------------------------------------
    def create_listing(self, title: str, description: str, claims: list[Claim],
                       source_url: str = "", sample: bool = False, capture_code: str = "") -> tuple[str, str]:
        listing_id, key = secrets.token_urlsafe(9), secrets.token_urlsafe(18)
        code = capture_code or "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))
        self.db.execute("BEGIN")
        self.db.execute("INSERT INTO listings VALUES (?,?,?,?,?,?)",
                        (listing_id, key, code, source_url, int(sample), now()))
        self._add_version(listing_id, 1, title, description, claims)
        self.log(listing_id, "listing_created", source_url=source_url)
        self.db.execute("COMMIT")
        return listing_id, key

    def _add_version(self, listing_id, version, title, description, claims):
        self.db.execute("INSERT INTO versions (listing_id, version, title, description, claims, created_at)"
                        " VALUES (?,?,?,?,?,?)",
                        (listing_id, version, title, description,
                         json.dumps([c.to_dict() for c in claims]), now()))

    def edit_listing(self, listing_id: str, title: str, description: str, claims: list[Claim]) -> int:
        """New version; every active report of the listing stops vouching for it."""
        self.db.execute("BEGIN")
        version = self.latest_version(listing_id)["version"] + 1
        self._add_version(listing_id, version, title, description, claims)
        tokens = [r["token"] for r in self.db.execute(
            "SELECT token FROM reports WHERE listing_id=? AND state='active'", (listing_id,))]
        self.db.execute("UPDATE reports SET state='invalidated' WHERE listing_id=? AND state='active'",
                        (listing_id,))
        self.log(listing_id, "listing_edited", version=version, invalidated=tokens)
        self.db.execute("COMMIT")
        return version

    def listing(self, listing_id: str):
        return self.db.execute("SELECT * FROM listings WHERE id=?", (listing_id,)).fetchone()

    def latest_version(self, listing_id: str):
        return self.db.execute("SELECT * FROM versions WHERE listing_id=? ORDER BY version DESC LIMIT 1",
                               (listing_id,)).fetchone()

    @staticmethod
    def claims_of(version) -> list[Claim]:
        return [Claim.from_dict(d) for d in json.loads(version["claims"])]

    def video_draft(self, listing_id: str, version: int) -> dict | None:
        """Muse Spark's latest draft from the seller's video, until the seller saves a version over it."""
        row = self.db.execute("SELECT detail FROM events WHERE listing_id=? AND kind='video_draft'"
                              " ORDER BY id DESC LIMIT 1", (listing_id,)).fetchone()
        draft = json.loads(row["detail"]) if row else None
        return draft if draft and draft["version"] == version else None

    # photos ----------------------------------------------------------------
    def add_photo(self, listing_id: str, slot: str, data: bytes) -> str:
        sha = hashlib.sha256(data).hexdigest()
        path = self.blobs / sha
        if not path.exists():
            path.write_bytes(data)
        photo_id = secrets.token_urlsafe(9)
        self.db.execute("INSERT INTO photos VALUES (?,?,?,?,?)", (photo_id, listing_id, slot, sha, now()))
        self.log(listing_id, "photo_added", slot=slot, sha256=sha)
        return photo_id

    def current_photos(self, listing_id: str) -> dict[str, sqlite3.Row]:
        """Latest photo per slot (a retake replaces the slot, older photos stay on record)."""
        rows = self.db.execute("SELECT * FROM photos WHERE listing_id=? ORDER BY received_at, rowid",
                               (listing_id,)).fetchall()
        return {r["slot"]: r for r in rows}

    def photo(self, photo_id: str):
        return self.db.execute("SELECT * FROM photos WHERE id=?", (photo_id,)).fetchone()

    def photo_bytes(self, sha256: str) -> bytes:
        return (self.blobs / sha256).read_bytes()

    # checks and reports ------------------------------------------------------
    def save_check(self, version_id: int, photo_ids: dict[str, str], observer: str, ok: bool,
                   error: str, observations: list[dict], verdicts: list[dict], latency_ms: int) -> str:
        check_id = secrets.token_urlsafe(9)
        self.db.execute("INSERT INTO checks VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (check_id, version_id, json.dumps(photo_ids), observer, int(ok), error,
                         json.dumps(observations), json.dumps(verdicts), latency_ms, now()))
        return check_id

    def latest_check(self, version_id: int):
        return self.db.execute("SELECT * FROM checks WHERE version_id=? ORDER BY created_at DESC, rowid DESC"
                               " LIMIT 1", (version_id,)).fetchone()

    def issue_report(self, listing_id: str, version_id: int, check_id: str, payload: dict,
                     digest: str) -> str:
        token = secrets.token_urlsafe(16)
        self.db.execute("INSERT INTO reports VALUES (?,?,?,?,?,?,?,?,?)",
                        (token, listing_id, version_id, check_id, json.dumps(payload), digest,
                         "active", payload["issued_at"], payload["expires_at"]))
        self.log(listing_id, "report_issued", token=token, digest=digest)
        return token

    def report(self, token: str):
        return self.db.execute("SELECT * FROM reports WHERE token=?", (token,)).fetchone()

    def active_reports(self, listing_id: str):
        return self.db.execute("SELECT * FROM reports WHERE listing_id=? AND state='active'"
                               " ORDER BY issued_at DESC", (listing_id,)).fetchall()

    def revoke(self, token: str):
        row = self.report(token)
        self.db.execute("UPDATE reports SET state='revoked' WHERE token=? AND state='active'", (token,))
        self.log(row["listing_id"], "report_revoked", token=token)
