from io import BytesIO
import json

import httpx
from PIL import Image
import pytest

from app.observation import Count, Defect, PhotoObservation
from app.observe import BudgetExceeded, Photo, SpendGuard
from app.segment import SamCounter, enrich, parse_boxes


SAMPLE = ("<0f>0<|box;x1=10;y1=20;x2=100;y2=200;w=640;h=480|>"
          "<|mask;x=0;y=0;data=480,640,~abc!|>,"
          "2<|box;w=640;h=480;y2=220;x2=300;y1=30;x1=150;c=0.98|>"
          "<|mask;x=0;y=0;c=0.98;data=480,640,~def|>")


def image_bytes():
    output = BytesIO()
    Image.new("RGB", (640, 480)).save(output, format="PNG")
    return output.getvalue()


def stream(events):
    return httpx.Response(200, headers={"content-type": "text/event-stream"},
                          text="".join("data: " + json.dumps(e) + "\n\n" for e in events))


def test_boxes_distinct_ids_first_frame_and_confidence():
    assert parse_boxes(SAMPLE) == [(10, 20, 100, 200), (150, 30, 300, 220)]
    assert parse_boxes(SAMPLE + "\n" + SAMPLE.replace("<0f>", "<1f>")) == parse_boxes(SAMPLE)
    assert parse_boxes(SAMPLE + "," + SAMPLE.split("<0f>")[1]) == parse_boxes(SAMPLE)
    assert parse_boxes("") == []
    with pytest.raises(ValueError):
        parse_boxes("unexpected output")


def test_streamed_counter_and_usage(tmp_path):
    def handler(request):
        assert request.url.path == "/v1/responses"
        assert request.headers["accept"] == "text/event-stream"
        body = json.loads(request.content)
        assert body["model"] == "sam-3.1" and body["stream"] is True
        content = body["input"][0]["content"]
        assert content[0] == {"type": "input_text", "text": "chair"}
        assert content[1]["image_url"].startswith("data:image/jpeg;base64,")
        return stream([{"type": "response.output_text.delta", "delta": SAMPLE[:45]},
                       {"type": "response.output_text.delta", "delta": SAMPLE[45:]},
                       {"type": "response.completed"}])

    guard = SpendGuard(tmp_path / "spend.json", 1)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert SamCounter("key", client=client, guard=guard).count(image_bytes(), "chair") == 2
    assert guard.spent_usd == pytest.approx(0.0025)


@pytest.mark.parametrize("events,expected", [([{"type": "response.completed"}], 0),
                                              ([], None),
                                              ([{"type": "response.failed"}], None)])
def test_empty_and_failed_streams(events, expected):
    with httpx.Client(transport=httpx.MockTransport(lambda r: stream(events))) as client:
        sam = SamCounter("key", client=client)
        if expected is None:
            with pytest.raises(ValueError):
                sam.count(image_bytes(), "chair")
        else:
            assert sam.count(image_bytes(), "chair") == expected


def test_sam_budget_prevents_request(tmp_path):
    calls = []
    with httpx.Client(transport=httpx.MockTransport(lambda r: calls.append(r))) as client:
        sam = SamCounter("key", client=client, guard=SpendGuard(tmp_path / "spend.json", 0))
        with pytest.raises(BudgetExceeded):
            sam.count(image_bytes(), "chair")
    assert not calls


@pytest.mark.parametrize("fail", [False, True])
def test_enrich_is_atomic_per_photo_and_preserves_original(fail):
    observation = PhotoObservation("p", "front", True, counts=(Count("chair", 2, True),),
                                   defects=(Defect("scratch", "seat"),))

    class Sam:
        def count(self, data, noun):
            assert noun == "chair"
            return 3

        def boxes(self, data, phrase):
            assert phrase == "scratch"
            if fail:
                raise RuntimeError("SAM unavailable after count")
            return [(1, 2, 3, 4), (5, 6, 7, 8)]

    [result] = enrich([observation], [Photo("p", "front", b"image")], Sam())
    assert observation.counts[0].sam_count is None and observation.defects[0].box is None
    if fail:
        assert result is observation
    else:
        assert result.counts[0].sam_count == 3 and result.defects[0].box == (1, 2, 3, 4)


def test_sam_cache_persists_and_keys_on_photo_and_noun(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    calls = []

    def handler(request):
        calls.append(request)
        return stream([{"type": "response.output_text.delta", "delta": SAMPLE},
                       {"type": "response.completed"}])

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        guard = SpendGuard(tmp_path / "spend.json", 1)
        sam = SamCounter("key", client=client, guard=guard)
        with ThreadPoolExecutor(max_workers=3) as pool:
            assert list(pool.map(lambda _: sam.count(image_bytes(), "chair"), range(3))) == [2] * 3
        assert len(calls) == 1
        sam = SamCounter("key", client=client, guard=SpendGuard(guard.path, 0))
        assert sam.boxes(image_bytes(), "chair") == parse_boxes(SAMPLE)
        assert len(calls) == 1
        sam.guard.cap_usd = 1
        assert sam.count(image_bytes(), "table") == 2
        assert sam.count(image_bytes() + b"changed", "chair") == 2
        assert len(calls) == 3
