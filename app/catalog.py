"""Closed catalogue of furniture claims a seller can make.

Each claim type says which photo slots it needs and whether photos can ever
support it. The model never sees claim values; it only gets neutral tasks
derived from claim *subjects* (e.g. "count the chairs", never "are there 4?").
"""
from dataclasses import dataclass
from enum import StrEnum

RULES_VERSION = "2026-10-27.1"


class Slot(StrEnum):
    FRONT = "front"
    SIDE = "side"
    DETAIL = "detail"


SLOT_PROMPTS = {
    Slot.FRONT: "Whole item from the front, filling most of the frame, good light.",
    Slot.SIDE: "Whole item from one side, including the legs or base.",
    Slot.DETAIL: "Close-up of the main surface (top or seat) where wear shows first.",
}


class ClaimType(StrEnum):
    COLOR = "color"
    PIECE_COUNT = "piece_count"
    NO_VISIBLE_DAMAGE = "no_visible_damage"
    UNCHECKABLE = "uncheckable"


REQUIRED_SLOTS = {
    ClaimType.COLOR: (Slot.FRONT,),
    ClaimType.PIECE_COUNT: (Slot.FRONT, Slot.SIDE),
    ClaimType.NO_VISIBLE_DAMAGE: (Slot.FRONT, Slot.SIDE, Slot.DETAIL),
    ClaimType.UNCHECKABLE: (),
}


@dataclass(frozen=True)
class Claim:
    id: str
    type: ClaimType
    text: str  # seller's own words, shown in the report
    subject: str = ""  # noun to count, e.g. "chair"; empty for other types
    value: str = ""  # claimed colour or count; never sent to the model

    @property
    def required_slots(self) -> tuple[Slot, ...]:
        return REQUIRED_SLOTS[self.type]

    def to_dict(self) -> dict:
        return {"id": self.id, "type": str(self.type), "text": self.text,
                "subject": self.subject, "value": self.value}

    @classmethod
    def from_dict(cls, d: dict) -> "Claim":
        return cls(id=d["id"], type=ClaimType(d["type"]), text=d["text"],
                   subject=d.get("subject", ""), value=str(d.get("value", "")))


def count_subjects(claims: list[Claim]) -> list[str]:
    """Nouns the observer is asked to count. Subjects only, never values."""
    return sorted({c.subject.strip().lower() for c in claims
                   if c.type == ClaimType.PIECE_COUNT and c.subject.strip()})


def required_slots(claims: list[Claim]) -> list[Slot]:
    return [s for s in Slot if any(s in c.required_slots for c in claims)]
