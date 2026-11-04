"""Web app: seller flow (claims -> guided photos -> check -> report) and public reports.

Sellers have no accounts: the listing URL carries a secret `k` (capability link).
"""
import base64
import dataclasses
import binascii
import hashlib
import io
import json
import os
import re
import time
from urllib.parse import urlencode
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import reports
from .marketplace import build_post
from .adjudicate import COLOR_FAMILIES, adjudicate, capture_code_seen, color_family, scan, shot_needs
from .catalog import CATEGORIES, SLOT_PROMPTS, SUBJECT, Claim, ClaimType, Slot, count_subjects, required_slots
from .observation import PhotoObservation
from .store import Store

BASE = Path(__file__).parent
SAMPLE = BASE.parent / "eval"
DATA = Path(os.environ.get("DATA_DIR", "data"))
MAX_PHOTO_BYTES = 12_000_000
MAX_SCAN_PHOTOS, MAX_SCAN_BYTES = 6, 5_000_000
CLAIM_ROWS = 12
MAX_FILM_FRAMES = 12
MAX_FRAME_BYTES = 2_000_000  # the phone sends JPEGs of at most 1280 px

app = FastAPI(title="Verified Asset")
app.add_middleware(CORSMiddleware, allow_origins=["https://www.facebook.com"],
                   allow_methods=["GET"])  # the browser extension reads /api/r/* from Marketplace
templates = Jinja2Templates(directory=BASE / "templates")
templates.env.globals["categories"] = CATEGORIES
templates.env.filters["day"] = lambda iso: datetime.fromisoformat(iso).strftime("%-d %b %Y")
templates.env.filters["timestamp"] = lambda iso: datetime.fromisoformat(iso).astimezone(timezone.utc).strftime("%-d %b %Y, %H:%M:%S UTC")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
# the CDN caches static files for days: a content hash in the URL makes a new deploy show up at once
templates.env.globals["v"] = hashlib.sha256(b"".join(
    f.read_bytes() for f in sorted((BASE / "static").iterdir()))).hexdigest()[:8]
store = Store(DATA)


def get_observer():
    """Live observer from the environment (Spark, or local Glimmer). Tests replace `app.state.observer`."""
    if getattr(app.state, "observer", None) is None:
        from .observe import observer_from_env
        app.state.observer = observer_from_env()
    return app.state.observer


def get_sam():
    if not hasattr(app.state, "sam"):
        from .observe import shared_guard
        from .segment import SamCounter
        key = os.environ.get("MODEL_API_KEY")
        app.state.sam = SamCounter(key, guard=shared_guard()) if key else None
    return app.state.sam


def seller_listing(listing_id: str, k: str):
    row = store.listing(listing_id)
    if row is None or k != row["seller_key"]:
        raise HTTPException(404)
    return row


