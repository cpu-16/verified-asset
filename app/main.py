"""Web app: seller flow (claims -> guided photos -> check -> report) and public reports.

Sellers have no accounts: the listing URL carries a secret `k` (capability link).
"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from . import reports
from .adjudicate import adjudicate, capture_code_seen
from .catalog import SLOT_PROMPTS, Claim, ClaimType, Slot, count_subjects, required_slots
from .observation import PhotoObservation
from .store import Store

BASE = Path(__file__).parent
DATA = Path(os.environ.get("DATA_DIR", "data"))
MAX_PHOTO_BYTES = 12_000_000
CLAIM_ROWS = 6

app = FastAPI(title="Verified Asset")
app.add_middleware(CORSMiddleware, allow_origins=["https://www.facebook.com"],
                   allow_methods=["GET"])  # the browser extension reads /api/r/* from Marketplace
templates = Jinja2Templates(directory=BASE / "templates")
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


def parse_claims(form) -> list[Claim]:
    claims = []
    for i in range(CLAIM_ROWS):
        text = (form.get(f"text{i}") or "").strip()
        if not text:
            continue
        ctype = ClaimType(form.get(f"type{i}") or ClaimType.UNCHECKABLE)
        claims.append(Claim(id=f"c{i + 1}", type=ctype, text=text[:200],
                            subject=(form.get(f"subject{i}") or "").strip()[:40],
                            value=(form.get(f"value{i}") or "").strip()[:40]))
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


@app.get("/l/{listing_id}", response_class=HTMLResponse)
def listing_page(request: Request, listing_id: str, k: str):
    row = seller_listing(listing_id, k)
    version = store.latest_version(listing_id)
    claims = store.claims_of(version)
    photos = store.current_photos(listing_id)
    check = store.latest_check(version["id"])
    verdicts = {v["claim_id"]: v for v in json.loads(check["verdicts"])} if check and check["ok"] else {}
    stale = bool(check) and json.loads(check["photos"]) != {s: p["id"] for s, p in photos.items()}
    return templates.TemplateResponse(request, "listing.html", {
        "listing": row, "k": k, "version": version, "claims": claims, "photos": photos,
        "slots": [(s, SLOT_PROMPTS[s]) for s in required_slots(claims)] or [(Slot.FRONT, SLOT_PROMPTS[Slot.FRONT])],
        "check": check, "verdicts": verdicts, "stale": stale,
        "reports": store.active_reports(listing_id), "types": list(ClaimType),
        "rows": range(CLAIM_ROWS)})


@app.get("/l/{listing_id}/photo/{photo_id}")
def photo(listing_id: str, photo_id: str, k: str):
    seller_listing(listing_id, k)  # raw photos are only ever shown to the seller
    row = store.photo(photo_id)
    if row is None or row["listing_id"] != listing_id:
        raise HTTPException(404)
    return Response(store.photo_bytes(row["sha256"]), media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=3600"})


@app.post("/l/{listing_id}/photo")
async def upload(listing_id: str, k: str, slot: Slot = Form(...), file: UploadFile = File(...)):
    seller_listing(listing_id, k)
    data = await file.read(MAX_PHOTO_BYTES + 1)
    if not data or len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "Photo missing or larger than 12 MB.")
    from .observe import prepare_image  # strips EXIF/GPS before anything is stored
    try:
        data, _ = prepare_image(data)
    except Exception:
        raise HTTPException(415, "That file is not a readable image.")
    store.add_photo(listing_id, str(slot), data)
    return RedirectResponse(f"/l/{listing_id}?k={k}#photos", status_code=303)


@app.post("/l/{listing_id}/check")
def run_check(listing_id: str, k: str):
    from .observe import Photo
    row = seller_listing(listing_id, k)
    version = store.latest_version(listing_id)
    claims = store.claims_of(version)
    current = store.current_photos(listing_id)
    photos = [Photo(id=p["id"], slot=s, data=store.photo_bytes(p["sha256"])) for s, p in current.items()]
    observer = get_observer()
    started = time.monotonic()
    result = observer.observe(photos, count_subjects(claims))
    observations, verdicts = [], []
    if result.ok:
        obs = result.observations
        sam = get_sam()
        if sam is not None:
            from .segment import enrich
            obs = enrich(obs, photos, sam)
        observations = [o.to_dict() for o in obs]
        verdicts = [v.to_dict() for v in adjudicate(claims, obs)]
    latency = result.latency_ms or int((time.monotonic() - started) * 1000)
    store.save_check(version["id"], {s: p["id"] for s, p in current.items()}, observer.name,
                     result.ok, result.error, observations, verdicts, latency)
    store.log(listing_id, "check_run", observer=observer.name, ok=result.ok, error=result.error,
              version=version["version"])
    return RedirectResponse(f"/l/{listing_id}?k={k}#check", status_code=303)


@app.post("/l/{listing_id}/report")
def issue(listing_id: str, k: str):
    row = seller_listing(listing_id, k)
    version = store.latest_version(listing_id)
    check = store.latest_check(version["id"])
    current = store.current_photos(listing_id)
    if not check or not check["ok"]:
        raise HTTPException(409, "Run a successful check first. A failed check never produces a report.")
    checked = json.loads(check["photos"])
    if checked != {s: p["id"] for s, p in current.items()}:
        raise HTTPException(409, "Photos changed since the last check. Run the check again.")
    from .adjudicate import Verdict, Status
    verdicts = [Verdict(v["claim_id"], Status(v["status"]), v["reason"], v["detail"],
                        tuple(v["photo_ids"]), v["request"]) for v in json.loads(check["verdicts"])]
    obs = [PhotoObservation.from_dict(o) for o in json.loads(check["observations"])]
    payload = reports.build_payload(
        listing_id=listing_id, version=version["version"], title=version["title"],
        description=version["description"], claims=store.claims_of(version), verdicts=verdicts,
        photos={s: current[s]["sha256"] for s in checked}, check_id=check["id"],
        observer=check["observer"], issued_at=datetime.now(timezone.utc),
        fresh_photo_ids=capture_code_seen(row["capture_code"], obs))
    token = store.issue_report(listing_id, version["id"], check["id"], payload, reports.digest(payload))
    return RedirectResponse(f"/r/{token}", status_code=303)


@app.post("/l/{listing_id}/edit")
async def edit(request: Request, listing_id: str, k: str):
    seller_listing(listing_id, k)
    form = await request.form()
    store.edit_listing(listing_id, (form.get("title") or "Untitled item")[:200],
                       (form.get("description") or "")[:2000], parse_claims(form))
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
    return templates.TemplateResponse(request, "report.html", {
        **view, "token": token, "summary": reports.summary(view["payload"]),
        "url": str(request.url)})


@app.get("/api/r/{token}")
def report_api(request: Request, token: str):
    row, view = public_report(token)
    p = view["payload"]
    out = {"state": view["state"], "title": p["title"], "url": str(request.url_for("report_page", token=token))}
    if view["state"] != "active":  # an old link never shows claims it no longer vouches for
        return JSONResponse(out)
    return JSONResponse({**out, "issued_at": p["issued_at"], "expires_at": p["expires_at"],
                         "digest": view["digest"], "observer": p["observer"],
                         "verdicts": [{"claim": c["text"], "status": c["verdict"]["status"],
                                       "detail": c["verdict"]["detail"],
                                       "request": c["verdict"]["request"]} for c in p["claims"]]})
