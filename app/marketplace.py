"""Deterministic, evidence-aware copy shared by seller, buyer demo and API."""
import re


def build_post(version, payload: dict, report_url: str) -> dict:
    """Use the checked version; callers expose this only while its report is active.

    Remove sentences containing a contradicted claim, ignoring case/whitespace.
    If a contradiction cannot be located, omit free-form description rather than
    guess whether it paraphrases the claim. This is deliberately not a language model.
    """
    title = version["title"]
    description = version["description"].strip()
    omitted = False  # the seller's description was left out: tell them, don't drop it silently
    lines = []
    for claim in payload["claims"]:
        verdict, text = claim["verdict"], claim["text"].strip()
        if verdict["status"] == "contradicted":
            pattern = re.compile(r"\s+".join(re.escape(w) for w in text.split()), re.I) if text else None
            if pattern and pattern.search(title):
                title = "Item for sale"
            if pattern and pattern.search(description):
                description = " ".join(s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", description)
                                       if not pattern.search(s))
            else:
                omitted, description = omitted or bool(description), ""
            detail = re.sub(r"^Seen:\s*", "", verdict["detail"].strip())
            # Do not reintroduce the seller's contradicted words through a detail.
            if detail and not (pattern and pattern.search(detail)):
                lines.append(f"Photos show: {detail}")
            else:
                lines.append("Photo check found a contradiction. See the evidence report for details.")
        elif verdict["status"] == "supported" and text:
            lines.append(f"✓ {text}")
        elif verdict["status"] == "inconclusive" and text:
            lines.append(f"Seller says: {text} (photos can't show this)")
    parts = [description] if description else []
    if payload.get("sample"):
        parts.insert(0, "SAMPLE · Not a real listing")
    if lines:
        parts.append("Photo-checked\n" + "\n".join(lines))
    parts.append(f"Evidence report: {report_url}")
    return {"title": title, "description": "\n\n".join(parts), "description_omitted": omitted,
            "photos": [f"{report_url}/photo/{slot}" for slot in ("front", "side", "detail")
                       if slot in payload["photos"]], "report_url": report_url}
