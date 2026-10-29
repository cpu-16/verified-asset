"""Social card for a report link: the preview WhatsApp, Messenger and Marketplace chat show when it is pasted."""
import io
import unicodedata

from PIL import Image, ImageDraw, ImageFont, ImageOps

W, H, PAD, PHOTO_W = 1200, 630, 48, 560
MAX_BYTES = 300_000
BG, INK, SOFT = "#0A0910", "#F4F3F8", "#A8A5B7"
YES, NO, MAYBE = "#5EE3A0", "#FF7D8E", "#FFC764"
MARKS = {"contradicted": (NO, "Contradicted"), "supported": (YES, "Supported"), "inconclusive": (MAYBE, "Can't tell")}
STATES = {"invalidated": "No longer valid", "revoked": "Withdrawn", "expired": "Expired"}
MAX_CLAIMS = 4


def font(size: int):
    return ImageFont.load_default(size=size)


def plain(text: str) -> str:
    """The default font has little beyond ASCII: 'Sillón' becomes 'Sillon', not a missing-glyph box."""
    # ponytail: non-Latin scripts drop out; ship an OFL font (Noto Sans) if such listings show up
    return " ".join(unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().split())


def fit(draw, text: str, f, width: int) -> str:
    """`text`, cut with an ellipsis if it is wider than `width` pixels."""
    if draw.textlength(text, font=f) <= width:
        return text
    while text and draw.textlength(text + "...", font=f) > width:
        text = text[:-1]
    return text.rstrip() + "..."


def wrap(draw, text: str, f, width: int, n: int) -> list[str]:
    """At most `n` lines; the last one ends in an ellipsis if text is left over."""
    words, out = text.split(), []
    while words and len(out) < n:
        line = words.pop(0)
        while words and draw.textlength(f"{line} {words[0]}", font=f) <= width:
            line += " " + words.pop(0)
        out.append(line)
    if words:
        out[-1] += " " + " ".join(words)
    return [fit(draw, line, f, width) for line in out]


def mark(draw, status: str, x: int, y: int, r: int = 20):
    """The verdict mark drawn as a shape: the default font has no check or cross glyphs."""
    draw.ellipse((x - r, y - r, x + r, y + r), fill=MARKS[status][0])
    if status == "supported":
        draw.line([(x - 9, y + 1), (x - 3, y + 8), (x + 10, y - 7)], fill=BG, width=5, joint="curve")
    elif status == "contradicted":
        draw.line([(x - 8, y - 8), (x + 8, y + 8)], fill=BG, width=5)
        draw.line([(x - 8, y + 8), (x + 8, y - 8)], fill=BG, width=5)
    else:
        draw.text((x, y + 1), "?", font=font(30), fill=BG, anchor="mm", stroke_width=1, stroke_fill=BG)


def render_card(store, view) -> bytes:
    """1200x630 JPEG: front photo and verdicts while active; only the state once it is not."""
    state, p = view["state"], view["payload"]
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    x = PAD
    if state == "active" and p["photos"].get("front"):  # photos go dark with the report, here too
        photo = Image.open(io.BytesIO(store.photo_bytes(p["photos"]["front"]))).convert("RGB")
        img.paste(ImageOps.fit(photo, (PHOTO_W, H)), (0, 0))
        x = PHOTO_W + PAD
    width = W - x - PAD

    kicker = ("SAMPLE - NOT A REAL LISTING", MAYBE) if p.get("sample") else ("EVIDENCE REPORT", SOFT)
    draw.text((x, PAD), kicker[0], font=font(22), fill=kicker[1])
    y = PAD + 40
    for line in wrap(draw, plain(p["title"]) or "Evidence report", font(44), width, 2):
        draw.text((x, y), line, font=font(44), fill=INK)
        y += 54
    y += 22

    if state == "active":
        claims = [c for s in MARKS for c in p["claims"] if c["verdict"]["status"] == s]
        for c in claims[:MAX_CLAIMS]:
            color, label = MARKS[c["verdict"]["status"]]
            mark(draw, c["verdict"]["status"], x + 20, y + 28)
            draw.text((x + 56, y), label, font=font(20), fill=color)
            draw.text((x + 56, y + 26), fit(draw, plain(c["text"]) or "See report for claim text", font(28), width - 56), font=font(28), fill=INK)
            y += 70
        if len(claims) > MAX_CLAIMS:
            draw.text((x + 56, y), f"+{len(claims) - MAX_CLAIMS} more in the report", font=font(20), fill=SOFT)
    else:
        color = MAYBE if state == "expired" else NO
        draw.text((x, y + 10), STATES.get(state, state.capitalize()), font=font(76), fill=color,
                  stroke_width=1, stroke_fill=color)
        draw.text((x, y + 116), "This link no longer vouches for the listing.", font=font(30), fill=INK)
        draw.text((x, y + 158), "Ask the seller for a new report.", font=font(30), fill=SOFT)

    code = f"{view['digest'][:4]} {view['digest'][4:8]}".upper()
    draw.text((x, H - PAD - 32), f"Report code {code}", font=font(22), fill=INK, anchor="ls")
    draw.text((x, H - PAD), "verified.adwentech.com", font=font(22), fill=SOFT, anchor="ls")

    for quality in (85, 70, 55, 40, 25, 10):
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality, optimize=True)
        if buf.tell() < MAX_BYTES:
            break
    return buf.getvalue()
