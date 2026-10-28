from app.adjudicate import Status, adjudicate, capture_code_seen
from app.catalog import Claim, ClaimType
from app.observation import Count, Defect, PhotoObservation


def photo(slot, **kw):
    return PhotoObservation(photo_id=f"p-{slot}", slot=slot, usable=kw.pop("usable", True), **kw)


ALL_VIEWS = [photo("front", dominant_colors=("walnut", "black")), photo("side"), photo("detail")]


def one(claim, obs):
    [v] = adjudicate([claim], obs)
    return v


def test_uncheckable_is_never_supported_even_with_perfect_photos():
    v = one(Claim("c1", ClaimType.UNCHECKABLE, "The wood is very strong"), ALL_VIEWS)
    assert v.status == Status.INCONCLUSIVE and v.reason == "NOT_PHOTO_CHECKABLE"


def test_missing_required_view_is_inconclusive_with_a_retake_request():
    v = one(Claim("c1", ClaimType.NO_VISIBLE_DAMAGE, "No scratches"), ALL_VIEWS[:2])
    assert v.status == Status.INCONCLUSIVE and v.reason == "MISSING_VIEW"
    assert "detail" in v.request


def test_unusable_view_is_inconclusive_not_contradicted():
    obs = [photo("front", usable=False, usability_issue="blurry"), photo("side"), photo("detail")]
    v = one(Claim("c1", ClaimType.COLOR, "Brown", value="brown"), obs)
    assert v.status == Status.INCONCLUSIVE and v.reason == "UNUSABLE_VIEW"


def test_color_uses_families():
    assert one(Claim("c1", ClaimType.COLOR, "Brown", value="brown"), ALL_VIEWS).status == Status.SUPPORTED
    v = one(Claim("c1", ClaimType.COLOR, "White", value="white"), ALL_VIEWS)
    assert v.status == Status.CONTRADICTED and v.reason == "COLOR_NOT_SEEN"


def test_count_match_needs_full_visibility():
    chairs = Claim("c1", ClaimType.PIECE_COUNT, "4 chairs", subject="chair", value="4")
    hidden = [photo("front", counts=(Count("chair", 4, False),)), photo("side", counts=(Count("chair", 3, False),))]
    assert one(chairs, hidden).reason == "PARTLY_HIDDEN"
    full = [photo("front", counts=(Count("chair", 4, True),)), photo("side", counts=(Count("chair", 2, False),))]
    assert one(chairs, full).status == Status.SUPPORTED


def test_count_mismatch_when_everything_is_visible():
    chairs = Claim("c1", ClaimType.PIECE_COUNT, "6 chairs", subject="chair", value="6")
    obs = [photo("front", counts=(Count("chair", 4, True),)), photo("side", counts=(Count("chair", 4, True),))]
    v = one(chairs, obs)
    assert v.status == Status.CONTRADICTED and "4 chair" in v.detail


def test_counts_are_not_summed_across_photos():
    chairs = Claim("c1", ClaimType.PIECE_COUNT, "4 chairs", subject="chair", value="4")
    obs = [photo("front", counts=(Count("chair", 2, True),)), photo("side", counts=(Count("chair", 2, True),))]
    assert one(chairs, obs).status == Status.CONTRADICTED


def test_segmentation_disagreement_blocks_a_decision():
    chairs = Claim("c1", ClaimType.PIECE_COUNT, "4 chairs", subject="chair", value="4")
    obs = [photo("front", counts=(Count("chair", 4, True, sam_count=3),)), photo("side")]
    assert one(chairs, obs).reason == "OBSERVERS_DISAGREE"


def test_damage_seen_contradicts_no_damage_claim():
    obs = [photo("front"), photo("side"), photo("detail", defects=(Defect("scratch", "top, left edge"),))]
    v = one(Claim("c1", ClaimType.NO_VISIBLE_DAMAGE, "No scratches"), obs)
    assert v.status == Status.CONTRADICTED and v.photo_ids == ("p-detail",)


def test_same_photos_opposite_claims_flip_only_the_verdict():
    """The observation does not depend on the claim: that's the point of blind observing."""
    brown = one(Claim("c1", ClaimType.COLOR, "Brown", value="brown"), ALL_VIEWS)
    white = one(Claim("c1", ClaimType.COLOR, "White", value="white"), ALL_VIEWS)
    assert {brown.status, white.status} == {Status.SUPPORTED, Status.CONTRADICTED}


def test_capture_code():
    obs = [photo("front", visible_text=("7Q4K",)), photo("side", visible_text=("IKEA",))]
    assert capture_code_seen("7q4k", obs) == ["p-front"]
    assert capture_code_seen("ZZZZ", obs) == []


def test_capture_code_only_counts_on_a_usable_photo():
    readable = photo("front", visible_text=("6YA7",))
    dark = PhotoObservation(photo_id="front", slot="front", usable=False, usability_issue="too_dark",
                            visible_text=("6YA7",))
    assert capture_code_seen("6ya7", [readable]) == ["p-front"] and capture_code_seen("6YA7", [dark]) == []
