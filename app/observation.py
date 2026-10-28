"""What an observer (Muse Spark, Glimmer, a recorded run) reports about ONE photo.

This is the contract between perception and the rules. Observers describe;
`adjudicate` decides. An observer that errors or breaks the schema produces a
failed check, never an `inconclusive` verdict.
"""
from dataclasses import dataclass, field

DEFECT_KINDS = ("scratch", "stain", "tear", "crack", "chip", "dent",
                "missing_part", "peeling", "burn", "other")
USABILITY_ISSUES = ("none", "blurry", "too_dark", "item_cut_off",
                    "wrong_item", "too_far")


@dataclass(frozen=True)
class Count:
    noun: str
    count: int
    all_instances_fully_visible: bool
    sam_count: int | None = None  # filled by the SAM 3.1 pass when it ran


@dataclass(frozen=True)
class Defect:
    kind: str
    location: str
    box: tuple[int, int, int, int] | None = None  # x1, y1, x2, y2 from SAM


@dataclass(frozen=True)
class PhotoObservation:
    photo_id: str
    slot: str
    usable: bool
    usability_issue: str = "none"
    item: str = ""
    dominant_colors: tuple[str, ...] = ()
    counts: tuple[Count, ...] = ()
    defects: tuple[Defect, ...] = ()
    visible_text: tuple[str, ...] = ()

    def count_for(self, noun: str) -> Count | None:
        noun = noun.strip().lower()
        return next((c for c in self.counts if c.noun.strip().lower() == noun), None)

    @classmethod
    def from_model(cls, photo_id: str, slot: str, d: dict) -> "PhotoObservation":
        """Build from the JSON an observer returned (see OBSERVATION_SCHEMA)."""
        return cls(
            photo_id=photo_id, slot=slot, usable=bool(d["usable"]),
            usability_issue=d.get("usability_issue", "none"),
            item=d.get("item", ""),
            dominant_colors=tuple(c.strip().lower() for c in d.get("dominant_colors", [])),
            counts=tuple(Count(noun=c["noun"], count=int(c["count"]),
                               all_instances_fully_visible=bool(c["all_instances_fully_visible"]))
                         for c in d.get("counts", [])),
            defects=tuple(Defect(kind=x["kind"], location=x.get("location", ""))
                          for x in d.get("defects", [])),
            visible_text=tuple(d.get("visible_text", [])),
        )

    def to_dict(self) -> dict:
        return {
            "photo_id": self.photo_id, "slot": self.slot, "usable": self.usable,
            "usability_issue": self.usability_issue, "item": self.item,
            "dominant_colors": list(self.dominant_colors),
            "counts": [c.__dict__ for c in self.counts],
            "defects": [{"kind": d.kind, "location": d.location,
                         "box": list(d.box) if d.box else None} for d in self.defects],
            "visible_text": list(self.visible_text),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PhotoObservation":
        return cls(
            photo_id=d["photo_id"], slot=d["slot"], usable=d["usable"],
            usability_issue=d.get("usability_issue", "none"), item=d.get("item", ""),
            dominant_colors=tuple(d.get("dominant_colors", [])),
            counts=tuple(Count(**c) for c in d.get("counts", [])),
            defects=tuple(Defect(kind=x["kind"], location=x["location"],
                                 box=tuple(x["box"]) if x.get("box") else None)
                          for x in d.get("defects", [])),
            visible_text=tuple(d.get("visible_text", [])),
        )


def observation_schema(count_nouns: list[str]) -> dict:
    """JSON schema sent with every observation request (structured output)."""
    return {
        "type": "object",
        "properties": {
            "usable": {"type": "boolean"},
            "usability_issue": {"type": "string", "enum": list(USABILITY_ISSUES)},
            "item": {"type": "string"},
            "dominant_colors": {"type": "array", "items": {"type": "string"}},
            "counts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "noun": {"type": "string", "enum": count_nouns or ["none"]},
                        "count": {"type": "integer"},
                        "all_instances_fully_visible": {"type": "boolean"},
                    },
                    "required": ["noun", "count", "all_instances_fully_visible"],
                },
            },
            "defects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": list(DEFECT_KINDS)},
                        "location": {"type": "string"},
                    },
                    "required": ["kind", "location"],
                },
            },
            "visible_text": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["usable", "usability_issue", "item", "dominant_colors",
                     "counts", "defects", "visible_text"],
    }


@dataclass
class CheckResult:
    """One observation run over a listing version's photos."""
    observer: str  # e.g. "muse-spark-1.3 (live)", "muse-glimmer-30b (local)", "replay"
    ok: bool
    observations: list[PhotoObservation] = field(default_factory=list)
    error: str = ""
    latency_ms: int = 0
