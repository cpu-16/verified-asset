"""Deterministic rules: claims + observations -> verdicts.

The model never decides. Defaults lean to `inconclusive`: a claim is only
`supported` when every required view is usable and the observation positively
matches. Pure functions, no I/O.
"""
from dataclasses import dataclass
from enum import StrEnum

from .catalog import SLOT_PROMPTS, Claim, ClaimType, Slot
from .observation import PhotoObservation


class Status(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class Verdict:
    claim_id: str
    status: Status
    reason: str  # stable code, see REASONS
    detail: str  # one human sentence for the report
    photo_ids: tuple[str, ...] = ()
    request: str = ""  # what photo would resolve an inconclusive verdict

    def to_dict(self) -> dict:
        return {"claim_id": self.claim_id, "status": str(self.status), "reason": self.reason,
                "detail": self.detail, "photo_ids": list(self.photo_ids), "request": self.request}


REASONS = {
    "NOT_PHOTO_CHECKABLE": "Photos cannot show this (strength, age, function, authenticity...).",
    "MISSING_VIEW": "A required photo is missing.",
    "UNUSABLE_VIEW": "A required photo is too blurry, dark or cut off.",
    "COLOR_SEEN": "The claimed colour is visible.",
    "COLOR_NOT_SEEN": "A different colour is visible.",
    "COUNT_MATCH": "The claimed number of pieces is visible.",
    "COUNT_MISMATCH": "A different number of pieces is fully visible.",
    "PARTLY_HIDDEN": "Some pieces may be hidden, so the count cannot be confirmed.",
    "OBSERVERS_DISAGREE": "The two observers counted differently.",
    "DAMAGE_SEEN": "Visible damage was observed.",
    "NO_DAMAGE_SEEN": "No damage is visible in the required photos.",
}

COLOR_FAMILIES = {
    "white": {"white", "ivory", "cream", "off-white", "off white"},
    "black": {"black", "ebony", "jet"},
    "gray": {"gray", "grey", "charcoal", "silver", "slate"},
    "brown": {"brown", "walnut", "chocolate", "espresso", "mahogany", "chestnut", "cognac"},
    "beige": {"beige", "tan", "khaki", "sand", "taupe", "camel"},
    "blue": {"blue", "navy", "teal", "turquoise"},
    "green": {"green", "olive", "sage", "emerald"},
    "red": {"red", "burgundy", "maroon", "wine"},
    "yellow": {"yellow", "mustard", "gold"},
    "orange": {"orange", "rust", "terracotta"},
    "pink": {"pink", "blush", "rose"},
    "purple": {"purple", "violet", "lilac", "plum"},
}


def color_family(name: str) -> str:
    name = name.strip().lower()
    for family, members in COLOR_FAMILIES.items():
        if name in members:
            return family
    return name  # unknown colours only match themselves


def _views(claim: Claim, obs: list[PhotoObservation]) -> tuple[list[PhotoObservation], Verdict | None]:
    """Required views for a claim, or an inconclusive verdict if any is missing/unusable."""
    by_slot = {o.slot: o for o in obs}
    views = []
    for slot in claim.required_slots:
        o = by_slot.get(str(slot))
        if o is None:
            return [], _inconclusive(claim, "MISSING_VIEW", slot)
        if not o.usable:
            return [], _inconclusive(claim, "UNUSABLE_VIEW", slot, (o.photo_id,), o.usability_issue)
        views.append(o)
    return views, None


def _inconclusive(claim, reason, slot: Slot | None = None, photo_ids=(), extra="") -> Verdict:
    detail = REASONS[reason] + (f" ({extra.replace('_', ' ')})" if extra and extra != "none" else "")
    request = f"Retake the {slot} photo: {SLOT_PROMPTS[slot]}" if slot else ""
    return Verdict(claim.id, Status.INCONCLUSIVE, reason, detail, tuple(photo_ids), request)


def _color(claim: Claim, views: list[PhotoObservation]) -> Verdict:
    claimed = color_family(claim.value)
    seen = {color_family(c) for o in views for c in o.dominant_colors}
    ids = tuple(o.photo_id for o in views)
    if claimed in seen:
        return Verdict(claim.id, Status.SUPPORTED, "COLOR_SEEN",
                       f"Observed colours: {', '.join(sorted(seen))}.", ids)
    if seen:
        return Verdict(claim.id, Status.CONTRADICTED, "COLOR_NOT_SEEN",
                       f"Observed colours: {', '.join(sorted(seen))}; not {claim.value}.", ids)
    return _inconclusive(claim, "UNUSABLE_VIEW", Slot.FRONT, ids, "no colour observed")


def _count(claim: Claim, views: list[PhotoObservation]) -> Verdict:
    try:
        claimed = int(claim.value)
    except ValueError:
        return _inconclusive(claim, "NOT_PHOTO_CHECKABLE", extra="count is not a number")
    counts = [(o, o.count_for(claim.subject)) for o in views]
    counts = [(o, c) for o, c in counts if c is not None]
    if not counts:
        return _inconclusive(claim, "PARTLY_HIDDEN", Slot.FRONT)
    for o, c in counts:  # a second observer (SAM) that disagrees blocks any decision
        if c.sam_count is not None and c.sam_count != c.count:
            return Verdict(claim.id, Status.INCONCLUSIVE, "OBSERVERS_DISAGREE",
                           f"{o.slot}: model counted {c.count}, segmentation found {c.sam_count}.",
                           (o.photo_id,), f"Retake the {o.slot} photo with every {claim.subject} in view.")
    # Never add counts across photos: the same piece shows up in several views.
    full = [(o, c) for o, c in counts if c.all_instances_fully_visible]
    if any(c.count == claimed for _, c in full):
        o = next(o for o, c in full if c.count == claimed)
        return Verdict(claim.id, Status.SUPPORTED, "COUNT_MATCH",
                       f"{claimed} {claim.subject}(s) fully visible in the {o.slot} photo.", (o.photo_id,))
    if full:
        o, c = max(full, key=lambda oc: oc[1].count)
        return Verdict(claim.id, Status.CONTRADICTED, "COUNT_MISMATCH",
                       f"{c.count} {claim.subject}(s) fully visible in the {o.slot} photo, not {claimed}.",
                       (o.photo_id,))
    o, c = max(counts, key=lambda oc: oc[1].count)
    return Verdict(claim.id, Status.INCONCLUSIVE, "PARTLY_HIDDEN",
                   f"Up to {c.count} {claim.subject}(s) visible, some may be hidden.", (o.photo_id,),
                   f"Take a photo where all {claimed} {claim.subject}(s) are fully visible.")


def _damage(claim: Claim, views: list[PhotoObservation]) -> Verdict:
    hits = [(o, d) for o in views for d in o.defects]
    if hits:
        desc = "; ".join(f"{d.kind} ({d.location}, {o.slot} photo)" for o, d in hits)
        return Verdict(claim.id, Status.CONTRADICTED, "DAMAGE_SEEN", f"Observed: {desc}.",
                       tuple(dict.fromkeys(o.photo_id for o, _ in hits)))
    return Verdict(claim.id, Status.SUPPORTED, "NO_DAMAGE_SEEN",
                   "No damage visible in the front, side and close-up photos, as photographed.",
                   tuple(o.photo_id for o in views))


def adjudicate(claims: list[Claim], obs: list[PhotoObservation]) -> list[Verdict]:
    verdicts = []
    for claim in claims:
        if claim.type == ClaimType.UNCHECKABLE:
            verdicts.append(Verdict(claim.id, Status.INCONCLUSIVE, "NOT_PHOTO_CHECKABLE",
                                    REASONS["NOT_PHOTO_CHECKABLE"]))
            continue
        views, blocked = _views(claim, obs)
        if blocked:
            verdicts.append(blocked)
            continue
        rule = {ClaimType.COLOR: _color, ClaimType.PIECE_COUNT: _count,
                ClaimType.NO_VISIBLE_DAMAGE: _damage}[claim.type]
        verdicts.append(rule(claim, views))
    return verdicts


def capture_code_seen(code: str, obs: list[PhotoObservation]) -> list[str]:
    """Photo ids where the one-time capture code written on paper is legible."""
    want = code.strip().upper()
    return [o.photo_id for o in obs
            if any(want == t.strip().upper().replace(" ", "") for t in o.visible_text)]
