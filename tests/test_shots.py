"""Muse Spark's shot plan: neutral needs in, one checked instruction per `can't tell` out."""
import json

import httpx

from app.adjudicate import Status, adjudicate, shot_needs
from app.catalog import Claim, ClaimType
from app.observation import Count, PhotoObservation
from app.observe import Photo, SparkObserver, SpendGuard, clean_plan, plan_prompt


def obs(slot, **kw):
    return PhotoObservation(photo_id=f"p-{slot}", slot=slot, usable=kw.pop("usable", True), **kw)


CLAIMS = [Claim("c1", ClaimType.PIECE_COUNT, "Set of 4 chairs", "chair", "4"),
          Claim("c2", ClaimType.COLOR, "Ivory white", value="ivory"),
          Claim("c3", ClaimType.LABEL_TEXT, "Genuine IKEA", value="IKEA"),
          Claim("c4", ClaimType.UNCHECKABLE, "Solid oak")]


def test_needs_are_neutral_and_only_for_photo_checkable_cant_tell():
    photos = [obs("front", usable=False, usability_issue="too_dark"),
              obs("side", counts=(Count("chair", 3, False),))]
    needs = shot_needs(CLAIMS, adjudicate(CLAIMS, photos))
    assert [n["id"] for n in needs] == ["c1", "c2", "c3"]  # c4 can never be settled by a photo
    assert needs[0]["problem"] == "the front photo is too blurry, dark or cut off"
    text = json.dumps(needs) + plan_prompt(needs)
    for leak in ("4", "ivory", "IKEA", "Set of", "Solid oak"):  # never the seller's words or values
        assert leak not in text


def test_no_needs_when_everything_is_decided():
    photos = [obs("front", dominant_colors=("white",), counts=(Count("chair", 4, True),)),
              obs("side", counts=(Count("chair", 4, True),))]
    verdicts = adjudicate(CLAIMS[:2], photos)
    assert {v.status for v in verdicts} == {Status.SUPPORTED} and shot_needs(CLAIMS[:2], verdicts) == []


def test_clean_plan_keeps_one_valid_shot_per_need():
    needs = [{"id": "c1"}, {"id": "c2"}]
    raw = {"shots": [
        {"need": "c1", "slot": "front", "instruction": "  Step back so  all chairs fit. ", "photo": "front", "box": [100, 200, 900, 950]},
        {"need": "c1", "slot": "side", "instruction": "duplicate", "photo": "none", "box": []},
        {"need": "c2", "slot": "front", "instruction": "Open the curtains.", "photo": "detail", "box": [0, 0, 10, 10]},
        {"need": "zz", "slot": "front", "instruction": "unknown need", "photo": "none", "box": []}]}
    plan = clean_plan(raw, needs, {"front", "side"}, "muse-spark-1.3")
    assert plan["c1"] == {"slot": "front", "instruction": "Step back so all chairs fit.", "photo": "front",
                          "box": [100, 200, 900, 950], "by": "muse-spark-1.3"}
    assert plan["c2"]["box"] == [] and plan["c2"]["photo"] == ""  # no detail photo exists to draw on
    assert set(plan) == {"c1", "c2"}
    bad = {"shots": [{"need": "c1", "slot": "front", "instruction": "x", "photo": "front", "box": [500, 0, 400, 2000]}]}
    assert clean_plan(bad, needs, {"front"}, "m")["c1"]["box"] == []


def test_plan_shots_sends_photos_and_needs_and_is_cached(tmp_path):
    calls = []
    answer = {"shots": [{"need": "c1", "slot": "side", "instruction": "Shoot the left side from 2 m.",
                         "photo": "none", "box": []}]}

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer)}}],
                                         "usage": {"prompt_tokens": 900, "completion_tokens": 60}})

    import io
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (40, 30), "white").save(buf, "JPEG")
    photos = [Photo("p1", "front", buf.getvalue())]
    needs = [{"id": "c1", "task": "see every chair fully, in one photo", "problem": "some pieces may be out of view or hidden"}]
    guard = SpendGuard(tmp_path / "spend.json", 1)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        spark = SparkObserver("key", client=client, guard=guard)
        assert spark.plan_shots(photos, needs)["c1"]["instruction"] == "Shoot the left side from 2 m."
        spark.plan_shots(photos, needs)
    assert len(calls) == 1  # same photos and needs: the cached plan, no second paid call
    content = calls[0]["messages"][0]["content"]
    assert [c["type"] for c in content] == ["text", "text", "image_url"] and content[1]["text"] == "Photo: front"
    assert guard.spent_usd > 0