NUMBER_WORDS = {w: n for n, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve".split())}
COLOR_WORDS = {w for members in COLOR_FAMILIES.values() for w in members}


def sentence_mismatch(ctype: ClaimType, text: str, value: str) -> str:
    """Why the sentence buyers will read disagrees with the value the rules check, or ''."""
    words = re.findall(r"[a-z]+|\d+", text.lower())
    if ctype == ClaimType.PIECE_COUNT:
        said = {int(w) if w.isdigit() else NUMBER_WORDS[w] for w in words if w.isdigit() or w in NUMBER_WORDS}
        if said and int(value) not in said:
            return f"says {', '.join(map(str, sorted(said)))} but the number to check is {value}"
    if ctype == ClaimType.COLOR:
        said = {color_family(w) for w in words if w in COLOR_WORDS}
        if said and color_family(value) not in said:
            return f"names {', '.join(sorted(said))} but the colour to check is {value}"
    return ""


def parse_claims(form) -> list[Claim]:
    claims = []
    for i in range(CLAIM_ROWS):
        text = (form.get(f"text{i}") or "").strip()
        if not text:
            continue
        ctype = ClaimType(form.get(f"type{i}") or ClaimType.UNCHECKABLE)
        subject = " ".join((form.get(f"subject{i}") or "").lower().split())
        if ctype in (ClaimType.PIECE_COUNT, ClaimType.PART_NO_DAMAGE) and not SUBJECT.fullmatch(subject):
            raise HTTPException(422, "What to count must be one to three plain words, e.g. 'chair'.")
        value = (form.get(f"value{i}") or "").strip()[:40]
        if ctype == ClaimType.PIECE_COUNT and not (value.isdigit() and 0 < int(value) < 100):
            raise HTTPException(422, f"Claim {i + 1}: enter the number of pieces as digits, e.g. 4.")
        if ctype == ClaimType.PART_NO_DAMAGE:
            text = f"{subject.capitalize()} has no visible damage"
        if ctype == ClaimType.LABEL_TEXT:
            if not value:
                raise HTTPException(422, "Enter the text to read on the label.")
            text = f"Label reads: {value}"
        if why := sentence_mismatch(ctype, text, value):
            raise HTTPException(422, f"Claim {i + 1} {why}. Make them match: buyers read your sentence.")
        claims.append(Claim(id=f"c{i + 1}", type=ctype, text=text[:200],
                            subject=subject[:40] if ctype in (ClaimType.PIECE_COUNT, ClaimType.PART_NO_DAMAGE) else "", value=value,
                            by="video" if form.get(f"by{i}") == "video" else ""))
    if not claims:
        raise HTTPException(422, "Add at least one claim.")
    return claims


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "home.html", {})


@app.get("/new", response_class=HTMLResponse)
def new_form(request: Request, title: str = "", description: str = "", source: str = ""):
    return templates.TemplateResponse(request, "new.html", {
        "title": title[:200], "description": description[:2000], "source": source[:500],
        "rows": range(CLAIM_ROWS), "types": list(ClaimType)})


@app.post("/new")
async def create(request: Request):
    form = await request.form()
    claims = parse_claims(form)
    listing_id, key = store.create_listing(
        (form.get("title") or "Untitled item")[:200], (form.get("description") or "")[:2000],
        claims, source_url=(form.get("source") or "")[:500])
    return RedirectResponse(f"/l/{listing_id}?k={key}", status_code=303)


SUGGESTIONS_PER_DAY = 20
FILMS_PER_DAY = 10
# ponytail: per address and in memory (a restart resets it); the daily spend cap is the real backstop
_per_address: dict[tuple[str, str, str], int] = {}


def over_daily_limit(request: Request, kind: str, limit: int) -> bool:
    seen = (time.strftime("%Y-%m-%d"), kind, request.client.host if request.client else "")
    _per_address[seen] = _per_address.get(seen, 0) + 1
    return _per_address[seen] > limit


def suggested_claims(request: Request, title: str, description: str) -> tuple[list[Claim], str]:
    """Muse Spark reads only the seller's words and proposes claim rows; it never sees the photos."""
    if not (title.strip() or description.strip()):
        return [], "Write a title or a description first."
    if over_daily_limit(request, "suggest", SUGGESTIONS_PER_DAY):
        return [], "That's the limit of suggestions for today. Fill in the claims yourself."
    try:
        observer = get_observer()
    except ValueError:
        return [], "Suggestions need the model, which isn't set up on this server. Fill in the claims yourself."
    try:
        claims = scan_claims(observer.extract_claims(title[:200], description[:2000]))[:CLAIM_ROWS]
    except Exception as exc:  # network, spending cap or an invalid answer
        return [], f"Muse Spark didn't answer ({type(exc).__name__}). Try again, or fill in the claims yourself."
    if not claims:
        return [], "Your description doesn't say anything a photo could check. Add the claims yourself."
    return claims, ""


