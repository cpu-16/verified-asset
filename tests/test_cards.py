"""Report social card: size, format, and no verdicts once the report stops vouching."""
import io
import os
from types import SimpleNamespace

from PIL import Image

from app.cards import render_card


def noisy_jpeg():  # worst case for JPEG size
    buf = io.BytesIO()
    Image.frombytes("RGB", (900, 1200), os.urandom(900 * 1200 * 3)).save(buf, "JPEG", quality=95)
    return buf.getvalue()


def view(state, claims, sample=False):
    statuses = ["supported", "contradicted", "inconclusive", "supported", "supported"]
    payload = {"title": "Sillón y mesa de comedor blanca con 4 sillas, poco uso, retiro en el centro",
               "photos": {"front": "f" * 64, "side": "s" * 64},
               "claims": [{"text": f"Claim number {i} with a long text that has to be cut to fit the card",
                           "verdict": {"status": s}} for i, s in enumerate(statuses[:claims])]}
    if sample:
        payload["sample"] = True
    return {"state": state, "payload": payload, "digest": "ab12cd34" + "0" * 56}


def test_active_card_is_a_small_1200x630_jpeg():
    photo = noisy_jpeg()
    for v in (view("active", 5), view("active", 2, sample=True)):
        data = render_card(SimpleNamespace(photo_bytes=lambda sha: photo), v)
        img = Image.open(io.BytesIO(data))
        assert (img.format, img.size) == ("JPEG", (1200, 630)) and len(data) < 300_000


def test_inactive_card_shows_neither_verdicts_nor_photo():
    def no_photo(sha):
        raise AssertionError("an inactive report's photo was read")

    store = SimpleNamespace(photo_bytes=no_photo)
    for state in ("revoked", "invalidated", "expired"):
        card = render_card(store, view(state, 5))
        assert Image.open(io.BytesIO(card)).size == (1200, 630)
        assert card == render_card(store, view(state, 0))  # the claims leave no trace on the card
