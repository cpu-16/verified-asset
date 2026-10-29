import hashlib
import hmac
import json
import time

import httpx
import pytest

from test_app import client, FakeObserver, jpeg


class Observer(FakeObserver):
    def extract_claims(self, title, description):
        return [{"type": "color", "text": "White finish", "value": "white"},
                {"type": "uncheckable", "text": "Solid oak"}]


@pytest.fixture
def wa(client, monkeypatch):
    main, c = client
    for key, value in {"TOKEN": "token", "PHONE_ID": "123", "APP_SECRET": "secret",
                       "VERIFY_TOKEN": "verify"}.items():
        monkeypatch.setenv("WA_" + key, value)
    monkeypatch.delenv("WA_ALLOWED", raising=False)
    main.app.state.observer = Observer()
    sent, downloads = [], []

    def http(request):
        assert request.headers["Authorization"] == "Bearer token"
        if request.method == "POST":
            body = json.loads(request.content)
            assert body["type"] == "text" and body["text"]["preview_url"]
            sent.append(body["text"]["body"])
            return httpx.Response(200, json={"messages": [{"id": "out"}]})
        if request.url.host == "graph.facebook.com":
            return httpx.Response(200, json={"url": "https://lookaside.fbsbx.com/media"})
        downloads.append(str(request.url))
        return httpx.Response(200, content=jpeg())

    # Meta's media download URLs use lookaside.fbsbx.com.
    main.app.state.wa_transport = httpx.MockTransport(http)
    return main, c, sent, downloads


def post(wa, messages):
    body = {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages",
            "value": {"metadata": {"phone_number_id": "123"}, "messages": messages}}]}]}
    raw = json.dumps(body).encode()
    signature = "sha256=" + hmac.new(b"secret", raw, hashlib.sha256).hexdigest()
    return wa[1].post("/wa/webhook", content=raw, headers={"X-Hub-Signature-256": signature})


def message(id, text=None, image=False, timestamp=None, sender="15551234"):
    m = {"id": id, "from": sender, "timestamp": str(timestamp or int(time.time()) - 10),
         "type": "image" if image else "text"}
    m[m["type"]] = {"id": "456", "caption": text or ""} if image else {"body": text or "White chairs"}
    return m


def seller(wa):
    assert post(wa, [message("start")]).status_code == 200
    assert "paper" in wa[2][-1]
    assert post(wa, [message("photo1", image=True), message("photo2", image=True),
                     message("photo3", image=True)]).status_code == 200
    row = wa[0].store.db.execute("SELECT * FROM reports").fetchone()
    assert row is not None, wa[2]
    return row["token"]


def test_disabled(client, monkeypatch):
    monkeypatch.delenv("WA_TOKEN", raising=False)
    assert client[1].get("/wa/webhook").status_code == 404
    assert client[1].post("/wa/webhook").status_code == 404


def test_verification_and_signature(wa):
    c = wa[1]
    query = {"hub.mode": "subscribe", "hub.verify_token": "verify", "hub.challenge": "007"}
    r = c.get("/wa/webhook", params=query)
    assert r.status_code == 200 and r.text == "007"
    query["hub.verify_token"] = "bad"
    assert c.get("/wa/webhook", params=query).status_code == 403
    assert c.post("/wa/webhook", content=b"{}").status_code == 403
    assert not wa[2]


def test_seller_buyer_retake_and_duplicate(wa):
    token = seller(wa)
    assert any(f"/r/{token}" in text for text in wa[2])
    assert "/l/" in wa[2][-1] and "?k=" in wa[2][-1]
    assert len(wa[3]) == 3
    before = len(wa[2])
    post(wa, [message("photo3", image=True)])
    assert len(wa[2]) == before and len(wa[3]) == 3
    wa[0].app.state.observer = object()
    post(wa, [message("buyer", f"What about http://testserver/r/{token}?", sender="15559999")])
    assert "Report: valid" in wa[2][-1] and "✓ supported" in wa[2][-1] and "? can't tell" in wa[2][-1]
    wa[0].app.state.observer = Observer()
    post(wa, [message("retake", "side", image=True)])
    assert wa[0].store.report(token)["state"] == "invalidated"
    assert wa[0].store.db.execute("SELECT count(*) FROM reports").fetchone()[0] == 2
    post(wa, [message("old", f"http://testserver/r/{token}", sender="15559999")])
    assert "invalidated" in wa[2][-1] and "✓" not in wa[2][-1]


def test_allowlist_and_old_messages(wa, monkeypatch):
    monkeypatch.setenv("WA_ALLOWED", "+15550000")
    post(wa, [message("blocked")])
    assert not wa[2]
    monkeypatch.setenv("WA_ALLOWED", "15551234")
    post(wa, [message("old", timestamp=int(time.time()) - 90000)])
    assert not wa[2]
    assert wa[0].store.db.execute("SELECT count(*) FROM listings").fetchone()[0] == 0


def test_failure_no_report_and_sender_limit(wa):
    wa[0].app.state.observer = Observer(ok=False)
    post(wa, [message("start"), message("p1", image=True), message("p2", image=True), message("p3", image=True)])
    assert wa[0].store.db.execute("SELECT count(*) FROM reports").fetchone()[0] == 0
    assert any("failed" in text for text in wa[2])