@app.post("/new/suggest", response_class=HTMLResponse)
def suggest(request: Request, title: str = Form(""), description: str = Form(""), source: str = Form("")):
    claims, error = suggested_claims(request, title, description)
    return templates.TemplateResponse(request, "new.html", {
        "title": title[:200], "description": description[:2000], "source": source[:500],
        "rows": range(CLAIM_ROWS), "types": list(ClaimType), "claims": claims, "suggested": bool(claims),
        "error": error})


@app.post("/film")
def film():
    """Film it instead: an empty listing whose page asks for one video. Muse Spark drafts the rest."""
    listing_id, key = store.create_listing("Untitled item", "", [])
    return RedirectResponse(f"/l/{listing_id}?k={key}#film", status_code=303)


@app.post("/l/{listing_id}/video")
def video(request: Request, listing_id: str, k: str, frames: list[UploadFile] = File(...),
          times: str = Form("")):
    """Frames the seller's phone took from their video (the video itself never leaves the phone)."""
    from .observe import CheckLimitExceeded, listing_check, prepare_image
    row = seller_listing(listing_id, k)
    if row["sample"]:
        raise HTTPException(409, "The sample's photos can't be changed. Start your own report to film an item.")
    if not 1 <= len(frames) <= MAX_FILM_FRAMES:
        raise HTTPException(422, f"Send between 1 and {MAX_FILM_FRAMES} frames.")
    data = []
    for f in frames:
        raw = f.file.read(MAX_FRAME_BYTES + 1)
        if not raw or len(raw) > MAX_FRAME_BYTES:
            raise HTTPException(413, "A frame is missing or larger than 2 MB.")
        try:
            data.append(prepare_image(raw)[0])  # strips EXIF/GPS like any photo
        except Exception:
            raise HTTPException(415, "A frame is not a readable image.")
    try:
        observer = get_observer()
    except ValueError:
        raise HTTPException(503, "Filming needs the model, which isn't set up on this server yet. "
                                 "Take photos instead.")
    if over_daily_limit(request, "film", FILMS_PER_DAY):
        raise HTTPException(429, "That's the limit of videos for today. Take photos instead.")
    try:
        with listing_check(store, listing_id):
            draft = observer.draft_from_frames(data)
    except CheckLimitExceeded as exc:
        raise HTTPException(429, str(exc))
    except Exception as exc:  # network, spending cap or an invalid answer
        raise HTTPException(503, f"Muse Spark couldn't draft from the video ({type(exc).__name__}). "
                                 "Try again, or take photos instead.")
    picks = {slot: draft[slot] for slot in Slot if 0 <= draft[slot] < len(data)}
    for slot, i in picks.items():
        store.add_photo(listing_id, slot, data[i])
    # only counts and colours, and only sentences that name the value they check: a drafted "no damage"
    # would be checked on frames the same model picked, so that claim stays the seller's to make
    claims = [dataclasses.replace(c, by="video") for c in scan_claims(draft["claims"])
              if c.type in (ClaimType.PIECE_COUNT, ClaimType.COLOR) and not sentence_mismatch(c.type, c.text, c.value)]
    claims = claims[:CLAIM_ROWS]
    store.log(listing_id, "video_draft", version=store.latest_version(listing_id)["version"],
              title=draft["title"].strip()[:200] or "Untitled item", description=draft["description"].strip()[:2000],
              claims=[c.to_dict() for c in claims], frames=picks, times=times[:200], observer=observer.name)
    return RedirectResponse(f"/l/{listing_id}?k={k}#draft", status_code=303)


@app.post("/sample")
def create_sample():
    claims = [Claim("c1", ClaimType.PIECE_COUNT, "Set of 4 chairs", "chair", "4"),
              Claim("c2", ClaimType.COLOR, "White finish", value="white"),
              Claim("c3", ClaimType.NO_VISIBLE_DAMAGE, "No scratches or stains"),
              Claim("c4", ClaimType.UNCHECKABLE, "Solid oak, not veneer")]
    listing_id, key = store.create_listing(
        "White dining table with 4 chairs", "Barely used. Pick up only.", claims,
        sample=True, capture_code="6YA7")
    for slot in (Slot.FRONT, Slot.SIDE):  # no close-up yet: Spark's recorded plan asks for it
        store.add_photo(listing_id, str(slot), (SAMPLE / "photos" / f"dining-{slot}.jpg").read_bytes())
    return RedirectResponse(f"/l/{listing_id}?k={key}", status_code=303)


