"""Closed catalogue of second-hand item claims a seller can make.

Each claim type says which photo slots it needs and whether photos can ever
support it. The model never sees claim values; it only gets neutral tasks
derived from claim *subjects* (e.g. "count the chairs", never "are there 4?").
"""
from dataclasses import dataclass
import re
from enum import StrEnum

RULES_VERSION = "2026-10-28.2"


class Slot(StrEnum):
    FRONT = "front"
    SIDE = "side"
    DETAIL = "detail"


SLOT_PROMPTS = {
    Slot.FRONT: "Whole item from the front, filling most of the frame, good light.",
    Slot.SIDE: "Whole item from one side, including its base or edges.",
    Slot.DETAIL: "Close-up of where wear shows first, or of the part or label you describe.",
}


class ClaimType(StrEnum):
    COLOR = "color"
    PIECE_COUNT = "piece_count"
    NO_VISIBLE_DAMAGE = "no_visible_damage"
    PART_NO_DAMAGE = "part_no_damage"
    LABEL_TEXT = "label_text"
    UNCHECKABLE = "uncheckable"


REQUIRED_SLOTS = {
    ClaimType.COLOR: (Slot.FRONT,),
    ClaimType.PIECE_COUNT: (Slot.FRONT, Slot.SIDE),
    ClaimType.NO_VISIBLE_DAMAGE: (Slot.FRONT, Slot.SIDE, Slot.DETAIL),
    ClaimType.PART_NO_DAMAGE: (Slot.DETAIL,),
    ClaimType.LABEL_TEXT: (Slot.DETAIL,),
    ClaimType.UNCHECKABLE: (),
}


@dataclass(frozen=True)
class Claim:
    id: str
    type: ClaimType
    text: str  # seller's own words, shown in the report
    subject: str = ""  # noun to count, e.g. "chair"; empty for other types
    value: str = ""  # claimed colour or count; never sent to the model
    by: str = ""  # "" = the seller wrote it; "video" = Muse Spark drafted it from the seller's video

    @property
    def required_slots(self) -> tuple[Slot, ...]:
        return REQUIRED_SLOTS[self.type]

    def to_dict(self) -> dict:
        d = {"id": self.id, "type": str(self.type), "text": self.text,
             "subject": self.subject, "value": self.value}
        return {**d, "by": self.by} if self.by else d  # seller-written claims keep their old shape

    @classmethod
    def from_dict(cls, d: dict) -> "Claim":
        return cls(id=d["id"], type=ClaimType(d["type"]), text=d["text"],
                   subject=d.get("subject", ""), value=str(d.get("value", "")), by=d.get("by", ""))


SUBJECT = re.compile(r"[a-z]+(?: [a-z]+){0,2}")  # the only seller text the observer ever sees


def count_subjects(claims: list[Claim]) -> list[str]:
    """Nouns the observer is asked to count. Subjects only, never values."""
    return sorted({c.subject.strip().lower() for c in claims
                   if c.type in (ClaimType.PIECE_COUNT, ClaimType.PART_NO_DAMAGE) and c.subject.strip()})


def required_slots(claims: list[Claim]) -> list[Slot]:
    return [s for s in Slot if any(s in c.required_slots for c in claims)]


# Fixed UI suggestions. No inference, retrieval or model call.
def attribute(label, rule, subject="", value=""):
    return dict(label=label, type=str(rule), subject=subject, value=value)


COMMON_ATTRIBUTES = [
    attribute("Color", ClaimType.COLOR),
    attribute("No visible damage", ClaimType.NO_VISIBLE_DAMAGE),
    attribute("Label reads", ClaimType.LABEL_TEXT),
]
CATEGORIES = {
    "Furniture": [attribute("Chairs", ClaimType.PIECE_COUNT, "chair"),
                  attribute("Seat cushions", ClaimType.PIECE_COUNT, "seat cushion"),
                  attribute("Upholstery has no visible damage", ClaimType.PART_NO_DAMAGE, "upholstery")],
    "Phones & tablets": [attribute("Includes charger", ClaimType.PIECE_COUNT, "charger", "1"),
                         attribute("Screen has no visible damage", ClaimType.PART_NO_DAMAGE, "screen")],
    "Electronics & gaming": [attribute("Controllers", ClaimType.PIECE_COUNT, "controller"),
                             attribute("Includes cable", ClaimType.PIECE_COUNT, "cable", "1"),
                             attribute("Screen has no visible damage", ClaimType.PART_NO_DAMAGE, "screen")],
    "Clothing & shoes": [attribute("Shoes (individual shoes)", ClaimType.PIECE_COUNT, "shoe"),
                         attribute("Shirts", ClaimType.PIECE_COUNT, "shirt"),
                         attribute("Sole has no visible damage", ClaimType.PART_NO_DAMAGE, "sole")],
    "Kitchen & home": [attribute("Plates", ClaimType.PIECE_COUNT, "plate"),
                       attribute("Cups", ClaimType.PIECE_COUNT, "cup"),
                       attribute("Handle has no visible damage", ClaimType.PART_NO_DAMAGE, "handle")],
}
CATEGORIES = {name: attrs + COMMON_ATTRIBUTES for name, attrs in CATEGORIES.items()}
