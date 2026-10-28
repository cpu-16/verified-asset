import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import inspect
from io import BytesIO
import json
from threading import Barrier

import httpx
from PIL import Image
import pytest

from app.observe import (BudgetExceeded, LocalObserver, Photo, ReplayObserver,
                         SparkObserver, SpendGuard, observation_prompt,
                         observer_from_env, prepare_image)
from app.observation import observation_schema


def image_bytes(size=(30, 20)):
    output = BytesIO()
    image = Image.new("RGB", size, "brown")
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "private metadata"
    image.save(output, format="JPEG", exif=exif)
    return output.getvalue()


def model_json():
    return {"usable": True, "usability_issue": "none", "item": "chair",
            "dominant_colors": ["brown"], "counts": [
                {"noun": "chair", "count": 2, "all_instances_fully_visible": True}],
            "defects": [], "visible_text": ["7Q4K"]}


def response(content=None):
    return httpx.Response(200, json={"choices": [{"message": {
        "content": json.dumps(model_json()) if content is None else content}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20}})


@pytest.fixture
def photo():
    return Photo("p1", "front", image_bytes())


def test_prepared_image_strips_metadata_and_orients():
    data, mime = prepare_image(image_bytes((2400, 1200)))
    with Image.open(BytesIO(data)) as image:
        assert image.size == (800, 1600)
        assert not image.getexif()
        assert not any(key in image.info for key in ("exif", "icc_profile", "comment"))
    assert mime == "image/jpeg"


def test_structured_request_is_claim_blind(photo, tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        return response()

    guard = SpendGuard(tmp_path / "spend.json", 1)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        observer = SparkObserver("secret", client=client, guard=guard)
        result = observer.observe([photo], ["chair"])
    assert result.ok and result.observations[0].count_for("chair").count == 2
    assert result.observations[0].photo_id == photo.id
    assert result.latency_ms >= 0
    assert "chair" in observation_prompt("front", ["chair"])
    assert list(inspect.signature(observer.observe).parameters) == ["photos", "count_nouns"]
    assert list(inspect.signature(observation_prompt).parameters) == ["slot", "count_nouns"]
    request = requests[0]
    body = json.loads(request.content)
    assert request.url.path == "/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer secret"
    assert "seller-claim-value-987654" not in request.content.decode()
    schema = observation_schema(["chair"])
    schema["additionalProperties"] = False
    for key in ("counts", "defects"):
        schema["properties"][key]["items"]["additionalProperties"] = False
    assert body["response_format"]["json_schema"] == {
        "name": "PhotoObservation", "schema": schema, "strict": True}
    url = body["messages"][0]["content"][1]["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
    with Image.open(BytesIO(base64.b64decode(url.split(",", 1)[1]))) as prepared:
        assert not prepared.getexif()
    assert guard.spent_usd == pytest.approx(0.00021)
    assert SpendGuard(guard.path, 1).spent_usd == guard.spent_usd
    assert json.loads(guard.path.read_text())["input_tokens"] == 100


@pytest.mark.parametrize("bad", ["not JSON", "{}", '[]',
                                 json.dumps({**model_json(), "usable": "true"}),
                                 json.dumps({**model_json(), "usability_issue": "unknown"})])
def test_invalid_response_retries_once(photo, tmp_path, bad):
    calls = []

    def handler(request):
        calls.append(request)
        return response(bad if len(calls) == 1 else None)

    guard = SpendGuard(tmp_path / "spend.json", 1)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = SparkObserver("key", client=client, guard=guard).observe([photo], ["chair"])
    assert result.ok and len(calls) == 2
    assert guard.spent_usd == pytest.approx(0.00042)


@pytest.mark.parametrize("failure,expected_calls", [("invalid", 2), ("http", 1), ("timeout", 1)])
def test_failures_return_no_observations(photo, failure, expected_calls):
    calls = []

    def handler(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(500) if failure == "http" else response("invalid")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = SparkObserver("key", client=client).observe([photo], ["chair"])
    assert not result.ok and not result.observations and result.error
    assert len(calls) == expected_calls


def test_budget_exceeded_sends_no_requests(photo, tmp_path):
    calls = []
    guard = SpendGuard(tmp_path / "spend.json", 0.009)
    with httpx.Client(transport=httpx.MockTransport(lambda r: calls.append(r))) as client:
        result = SparkObserver("key", client=client, guard=guard).observe([photo] * 3, ["chair"])
    assert not result.ok and "BudgetExceeded" in result.error
    assert not calls


def test_guard_reserves_across_threads_and_persists(tmp_path):
    guard = SpendGuard(tmp_path / "spend.json", 0.015)
    barrier = Barrier(3)

    def reserve(_):
        barrier.wait()
        try:
            guard.reserve(0.01)
            return True
        except BudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=3) as pool:
        assert sum(pool.map(reserve, range(3))) == 1
    with pytest.raises(BudgetExceeded):
        SpendGuard(guard.path, 0.015).reserve(0.01)


def test_local_has_no_auth_and_costs_zero(photo, tmp_path):
    def handler(request):
        assert "authorization" not in request.headers
        assert request.url.host == "127.0.0.1"
        return response()

    guard = SpendGuard(tmp_path / "spend.json", 0)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        observer = LocalObserver(client=client, guard=guard)
        assert observer.observe([photo], ["chair"]).ok
    assert observer.name == "muse-glimmer-30b (local)"
    assert observer.concurrency == 1 and guard.spent_usd == 0


def test_replay_uses_original_hash_and_never_returns_partial(photo, tmp_path):
    path = tmp_path / "replay.json"
    path.write_text(json.dumps({hashlib.sha256(photo.data).hexdigest(): model_json(),
                               "_meta": {"model": "muse-spark-1.3", "recorded_at": "2026-10-29"}}))
    observer = ReplayObserver(path)
    assert observer.name == "replay of muse-spark-1.3 recorded 2026-10-29"
    assert observer.observe([photo], ["chair"]).ok
    result = observer.observe([photo, Photo("unknown", "side", b"unknown")], ["chair"])
    assert not result.ok and not result.observations


def test_environment_selection(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("LOCAL_MODEL_URL", raising=False)
    with pytest.raises(ValueError):
        observer_from_env()
    monkeypatch.setenv("LOCAL_MODEL_URL", "http://localhost:1234/v1")
    assert isinstance(observer_from_env(), LocalObserver)
    monkeypatch.setenv("MODEL_API_KEY", "key")
    monkeypatch.setenv("SPEND_CAP_USD", "5")
    import app.observe
    monkeypatch.setattr(app.observe, "_guard", None)  # the guard is shared per process
    observer = observer_from_env()
    assert type(observer) is SparkObserver and observer.guard.cap_usd == 5


def test_cache_persists_shares_photos_and_invalidates(photo, tmp_path, monkeypatch):
    import app.observe as module
    calls = []
    with httpx.Client(transport=httpx.MockTransport(lambda r: (calls.append(r), response())[1])) as client:
        guard = SpendGuard(tmp_path / "spend.json", 1)
        observer = SparkObserver("key", client=client, guard=guard)
        assert observer.observe([photo] * 3, ["table", "chair"]).ok
        assert len(calls) == 1
        observer = SparkObserver("key", client=client, guard=SpendGuard(guard.path, 0))
        other = Photo("other-listing", "side", photo.data)
        result = observer.observe([other], ["chair", "table"])
        assert result.ok and result.observations[0].photo_id == other.id
        assert result.observations[0].slot == "side" and len(calls) == 1
        observer.guard.cap_usd = 1
        assert observer.observe([photo], ["chair"]).ok
        observer.model = "another-model"
        assert observer.observe([photo], ["chair"]).ok
        monkeypatch.setattr(module, "PROMPT_VERSION", module.PROMPT_VERSION + 1)
        assert observer.observe([photo], ["chair"]).ok
        assert observer.observe([Photo("new", "front", image_bytes((40, 30)))], ["chair"]).ok
        assert len(calls) == 5


def test_failed_observations_are_not_cached(photo, tmp_path):
    calls = []
    with httpx.Client(transport=httpx.MockTransport(
            lambda r: (calls.append(r), response("invalid"))[1])) as client:
        observer = SparkObserver("key", client=client, guard=SpendGuard(tmp_path / "spend.json", 1))
        assert not observer.observe([photo], ["chair"]).ok
        assert not observer.observe([photo], ["chair"]).ok
    assert len(calls) == 4


def test_daily_cap_persists_resets_and_keeps_total(tmp_path, monkeypatch):
    import app.observe as module
    monkeypatch.setattr(module, "utc_day", lambda: "2026-10-27")
    path = tmp_path / "spend.json"
    guard = SpendGuard(path, 0.03, daily_usd=0.02)
    guard.reserve(0.02)
    guard.record(10, 5, 0.02)
    with pytest.raises(BudgetExceeded, match="Daily"):
        SpendGuard(path, 0.03, daily_usd=0.02).reserve(0.001)
    monkeypatch.setattr(module, "utc_day", lambda: "2026-10-28")
    guard.reserve(0.01)
    guard.record(10, 5, 0.01)
    state = json.loads(path.read_text())
    assert state["day"] == "2026-10-28" and state["daily_spent_usd"] == 0.01
    assert guard.spent_usd == pytest.approx(0.03)
    with pytest.raises(BudgetExceeded, match="Spending cap"):
        guard.reserve(0.001)


def test_daily_reservations_shared_by_guard_instances(tmp_path, monkeypatch):
    import app.observe as module
    monkeypatch.setattr(module, "utc_day", lambda: "2026-10-27")
    path = tmp_path / "spend.json"
    guards = [SpendGuard(path, 1, daily_usd=0.015) for _ in range(3)]
    barrier = Barrier(3)

    def reserve(guard):
        barrier.wait()
        try:
            guard.reserve(0.01)
            return True
        except BudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=3) as pool:
        assert sum(pool.map(reserve, guards)) == 1
    monkeypatch.setattr(module, "utc_day", lambda: "2026-10-28")
    with pytest.raises(BudgetExceeded):
        SpendGuard(path, 1, daily_usd=0.015).reserve(0.01)


def test_old_spend_state_and_default_caps(tmp_path, monkeypatch):
    import app.observe as module
    path = tmp_path / "spend.json"
    path.write_text(json.dumps({"spent_usd": 0.1, "reserved_usd": 0,
                                "input_tokens": 100, "output_tokens": 20}))
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SPEND_CAP_USD", raising=False)
    monkeypatch.delenv("SPEND_DAILY_USD", raising=False)
    monkeypatch.setattr(module, "_guard", None)
    guard = module.shared_guard()
    assert guard.cap_usd == 10 and guard.daily_usd == 2 and guard.spent_usd == 0.1


def test_concurrent_checks_and_failed_calls_consume_quota(tmp_path, monkeypatch):
    import app.observe as module
    from app.store import Store
    store = Store(tmp_path)
    guard = SpendGuard(tmp_path / "spend.json", 1)
    monkeypatch.setenv("CHECKS_PER_LISTING_PER_DAY", "2")
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("unknown billing", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        observer = SparkObserver("key", client=client, guard=guard)

        def check(i):
            with module.listing_check(store, "listing"):
                return observer.observe([Photo(str(i), "front", image_bytes((30 + i, 20)))], ["chair"])

        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(check, range(6)))
        assert not any(r.ok for r in results)
        assert len(calls) == 2
        assert sum("CheckLimitExceeded" in r.error for r in results) == 4
        assert guard.spent_usd == pytest.approx(0.02)


def test_budget_rejection_does_not_consume_check_quota(photo, tmp_path):
    import app.observe as module
    from app.store import Store
    store = Store(tmp_path)
    with httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail("paid call"))) as client:
        observer = SparkObserver("key", client=client, guard=SpendGuard(tmp_path / "spend.json", 0))
        with module.listing_check(store, "listing"):
            assert not observer.observe([photo], ["chair"]).ok
    assert store.db.execute("SELECT * FROM paid_checks").fetchall() == []


def test_only_claim_extraction_turns_reasoning_down(photo, tmp_path):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        if "Split this" in bodies[-1]["messages"][0]["content"][0]["text"]:
            return response(json.dumps({"claims": []}))
        return response()

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        SparkObserver("secret", client=client).observe([photo], ["chair"])
        SparkObserver("secret", client=client).extract_claims("Chair", "2 chairs")
        LocalObserver(client=client).extract_claims("Chair", "2 chairs")
    assert [b.get("reasoning_effort") for b in bodies] == [None, "low", None]  # the evaluated observer is untouched