@app.post("/l/{listing_id}/sample-detail")
def sample_detail(listing_id: str, k: str):
    """The sample's close-up, the one photo a sample can add: what Muse Spark's recorded plan asks for."""
    row = seller_listing(listing_id, k)
    if not row["sample"] or "detail" in store.current_photos(listing_id):
        raise HTTPException(409, "Only a sample without its close-up can add it.")
    store.add_photo(listing_id, "detail", (SAMPLE / "photos" / "dining-detail.jpg").read_bytes())
    return RedirectResponse(f"/l/{listing_id}?k={k}#check", status_code=303)


@app.get("/l/{listing_id}", response_class=HTMLResponse)
def listing_page(request: Request, listing_id: str, k: str):
    row = seller_listing(listing_id, k)
    version = store.latest_version(listing_id)
    claims = store.claims_of(version)
    photos = store.current_photos(listing_id)
    check = store.latest_check(version["id"])
    verdicts = {v["claim_id"]: v for v in json.loads(check["verdicts"])} if check and check["ok"] else {}
    stale = bool(check) and json.loads(check["photos"]) != {s: p["id"] for s, p in photos.items()}
    marks = sam_marks(check, photos) if check and check["ok"] and not stale else {}
    draft = None if row["sample"] else store.video_draft(listing_id, version["version"])
    if draft:
        draft["claims"] = [Claim.from_dict(d) for d in draft["claims"]]
    active = [r for r in store.active_reports(listing_id)
              if reports.effective_state(r["state"], r["expires_at"]) == "active"]
    current = bool(check) and any(r["check_id"] == check["id"] for r in active)  # a report of the latest check
    posts = {r["token"]: build_post(version, json.loads(r["payload"]),
                                  str(request.url_for("report_page", token=r["token"]))) for r in active}
    return templates.TemplateResponse(request, "listing.html", {
        "draft": draft,
        "listing": row, "k": k, "version": version, "claims": claims, "photos": photos,
        "slots": [(s, SLOT_PROMPTS[s]) for s in required_slots(claims)] or [(Slot.FRONT, SLOT_PROMPTS[Slot.FRONT])],
        "check": check, "verdicts": verdicts, "stale": stale, "marks": marks,
        "observations_json": json.dumps(json.loads(check["observations"] or "[]"), indent=2, ensure_ascii=False)
        if check and check["ok"] else "",
        "reports": active, "current": current, "posts": posts, "types": list(ClaimType),
        "rows": range(CLAIM_ROWS)})


def sam_marks(check, photos) -> dict[str, list[tuple[str, str]]]:
    """SAM's boxes around observed damage, as CSS percentages over the seller's photo. Never on the public report."""
    from PIL import Image
    marks = {}
    for o in json.loads(check["observations"]):
        boxes = [(d["kind"], d["box"]) for d in o["defects"] if d.get("box")]
        if boxes and o["slot"] in photos:
            with Image.open(io.BytesIO(store.photo_bytes(photos[o["slot"]]["sha256"]))) as im:
                w, h = im.size  # boxes are in the stored (already prepared) photo's pixels
            marks[o["slot"]] = [(kind, f"left:{x0 / w:.2%};top:{y0 / h:.2%};"
                                       f"width:{(x1 - x0) / w:.2%};height:{(y1 - y0) / h:.2%}")
                                for kind, (x0, y0, x1, y1) in boxes]
    return marks


