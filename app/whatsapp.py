"""WhatsApp Cloud API adapter. No model calls on the buyer path."""
import hashlib
import hmac
import json
import os
import re
import time
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse

from .catalog import SLOT_PROMPTS, Slot
from .observe import prepare_image, utc_day
from .store import file_lock

router = APIRouter()
SLOTS = (Slot.FRONT, Slot.SIDE, Slot.DETAIL)


def settings():
    values = {key: os.getenv(f"WA_{key}", "") for key in
              ("TOKEN", "PHONE_ID", "APP_SECRET", "VERIFY_TOKEN")}
    if not all(values.values()):
        raise HTTPException(404)
    values["GRAPH_VERSION"] = os.getenv("WA_GRAPH_VERSION", "v24.0")
    return values


class Client:
    def __init__(self, config, transport=None):
        self.config = config
        self.http = httpx.Client(transport=transport, timeout=30, follow_redirects=False,
                                 headers={"Authorization": f"Bearer {config['TOKEN']}"})
        self.graph = f"https://graph.facebook.com/{config['GRAPH_VERSION']}"

    def close(self):
        self.http.close()

    def send(self, sender, text):
        # Cloud API accepts at most 4096 characters per text message.
        for start in range(0, len(text), 4000):
            response = self.http.post(f"{self.graph}/{self.config['PHONE_ID']}/messages", json={
                "messaging_product": "whatsapp", "recipient_type": "individual", "to": sender,
                "type": "text", "text": {"preview_url": True, "body": text[start:start + 4000]}})
            response.raise_for_status()

    def photo(self, media_id, limit):
        if not re.fullmatch(r"[0-9]+", media_id):
            raise ValueError("Invalid media ID")
        response = self.http.get(f"{self.graph}/{media_id}",
                                 params={"phone_number_id": self.config["PHONE_ID"]})
        response.raise_for_status()
        metadata = response.json()
        if int(metadata.get("file_size", 0)) > limit:
            raise ValueError("Photo larger than 12 MB")
        url = urlsplit(metadata["url"])
        if (url.scheme != "https" or url.username or url.password or
                not (url.hostname == "facebook.com" or (url.hostname or "").endswith(".facebook.com")
                     or (url.hostname or "").endswith(".fbcdn.net")
                     or url.hostname == "lookaside.fbsbx.com")):
            raise ValueError("Unexpected media host")
        data = bytearray()
        with self.http.stream("GET", metadata["url"]) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > limit:
                    raise ValueError("Photo larger than 12 MB")
        return prepare_image(bytes(data))[0]


@router.get("/wa/webhook")
def verify(request: Request):
    config = settings()
    query = request.query_params
    if (query.get("hub.mode") != "subscribe" or not hmac.compare_digest(
            query.get("hub.verify_token", "").encode(), config["VERIFY_TOKEN"].encode())):
        raise HTTPException(403)
    if "hub.challenge" not in query:
        raise HTTPException(400)
    return PlainTextResponse(query["hub.challenge"])


@router.post("/wa/webhook")
async def webhook(request: Request, background: BackgroundTasks):
    config = settings()
    raw = await request.body()
    signature = "sha256=" + hmac.new(config["APP_SECRET"].encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature.encode(), request.headers.get("x-hub-signature-256", "").encode()):
        raise HTTPException(403)
    try:
        body = json.loads(raw)
        messages = []
        if body.get("object") == "whatsapp_business_account":
            for entry in body.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    if (change.get("field") == "messages" and
                            value.get("metadata", {}).get("phone_number_id") == config["PHONE_ID"]):
                        for message in value.get("messages", []):
                            if (isinstance(message.get("id"), str) and
                                    re.fullmatch(r"\d+", message.get("from", "")) and
                                    str(message.get("timestamp", "")).isdigit()):
                                messages.append(message)
        messages.sort(key=lambda m: int(m["timestamp"]))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(400)
    background.add_task(process, messages, str(request.base_url).rstrip("/"), config)
    return {"ok": True}


def report_text(view, code):
    payload = view["payload"]
    state = "valid" if view["state"] == "active" else view["state"]
    lines = [f"{'Sample report' if payload.get('sample') else 'Report'}: {state}. {payload['title']}"]
    if view["state"] != "active":
        return "\n".join(lines + ["Ask the seller for a new report. Previous verdicts no longer apply."])
    marks = {"supported": "✓ supported", "contradicted": "✕ contradicted", "inconclusive": "? can't tell"}
    for claim in payload["claims"]:
        verdict = claim["verdict"]
        lines.append(f"{marks[verdict['status']]} — {claim['text']}: {verdict['detail']}")
        if verdict["status"] == "inconclusive":
            if verdict.get("request"):
                lines.append(f"Ask the seller: Please send this photo: {verdict['request']} "
                             f"Include {code} written on paper in the photo.")
            else:
                lines.append(f"Ask the seller: How can you substantiate '{claim['text']}'? "
                             "Photos alone cannot confirm this claim.")
    return "\n".join(lines)


def buyer_link(text, base):
    for match in re.finditer(r"https?://[^\s<>]+", text):
        url = urlsplit(match[0].rstrip(".,;!?)]}"))
        if url.netloc == urlsplit(base).netloc and url.scheme == urlsplit(base).scheme:
            token = re.fullmatch(r"/r/([A-Za-z0-9_-]+)(?:/)?", url.path)
            if token:
                return token[1]
    return None


