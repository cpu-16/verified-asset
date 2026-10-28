"""Optional SAM second opinions, with boxes in prepared-image pixel coordinates."""
import base64
from dataclasses import replace
import hashlib
import json
import re

import httpx

from .observation import PhotoObservation
from .observe import CheckLimitExceeded, Photo, SpendGuard, prepare_image
from .store import Store

Box = tuple[int, int, int, int]


def parse_boxes(text: str) -> list[Box]:
    """Read distinct object ids from the first frame, ignoring mask payloads."""
    if not text.strip():
        return []
    frames = list(re.finditer(r"<\d+f>", text))
    if not frames:
        raise ValueError("Missing SAM frame marker")
    frame = text[frames[0].end():frames[1].start() if len(frames) > 1 else len(text)]
    boxes = {}
    # Consume whole mask tokens: their payload may itself contain commas.
    record = re.compile(r"\s*(\d+)\s*<\|box;([^|]+)\|>\s*<\|mask;.*?\|>", re.DOTALL)
    position = 0
    while position < len(frame):
        if not frame[position:].strip():
            break
        match = record.match(frame, position)
        if match is None:
            raise ValueError("Malformed SAM record")
        fields = dict(part.split("=", 1) for part in match[2].split(";"))
        try:
            box = tuple(int(fields[key]) for key in ("x1", "y1", "x2", "y2"))
        except KeyError as exc:
            raise ValueError("Missing SAM box coordinate") from exc
        if min(box) < 0 or box[2] < box[0] or box[3] < box[1]:
            raise ValueError("Invalid SAM box coordinates")
        boxes.setdefault(int(match[1]), box)
        position = match.end()
        if frame[position:].strip():
            separator = re.match(r"\s*,", frame[position:])
            if separator is None:
                raise ValueError("Missing SAM record separator")
            position += separator.end()
    return list(boxes.values())


def _events(response: httpx.Response):
    """Decode SSE data fields, including multi-line events and a final EOF event."""
    data = []
    for line in response.iter_lines():
        if not line:
            if data:
                yield "\n".join(data)
                data = []
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
    if data:
        yield "\n".join(data)


class SamCounter:
    cost_usd = 2.50 / 1000

    def __init__(self, api_key: str, base_url: str = "https://api.meta.ai/v1",
                 timeout: float = 45.0, client: httpx.Client | None = None,
                 guard: SpendGuard | None = None):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = client
        self.guard = guard
        self.cache = Store(guard.path.parent) if guard else None

    def count(self, image_bytes: bytes, noun: str) -> int:
        return len(self.boxes(image_bytes, noun))

    def boxes(self, image_bytes: bytes, phrase: str) -> list[Box]:
        key = ["sam-3.1", hashlib.sha256(image_bytes).hexdigest(), phrase]
        call = lambda: self._boxes(image_bytes, phrase)
        boxes = self.cache.cached(key, call) if self.cache else call()
        return [tuple(box) for box in boxes]

    def _boxes(self, image_bytes: bytes, phrase: str) -> list[Box]:
        data, mime = prepare_image(image_bytes)
        body = {"model": "sam-3.1", "stream": True, "input": [{
            "role": "user", "content": [
                {"type": "input_text", "text": phrase},
                {"type": "input_image", "image_url":
                 f"data:{mime};base64,{base64.b64encode(data).decode()}"},
            ]}]}
        client = self.client or httpx.Client()
        reserved = False
        try:
            if self.guard:
                self.guard.reserve(self.cost_usd)
                reserved = True
            with client.stream("POST", f"{self.base_url}/responses", json=body,
                               headers={"Authorization": f"Bearer {self.api_key}",
                                        "Accept": "text/event-stream"}, timeout=self.timeout) as response:
                response.raise_for_status()
                chunks = []
                completed = False
                for data in _events(response):
                    if data == "[DONE]":
                        break
                    event = json.loads(data)
                    kind = event.get("type")
                    if kind == "response.output_text.delta":
                        chunks.append(event["delta"])
                    elif kind == "response.completed":
                        completed = True
                        break
                    elif kind in ("error", "response.failed", "response.incomplete"):
                        raise ValueError(f"SAM stream failed: {kind}")
                if not completed:
                    raise ValueError("SAM stream ended before response.completed")
            return parse_boxes("".join(chunks))
        finally:
            try:
                # Even interrupted requests may be billed for the submitted image.
                if self.guard and reserved:
                    self.guard.record(0, 0, self.cost_usd)
            finally:
                if self.client is None:
                    client.close()


def enrich(observations: list[PhotoObservation], photos: list[Photo],
           sam: SamCounter) -> list[PhotoObservation]:
    by_id = {p.id: p for p in photos}
    enriched = []
    for observation in observations:
        try:
            data = by_id[observation.photo_id].data
            counts = tuple(replace(c, sam_count=sam.count(data, c.noun)) for c in observation.counts)
            defects = []
            for defect in observation.defects:
                boxes = sam.boxes(data, defect.kind)
                defects.append(replace(defect, box=boxes[0] if boxes else None))
            enriched.append(replace(observation, counts=counts, defects=tuple(defects)))
        except CheckLimitExceeded:
            raise
        except Exception:
            # Enrichment is atomic per photo and never invalidates primary evidence.
            enriched.append(observation)
    return enriched