@app.get("/l/{listing_id}/photo/{photo_id}")
def photo(listing_id: str, photo_id: str, k: str):
    seller_listing(listing_id, k)  # raw photos are only ever shown to the seller
    row = store.photo(photo_id)
    if row is None or row["listing_id"] != listing_id:
        raise HTTPException(404)
    return Response(store.photo_bytes(row["sha256"]), media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=3600"})


@app.post("/l/{listing_id}/photo")
async def upload(listing_id: str, k: str, slot: Slot = Form(...), file: UploadFile = File(...), back: str = ""):
    row = seller_listing(listing_id, k)
    if row["sample"]:
        raise HTTPException(409, "The sample replays recorded observations of these photos, so they can't be changed. "
                            "Start your own report to use your photos.")
    data = await file.read(MAX_PHOTO_BYTES + 1)
    if not data or len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "Photo missing or larger than 12 MB.")
    from .observe import prepare_image  # strips EXIF/GPS before anything is stored
    try:
        data, _ = prepare_image(data)
    except Exception:
        raise HTTPException(415, "That file is not a readable image.")
    store.add_photo(listing_id, str(slot), data)
    return RedirectResponse(f"/l/{listing_id}?k={k}#{'check' if back == 'check' else 'photos'}", status_code=303)


@app.post("/l/{listing_id}/check")
def run_check(listing_id: str, k: str):
    check_listing(listing_id, k)
    return RedirectResponse(f"/l/{listing_id}?k={k}#check", status_code=303)


def check_listing(listing_id: str, k: str):
    from .observe import CheckLimitExceeded, Photo, ReplayObserver, listing_check
    from .observation import CheckResult
    row = seller_listing(listing_id, k)
    version = store.latest_version(listing_id)
    claims = store.claims_of(version)
    current = store.current_photos(listing_id)
    photos = [Photo(id=p["id"], slot=s, data=store.photo_bytes(p["sha256"])) for s, p in current.items()]
    try:
        observer = ReplayObserver(SAMPLE / "recordings" / "muse-spark-1.3.json") if row["sample"] else get_observer()
    except ValueError:  # no MODEL_API_KEY / LOCAL_MODEL_URL on this server
        store.save_check(version["id"], {s: p["id"] for s, p in current.items()}, "none", False,
                         "no model is configured on this server yet", [], [], 0)
        return None
    started = time.monotonic()
    observations, verdicts = [], []
    with listing_check(store, listing_id):
        if row["sample"] and any(subject != "chair" for subject in count_subjects(claims)):
            result = CheckResult(observer.name, False, error=
                                 "The sample only has recorded observations for counting chairs. "
                                 "Start your own report to count something else.")
        else:
            result = observer.observe(photos, ["chair"] if row["sample"] else count_subjects(claims))
        if result.ok:
            obs = result.observations
            sam = get_sam() if not row["sample"] and count_subjects(claims) else None
            try:
                if sam is not None:
                    from .segment import enrich
                    obs = enrich(obs, photos, sam)
            except CheckLimitExceeded as exc:
                result = CheckResult(observer.name, False, error=str(exc))
            if result.ok:
                observations = [o.to_dict() for o in obs]
                decided = adjudicate(claims, obs)
                verdicts = [v.to_dict() for v in decided]
                attach_shots(listing_id, observer, photos, shot_needs(claims, decided), verdicts)
    latency = result.latency_ms or int((time.monotonic() - started) * 1000)
    check_id = store.save_check(version["id"], {s: p["id"] for s, p in current.items()}, observer.name,
                     result.ok, result.error, observations, verdicts, latency)
    store.log(listing_id, "check_run", observer=observer.name, ok=result.ok, error=result.error,
              version=version["version"])
    return check_id