def test_media_size_and_host(wa):
    from app.whatsapp import Client, settings
    for metadata in ({"url": "https://evil.example/p"},
                     {"url": "https://lookaside.fbsbx.com/p", "file_size": 12000001}):
        api = Client(settings(), httpx.MockTransport(lambda req: httpx.Response(200, json=metadata)))
        with pytest.raises(ValueError):
            api.photo("456", 12000000)
        api.close()


def test_photo_timestamp_order(wa):
    post(wa, [message("start")])
    now = int(time.time()) - 5
    post(wa, [message("late", image=True, timestamp=now)])
    post(wa, [message("early", image=True, timestamp=now - 2)])
    post(wa, [message("middle", image=True, timestamp=now - 1)])
    session = wa[0].store.db.execute("SELECT images FROM wa_sessions").fetchone()
    assert [p["id"] for p in json.loads(session[0])] == ["early", "middle", "late"]


def test_budget_exception_and_sender_daily_limit(wa):
    from app.observe import BudgetExceeded, utc_day

    class Limited(Observer):
        def observe(self, photos, count_nouns):
            raise BudgetExceeded("cap")

    wa[0].app.state.observer = Limited()
    post(wa, [message("start"), message("a", image=True), message("b", image=True), message("c", image=True)])
    assert "No new report" in wa[2][-1]
    assert wa[0].store.db.execute("SELECT count(*) FROM reports").fetchone()[0] == 0
    wa[0].store.db.execute("UPDATE paid_checks SET count=20 WHERE listing_id=? AND day=?",
                           ("wa-check:15551234", utc_day()))
    wa[0].app.state.observer = object()
    post(wa, [message("limit", "White chairs")])
    assert "daily limit" in wa[2][-1]


def test_buyer_request_and_inactive_states(wa):
    class CountObserver(Observer):
        def extract_claims(self, title, description):
            return [{"type": "piece_count", "text": "4 tables", "subject": "table", "value": "4"}]

    wa[0].app.state.observer = CountObserver()
    token = seller(wa)
    row = wa[0].store.report(token)
    code = wa[0].store.listing(row["listing_id"])["capture_code"]
    wa[0].app.state.observer = object()
    post(wa, [message("buyer", f"http://testserver/r/{token}")])
    assert "? can't tell" in wa[2][-1] and code in wa[2][-1] and "paper" in wa[2][-1]
    wa[0].store.db.execute("UPDATE reports SET expires_at='2000-01-01T00:00:00+00:00' WHERE token=?", (token,))
    post(wa, [message("expired", f"http://testserver/r/{token}")])
    assert "expired" in wa[2][-1] and "? can't tell" not in wa[2][-1]
    wa[0].store.revoke(token)
    post(wa, [message("revoked", f"http://testserver/r/{token}")])
    assert "revoked" in wa[2][-1]


def test_new_and_caption_description(wa):
    post(wa, [message("start", "new")])
    post(wa, [message("a", image=True), message("b", image=True), message("c", "White finish", image=True)])
    assert wa[0].store.db.execute("SELECT count(*) FROM reports").fetchone()[0] == 1
    post(wa, [message("new", "new")])
    assert wa[0].store.db.execute("SELECT count(*) FROM listings").fetchone()[0] == 2


def test_failed_retake_invalidates_old_report(wa):
    token = seller(wa)
    wa[0].app.state.observer = Observer(ok=False)
    post(wa, [message("retake", "front", image=True)])
    assert wa[0].store.report(token)["state"] == "invalidated"
    assert wa[0].store.db.execute("SELECT count(*) FROM reports").fetchone()[0] == 1
    assert "No new report" in wa[2][-1]


def test_listing_paid_limit_and_persistent_deduplication(wa, monkeypatch):
    from app.observe import _before_paid_call
    from app.store import Store

    class Paid(Observer):
        def observe(self, photos, count_nouns):
            _before_paid_call.get()()
            return super().observe(photos, count_nouns)

    monkeypatch.setenv("CHECKS_PER_LISTING_PER_DAY", "0")
    wa[0].app.state.observer = Paid()
    post(wa, [message("start"), message("a", image=True), message("b", image=True), message("c", image=True)])
    assert "No new report" in wa[2][-1]
    assert wa[0].store.db.execute("SELECT count(*) FROM reports").fetchone()[0] == 0
    before = len(wa[2])
    wa[0].store = Store(wa[0].store.data_dir)
    post(wa, [message("start")])
    assert len(wa[2]) == before


def test_card_endpoint_and_metadata(wa):
    from PIL import Image
    import io

    token = seller(wa)
    c = wa[1]
    response = c.get(f"/r/{token}/card.jpg")
    assert response.headers["content-type"] == "image/jpeg"
    assert "max-age=60" in response.headers["cache-control"]
    assert len(response.content) < 300000
    assert Image.open(io.BytesIO(response.content)).size == (1200, 630)
    page = c.get(f"/r/{token}").text
    assert f'og:image" content="http://testserver/r/{token}/card.jpg"' in page
    assert 'og:image:width" content="1200"' in page and 'summary_large_image' in page
    wa[0].store.revoke(token)
    assert c.get(f"/r/{token}/card.jpg").status_code == 200
    assert c.get("/r/missing/card.jpg").status_code == 404