def handle(message, base, client):
    from . import main
    store = main.store
    sender = message["from"]
    text = (message.get("text", {}).get("body", "") if message["type"] == "text"
            else message.get("image", {}).get("caption", "")).strip()[:2000]
    if token := buyer_link(text, base):
        try:
            row, view = main.public_report(token)
        except HTTPException:
            return "Report not found. Check the link with the seller."
        return report_text(view, store.listing(row["listing_id"])["capture_code"])
    session = store.db.execute("SELECT * FROM wa_sessions WHERE sender=?", (sender,)).fetchone()
    if session is None or text.lower() == "new":
        if message["type"] != "text":
            return "Send a description first to start a listing and get your capture code."
        if not store.claim_paid_check("wa-new:" + sender, utc_day(), 20):
            return "You've started enough listings today. Try again tomorrow."
        description = "" if text.lower() == "new" else text
        listing_id, key = store.create_listing(description[:200] or "Untitled item", description, [])
        store.db.execute("INSERT OR REPLACE INTO wa_sessions VALUES (?,?,?,?)",
                         (sender, listing_id, description, "[]"))
        code = store.listing(listing_id)["capture_code"]
        return (f"Write {code} on paper. Send 3 photos in this order:\n" +
                "\n".join(f"{i + 1}. {slot}: {SLOT_PROMPTS[slot]}" for i, slot in enumerate(SLOTS)) +
                "\nKeep the paper visible in the front photo. Send a description of what you're selling "
                "as you would write it in your listing (text or a photo caption). "
                "Send 'new' to start another item.")
    listing_id = session["listing_id"]
    row = store.listing(listing_id)
    images = json.loads(session["images"])
    description = session["description"]
    if message["type"] == "image":
        replacement = text.lower() if len(images) >= 3 and text.lower() in SLOTS else None
        if len(images) >= 3 and not replacement:
            return "To replace a photo, send it with the caption 'front', 'side' or 'detail'."
        data = client.photo(message["image"]["id"], main.MAX_PHOTO_BYTES)
        version = store.latest_version(listing_id)
        # Invalidate before changing evidence, even if the next model call fails.
        store.edit_listing(listing_id, version["title"], version["description"], store.claims_of(version))
        if replacement:
            store.add_photo(listing_id, replacement, data)
        else:
            sha = hashlib.sha256(data).hexdigest()
            (store.blobs / sha).write_bytes(data)
            images.append({"sha": sha, "timestamp": int(message["timestamp"]), "id": message["id"]})
            images.sort(key=lambda image: image["timestamp"])
            current = store.current_photos(listing_id)
            for slot, image in zip(SLOTS, images):
                if slot not in current or current[slot]["sha256"] != image["sha"]:
                    store.add_photo(listing_id, slot, store.photo_bytes(image["sha"]))
        if text and not replacement:
            description = text
    elif text:
        description = text
        version = store.latest_version(listing_id)
        store.edit_listing(listing_id, description[:200], description, store.claims_of(version))
    store.db.execute("UPDATE wa_sessions SET description=?, images=? WHERE sender=?",
                     (description, json.dumps(images), sender))
    if len(store.current_photos(listing_id)) < 3 or not description:
        return "Photo received. Send the remaining views and your listing description."
    if not store.claim_paid_check("wa-check:" + sender, utc_day(), 20):
        return "That's your daily limit of checks. Try again tomorrow. No new report was issued."
    request = Request({"type": "http", "client": ("wa:" + sender, 0), "headers": []})
    claims, error = main.suggested_claims(request, description[:200], description)
    if error:
        return error + " No new report was issued. Send an updated description to retry."
    store.edit_listing(listing_id, description[:200], description, claims)
    try:
        check_id = main.check_listing(listing_id, row["seller_key"])
    except Exception:
        return "The check failed or reached its spending limit. No new report was issued. Try again later."
    check = store.check(check_id) if check_id else None
    if not check or not check["ok"]:
        return "The check failed or reached its spending limit. No new report was issued. Try again later."
    token = main.issue_listing(listing_id, row["seller_key"])
    _, view = main.public_report(token)
    # Separate public and capability links so only the public report gets a preview.
    return [report_text(view, row["capture_code"]) + f"\n{base}/r/{token}",
            f"Private seller link — keep it to yourself: {base}/l/{listing_id}?k={row['seller_key']}"]


def process(messages, base, config):
    from . import main
    allowed = os.getenv("WA_ALLOWED")
    allowed = {n.strip().lstrip("+") for n in allowed.split(",")} if allowed is not None else None
    client = Client(config, getattr(main.app.state, "wa_transport", None))
    try:
        for message in messages:
            sender = message["from"]
            if allowed is not None and sender not in allowed:
                continue
            if message.get("type") not in ("text", "image"):
                continue
            # Do not answer retries from outside the customer service window.
            if not 0 <= time.time() - int(message["timestamp"]) < 86400:
                continue
            lock = hashlib.sha256(sender.encode()).hexdigest()
            with file_lock(main.store.data_dir / "wa-locks" / lock):
                inserted = main.store.db.execute("INSERT OR IGNORE INTO wa_messages VALUES (?,?,?)",
                                                  (message["id"], sender, int(message["timestamp"])))
                if not inserted.rowcount:
                    continue
                try:
                    reply = handle(message, base, client)
                except Exception:
                    reply = ("We couldn't complete this request. "
                             "Check your private listing link, or send the message again to retry.")
                try:
                    for text in reply if isinstance(reply, list) else [reply]:
                        if time.time() - int(message["timestamp"]) < 86400:
                            client.send(sender, text)
                except httpx.HTTPError:
                    # No exception body or URL: either may contain credentials or private links.
                    main.store.log(None, "wa_send_failed")
    finally:
        client.close()
