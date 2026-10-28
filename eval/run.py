"""Score the labelled cases in cases.json against a photo observer.

    LOCAL_MODEL_URL=http://127.0.0.1:1234/v1 uv run python -m eval.run           # Glimmer, free
    MODEL_API_KEY=... uv run python -m eval.run [--direct]                        # Muse Spark, paid

Each photo is observed once, blind to every claim, and the raw answer is kept in
recordings/<model>.json, so a rerun only pays for photos it hasn't seen yet.
--direct adds the ablation: the same model sees the claim with the photos and judges it itself.
"""
import base64
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.adjudicate import adjudicate, capture_code_seen
from app.catalog import Claim, ClaimType
from app.observation import PhotoObservation
from app.observe import _strict_schema, observation_prompt, observer_from_env, prepare_image

HERE = Path(__file__).parent
SPEC = json.loads((HERE / "cases.json").read_text())
STATUSES = ["supported", "contradicted", "inconclusive"]
DIRECT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["status"],
                 "properties": {"status": {"type": "string", "enum": STATUSES}}}


def digest(name):
    return hashlib.sha256((HERE / "photos" / name).read_bytes()).hexdigest()


def image(name):
    data, mime = prepare_image((HERE / "photos" / name).read_bytes())
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(data).decode()}"}}


def direct_prompt(text, slots):
    return (f"A seller of a second-hand item claims: {json.dumps(text)}. The {', '.join(slots)} photos follow. "
            "Is the claim supported by the photos, contradicted by them, or inconclusive because the photos "
            "can't settle it? Return only JSON matching the schema.")


def record(observer, rec, save, run_direct):
    """Fill the recording with whatever is missing; returns how many model calls that took."""
    nouns, slot_of = {}, {}
    for case in SPEC["cases"]:
        for slot, name in SPEC["sets"][case["set"]].items():
            nouns.setdefault(name, set()).update({case["claim"]["subject"]} - {""})
            slot_of[name] = slot
    calls = 0
    with httpx.Client() as client:
        for name in sorted(nouns):
            if digest(name) not in rec:
                ns = sorted(nouns[name])
                rec[digest(name)] = observer._call(client, [
                    {"type": "text", "text": observation_prompt(slot_of[name], ns)}, image(name)],
                    _strict_schema(ns), "PhotoObservation")
                calls += 1
                save()
        direct = rec.setdefault("_direct", {})
        for case in SPEC["cases"] if run_direct else ():
            if case["id"] not in direct:
                photos = SPEC["sets"][case["set"]]
                content = [{"type": "text", "text": direct_prompt(case["claim"]["text"], list(photos))}]
                direct[case["id"]] = observer._call(client, content + [image(n) for n in photos.values()],
                                                    DIRECT_SCHEMA, "DirectVerdict")["status"]
                calls += 1
                save()
    return calls


def score(model, rec):
    direct = rec.get("_direct", {})
    lines = [f"# {model}", "", f"Recorded {rec['_meta']['recorded_at']}, observation prompt {rec['_meta']['prompt']}.", "",
             "| Case | Label | Seller's claim | Expected | Blind + rules | Direct |", "|---|---|---|---|---|---|"]
    tally = {"blind": [0, 0], "direct": [0, 0]}  # [correct, false reassurance] over the 12 labelled cases
    for case in SPEC["cases"]:
        photos = SPEC["sets"][case["set"]]
        obs = [PhotoObservation.from_model(name, slot, rec[digest(name)]) for slot, name in photos.items()]
        c = case["claim"]
        got = adjudicate([Claim("c1", ClaimType(c["type"]), c["text"], c["subject"], c["value"])], obs)[0]
        answers = {"blind": str(got.status), "direct": direct.get(case["id"], "")}
        if not case["label"].startswith("extra"):
            for k, a in answers.items():
                tally[k][0] += a == case["expect"]
                tally[k][1] += a == "supported" != case["expect"]
        mark = lambda a: f"**{a}**" if a and a != case["expect"] else a or "not run"
        lines.append(f"| {case['id']} | {case['label']} | {c['text']} | {case['expect']} | "
                     f"{mark(answers['blind'])} — {got.detail} | {mark(answers['direct'])} |")
    n = sum(not c["label"].startswith("extra") for c in SPEC["cases"])
    lines += ["", f"Blind + rules: {tally['blind'][0]}/{n} correct, {tally['blind'][1]} false reassurance "
              "(supported when it shouldn't be)."]
    if direct:
        lines.append(f"Direct: {tally['direct'][0]}/{n} correct, {tally['direct'][1]} false reassurance.")
    lines += ["", "| Front photo | Code | Should be read | Read |", "|---|---|---|---|"]
    for name, (code, legible) in SPEC["codes"].items():
        seen = bool(capture_code_seen(code, [PhotoObservation.from_model(name, "front", rec[digest(name)])]))
        lines.append(f"| {name} | {code} | {'yes' if legible else 'no'} | "
                     f"{'yes' if seen else 'no'}{'' if seen == legible else ' **wrong**'} |")
    return "\n".join(lines) + "\n"


def main():
    observer = observer_from_env()
    observer.timeout = max(observer.timeout, 240)
    path = HERE / "recordings" / f"{observer.model}.json"
    rec = json.loads(path.read_text()) if path.exists() else {}
    prompt = hashlib.sha256(observation_prompt("front", []).encode()).hexdigest()[:12]
    if rec.get("_meta", {}).get("prompt", prompt) != prompt:
        sys.exit(f"{path} was recorded with another observation prompt; move it away to record again")
    rec["_meta"] = {"model": observer.model, "prompt": prompt, "recorded_at": rec.get("_meta", {}).get(
        "recorded_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))}
    path.parent.mkdir(exist_ok=True)
    calls = record(observer, rec, lambda: path.write_text(json.dumps(rec, indent=1, sort_keys=True)),
                   "--direct" in sys.argv)
    report = score(observer.model, rec)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / f"{observer.model}.md").write_text(report)
    print(report)
    print(f"{calls} model calls this run; spend guard total ${observer.guard.spent_usd:.4f}" if observer.guard
          else f"{calls} model calls this run")


if __name__ == "__main__":
    main()