def attach_shots(listing_id: str, observer, photos, needs: list[dict], verdicts: list[dict]) -> None:
    """Muse Spark plans the exact photo each `can't tell` needs. Seller-only advice: it never changes a verdict."""
    if not needs or not hasattr(observer, "plan_shots"):  # the replayed sample has no planner
        return
    try:
        plan = observer.plan_shots(photos, needs)
    except Exception as exc:  # ponytail: optional advice; the rule's generic request still shows
        store.log(listing_id, "shot_plan_failed", error=f"{type(exc).__name__}: {exc}")
        return
    for v in verdicts:
        if v["claim_id"] in plan:
            v["shot"] = plan[v["claim_id"]]


@app.post("/l/{listing_id}/report")
def issue(listing_id: str, k: str):
    token = issue_listing(listing_id, k)
    return RedirectResponse(f"/r/{token}", status_code=303)


def issue_listing(listing_id: str, k: str):
    row = seller_listing(listing_id, k)
    version = store.latest_version(listing_id)
    check = store.latest_check(version["id"])
    current = store.current_photos(listing_id)
    if not check or not check["ok"]:
        raise HTTPException(409, "Run a successful check first. A failed check never produces a report.")
    checked = json.loads(check["photos"])
    if checked != {s: p["id"] for s, p in current.items()}:
        raise HTTPException(409, "Photos changed since the last check. Run the check again.")
    if not checked:
        raise HTTPException(409, "Add at least one photo and check again. A report without photos backs up nothing.")
    from .adjudicate import Verdict, Status
    verdicts = [Verdict(v["claim_id"], Status(v["status"]), v["reason"], v["detail"],
                        tuple(v["photo_ids"]), v["request"]) for v in json.loads(check["verdicts"])]
    obs = [PhotoObservation.from_dict(o) for o in json.loads(check["observations"])]
    payload = reports.build_payload(
        listing_id=listing_id, version=version["version"], title=version["title"],
        description=version["description"], claims=store.claims_of(version), verdicts=verdicts,
        photos={s: current[s]["sha256"] for s in checked}, check_id=check["id"],
        observer=check["observer"], issued_at=datetime.now(timezone.utc),
        fresh_photo_ids=capture_code_seen(row["capture_code"], obs), capture_code=row["capture_code"])
    if row["sample"]:
        payload["sample"] = True
    token = store.issue_report(listing_id, version["id"], check["id"], payload, reports.digest(payload))
    return token


@app.post("/l/{listing_id}/edit")
async def edit(request: Request, listing_id: str, k: str):
    seller_listing(listing_id, k)
    form = await request.form()
    store.edit_listing(listing_id, (form.get("title") or "Untitled item")[:200],
                       (form.get("description") or "")[:2000], parse_claims(form))
    if request.query_params.get("check"):  # "Save and check" on a draft from the video
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(run_check, listing_id, k)
    return RedirectResponse(f"/l/{listing_id}?k={k}", status_code=303)


@app.post("/r/{token}/revoke")
def revoke(token: str, k: str):
    row = store.report(token)
    if row is None:
        raise HTTPException(404)
    seller_listing(row["listing_id"], k)
    store.revoke(token)
    return RedirectResponse(f"/r/{token}", status_code=303)


def public_report(token: str) -> tuple[dict, dict]:
    row = store.report(token)
    if row is None:
        raise HTTPException(404)
    payload = json.loads(row["payload"])
    state = reports.effective_state(row["state"], row["expires_at"])
    return row, {"state": state, "payload": payload, "digest": row["digest"]}


@app.get("/r/{token}", response_class=HTMLResponse)
def report_page(request: Request, token: str):
    row, view = public_report(token)
    photos = [(slot, f"/r/{token}/photo/{slot}") for slot in view["payload"]["photos"]] \
        if view["state"] == "active" else []
    return templates.TemplateResponse(request, "report.html", {
        **view, "token": token, "summary": reports.summary(view["payload"]),
        "checked_at": store.check(row["check_id"])["created_at"],
        "url": str(request.url), "photos": photos,
        "image": f"{request.base_url}r/{token}/card.jpg"})


