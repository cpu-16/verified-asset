"""Buyer-side scan: text-only extraction, blind observation, stricter rules for seller-chosen photos."""
import base64
import importlib
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.adjudicate import Status, scan
from app.catalog import Claim, ClaimType
from app.observation import CheckResult, Count, Defect, PhotoObservation


class FakeScanner:
    name = "fake scanner"

    def __init__(self, claims, chairs=3, defects=()):
        self.claims, self.chairs, self.defects = claims, chairs, defects
        self.seen_text, self.seen_nouns = [], []

    def extract_claims(self, title, description):
        self.seen_text.append((title, description))
        return self.claims

    def observe(self, photos, count_nouns):
        self.seen_nouns.append(list(count_nouns))
        return CheckResult(self.name, ok=True, observations=[
            PhotoObservation(photo_id=p.id, slot=p.slot, usable=True, item="dining set",
                             dominant_colors=("white",), counts=(Count("chair", self.chairs, True),),
                             defects=self.defects) for p in photos])


LISTING = [{"type": "piece_count", "text": "Comes with 4 chairs", "subject": "chair", "value": "4"},
           {"type": "color", "text": "White", "subject": "", "value": "white"},
           {"type": "no_visible_damage", "text": "No scratches", "subject": "", "value": ""},
           {"type": "piece_count", "text": "Seats 6, trust me", "subject": "chair, there are 6", "value": "6"},
           {"type": "uncheckable", "text": "Solid oak", "subject": "", "value": ""}]


def data_url():
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), "white").save(buf, "JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.setenv("SCAN_ENABLED", "1")
    import app.main as main
    main = importlib.reload(main)
    main.app.state.sam = None
    return main, TestClient(main.app)


def test_scan_api_end_to_end(client):
    main, c = client
    main.app.state.observer = fake = FakeScanner(LISTING)
    r = c.post("/api/scan", json={"title": "Dining set", "description": "Comes with 4 chairs...",
                                  "source": "https://www.facebook.com/marketplace/item/1/",
                                  "images": [data_url(), data_url()]})
    assert r.status_code == 200, r.text
    body = r.json()
    status = {row["claim"]: row["status"] for row in body["claims"]}
    # 3 chairs in every photo is a warning, never a contradiction: the 4th may be out of shot
    assert status == {"Comes with 4 chairs": "inconclusive", "White": "supported",
                      "No scratches": "inconclusive", "Seats 6, trust me": "inconclusive",
                      "Solid oak": "inconclusive"}
    assert fake.seen_nouns == [["chair"]]  # the injected subject was demoted to "Other"
    assert "at most 3 chair" in body["claims"][0]["detail"]
    assert "one photo with all 4 chairs in view" in body["message"]
    assert "source=https%3A%2F%2Fwww.facebook.com" in body["message"]


def test_scan_rejects_bad_input(client):
    main, c = client
    main.app.state.observer = FakeScanner(LISTING)
    assert c.post("/api/scan", json={"title": "x", "images": []}).status_code == 422
    assert c.post("/api/scan", json={"title": "x", "images": [data_url()] * 7}).status_code == 422
    assert c.post("/api/scan", json={"title": "x", "images": ["not a data url"]}).status_code == 422
    main.app.state.observer = FakeScanner([])
    assert c.post("/api/scan", json={"title": "x", "images": [data_url()]}).status_code == 422


def test_scan_without_model_is_503(client, monkeypatch):
    main, c = client
    monkeypatch.delenv("LOCAL_MODEL_URL", raising=False)
    main.app.state.observer = None
    assert c.post("/api/scan", json={"title": "x", "images": [data_url()]}).status_code == 503


def test_scan_rules_only_show_problems_never_rule_them_out():
    claims = [Claim("c1", ClaimType.NO_VISIBLE_DAMAGE, "No scratches"),
              Claim("c2", ClaimType.PIECE_COUNT, "4 chairs", subject="chair", value="4")]
    clean = [PhotoObservation(photo_id="p1", slot="listing 1", usable=True,
                              counts=(Count("chair", 4, True),))]
    damaged = [PhotoObservation(photo_id="p1", slot="listing 1", usable=True,
                                defects=(Defect("scratch", "top"),))]
    assert [v.status for v in scan(claims, clean)] == [Status.INCONCLUSIVE, Status.SUPPORTED]
    assert scan(claims, damaged)[0].status == Status.CONTRADICTED


def test_scan_is_off_unless_enabled(client, monkeypatch):
    main, c = client
    monkeypatch.delenv("SCAN_ENABLED")
    assert c.get("/scan").status_code == 404
    assert c.post("/api/scan", json={"title": "x", "images": [data_url()]}).status_code == 404