def post_for_report(request: Request, row, view) -> dict:
    version = store.db.execute("SELECT * FROM versions WHERE id=?", (row["version_id"],)).fetchone()
    return build_post(version, view["payload"], str(request.url_for("report_page", token=row["token"])))


@app.get("/r/{token}/listing", response_class=HTMLResponse)
def buyer_listing(request: Request, token: str):
    row, view = public_report(token)
    active = view["state"] == "active"
    return templates.TemplateResponse(request, "buyer_listing.html", {
        **view, "token": token,
        "post": post_for_report(request, row, view) if active else None,
        "summary": reports.summary(view["payload"]) if active else None,
        "image": f"{request.base_url}r/{token}/card.jpg"},
        headers={"Cache-Control": "no-store"})


@app.get("/r/{token}/card.jpg")
def report_card(token: str):
    from .cards import render_card
    _, view = public_report(token)
    return Response(render_card(store, view), media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=60, must-revalidate"})


@app.get("/r/{token}/photo/{slot}")
def report_photo(token: str, slot: str):
    """The exact checked photos (EXIF already stripped on upload), only while the report is active."""
    row, view = public_report(token)
    sha = view["payload"]["photos"].get(slot)
    if view["state"] != "active" or not sha:
        raise HTTPException(404)
    return Response(store.photo_bytes(sha), media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=3600"})


@app.get("/api/r/{token}")
def report_api(request: Request, token: str):
    row, view = public_report(token)
    p = view["payload"]
    out = {"state": view["state"], "title": p["title"], "url": str(request.url_for("report_page", token=token))}
    if p.get("sample"):
        out["sample"] = True
    if view["state"] != "active":  # an old link never shows claims it no longer vouches for
        return JSONResponse(out)
    return JSONResponse({**out, "issued_at": p["issued_at"], "expires_at": p["expires_at"],
                         "digest": view["digest"], "observer": p["observer"],
                         "post": post_for_report(request, row, view),
                         "verdicts": [{"claim": c["text"], "by": c.get("by", ""), "status": c["verdict"]["status"],
                                       "detail": c["verdict"]["detail"],
                                       "request": c["verdict"]["request"]} for c in p["claims"]]})


# Buyer side: check any listing's own text against its own photos ------------------
def scan_claims(raw: list[dict]) -> list[Claim]:
    """Model-extracted claims, re-validated: a bad count subject or number becomes 'Other'."""
    claims = []
    for i, d in enumerate(raw[:8]):
        text = str(d.get("text", "")).strip()[:200]
        ctype = ClaimType(d.get("type", ClaimType.UNCHECKABLE))
        subject = " ".join(str(d.get("subject", "")).lower().split())[:40]
        value = str(d.get("value", "")).strip()[:40]
        if ctype == ClaimType.PIECE_COUNT and not (SUBJECT.fullmatch(subject) and value.isdigit()):
            ctype = ClaimType.UNCHECKABLE
        if text:
            claims.append(Claim(id=f"c{i + 1}", type=ctype, text=text,
                                subject=subject if ctype == ClaimType.PIECE_COUNT else "",
                                value=value if ctype in (ClaimType.PIECE_COUNT, ClaimType.COLOR) else ""))
    return claims


def seller_message(base: str, source: str, rows: list[dict]) -> str:
    asks = list(dict.fromkeys(r["request"] for r in rows if r["request"]))
    link = f"{base}new?{urlencode({'source': source})}" if source else f"{base}new"
    text = ("Hi! I'm interested. Before I come to see it, could you share a Verified Asset report? "
            f"It's a few photos with a code written on paper, and it's free: {link}")
    return text + ("\nThe photos that would help most: " + "; ".join(asks) + "." if asks else "")


def run_scan(title: str, description: str, images: list[bytes]) -> tuple[str, list[dict]]:
    """Text -> claims (text-only call), photos -> observations (never sees the text), rules decide.
    Parsed model results are cached; raw listing text and photos are not stored."""
    from .observe import Photo, prepare_image
    if not 1 <= len(images) <= MAX_SCAN_PHOTOS:
        raise HTTPException(422, f"Send between 1 and {MAX_SCAN_PHOTOS} photos of the listing.")
    if not (title.strip() or description.strip()):
        raise HTTPException(422, "The listing has no title or description to check.")
    try:
        observer = get_observer()
    except ValueError:
        raise HTTPException(503, "No model is configured on this server yet.")
    try:
        photos = [Photo(id=f"p{i + 1}", slot=f"listing {i + 1}", data=prepare_image(b)[0])
                  for i, b in enumerate(images)]
    except Exception:
        raise HTTPException(415, "One of the photos is not a readable image.")
    try:
        claims = scan_claims(observer.extract_claims(title[:200], description[:2000]))
    except Exception as exc:  # network, spending cap or an invalid answer
        raise HTTPException(503, f"Reading the listing text failed ({type(exc).__name__}). Try again.")
    if not claims:
        raise HTTPException(422, "The listing text doesn't make any claims to check.")
    result = observer.observe(photos, count_subjects(claims))
    if not result.ok:
        raise HTTPException(503, f"Looking at the photos failed ({result.error}). Try again.")
    obs = result.observations
    sam = get_sam() if count_subjects(claims) else None
    if sam is not None:
        from .segment import enrich
        obs = enrich(obs, photos, sam)
    store.log(None, "scan", observer=observer.name, photos=len(photos), claims=len(claims))
    return observer.name, [{"claim": c.text, "status": str(v.status), "detail": v.detail, "request": v.request}
                           for c, v in zip(claims, scan(claims, obs))]


class ScanIn(BaseModel):
    title: str = ""
    description: str = ""
    source: str = ""
    images: list[str]


def data_url_bytes(url: str) -> bytes:
    try:
        data = base64.b64decode(url.split(",", 1)[1], validate=True)
    except (IndexError, binascii.Error):
        raise HTTPException(422, "Photos must be base64 data URLs.")
    if len(data) > MAX_SCAN_BYTES:
        raise HTTPException(413, "Each photo must be 5 MB or smaller.")
    return data


def scan_enabled():
    """Off unless SCAN_ENABLED is set: the buyer scan is roadmap, shown only with our own sample photos."""
    if not os.getenv("SCAN_ENABLED"):
        raise HTTPException(404)


@app.post("/api/scan")
def scan_api(request: Request, body: ScanIn):
    scan_enabled()
    observer, rows = run_scan(body.title, body.description,
                              [data_url_bytes(u) for u in body.images[:MAX_SCAN_PHOTOS + 1]])
    return {"observer": observer, "claims": rows,
            "message": seller_message(str(request.base_url), body.source[:500], rows)}


@app.get("/scan", response_class=HTMLResponse)
def scan_form(request: Request):
    scan_enabled()
    return templates.TemplateResponse(request, "scan.html", {"max": MAX_SCAN_PHOTOS})


@app.post("/scan", response_class=HTMLResponse)
async def scan_page(request: Request, title: str = Form(""), description: str = Form(""),
                    files: list[UploadFile] = File(...)):
    scan_enabled()
    images = [await f.read(MAX_SCAN_BYTES + 1) for f in files[:MAX_SCAN_PHOTOS + 1] if f.filename]
    ctx = {"max": MAX_SCAN_PHOTOS, "title": title, "description": description}
    try:
        if any(len(b) > MAX_SCAN_BYTES for b in images):
            raise HTTPException(413, "Each photo must be 5 MB or smaller.")
        from starlette.concurrency import run_in_threadpool
        ctx["observer"], ctx["rows"] = await run_in_threadpool(run_scan, title, description, images)
        ctx["message"] = seller_message(str(request.base_url), "", ctx["rows"])
    except HTTPException as exc:
        ctx["error"] = exc.detail
    return templates.TemplateResponse(request, "scan.html", ctx)


from .whatsapp import router as whatsapp_router

app.include_router(whatsapp_router)
