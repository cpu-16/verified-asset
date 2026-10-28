"""Take the demo guide's screenshots from a running site and number the parts the guide talks about.

    python3 docs/guide/shoot.py [base url] [draft url]    (needs playwright with its browser, and pillow)

Uses only the sample listing, so it never calls a model and never spends. The optional draft url is the
seller's page of a "Film it instead" listing whose draft is already made; without it, 11-film is skipped.
"""
import asyncio
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from playwright.async_api import async_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://verified.adwentech.com").rstrip("/")
OUT = Path(__file__).parent
DPR = 2
RING, DOT = (255, 255, 255), (124, 77, 255)
FONT = ImageFont.truetype("/usr/share/fonts/google-noto-vf/NotoSans[wght].ttf", 30)


async def box(pg, sel):
    return await pg.locator(sel).first.evaluate(
        "e => { const r = e.getBoundingClientRect(); return [r.x, r.y + scrollY, r.width, r.height]; }")


def mark(png, marks, crop, name, width=1100):
    im = Image.open(png).convert("RGB")
    d = ImageDraw.Draw(im)
    for n, (x, y, w, h) in marks:
        x, y, w, h = (v * DPR for v in (x, y, w, h))
        d.rounded_rectangle([x - 8, y - 8, x + w + 8, y + h + 8], radius=18, outline=RING, width=5)
        cx, cy, r = x - 6, y - 6, 24
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=DOT, outline=RING, width=4)
        d.text((cx, cy), str(n), fill=RING, font=FONT, anchor="mm")
    x0, y0, x1, y1 = (v * DPR for v in crop)
    im = im.crop((max(0, x0), max(0, y0), min(im.width, x1), min(im.height, y1)))
    im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    im.save(OUT / f"{name}.webp", quality=82)
    print(name, im.size)


async def shot(pg, name):
    path = OUT / f"raw-{name}.png"
    await pg.evaluate("scrollTo(0, 0)")  # sticky header and rail otherwise land mid-page in a full-page shot
    await pg.wait_for_timeout(300)
    await pg.screenshot(path=str(path), full_page=True)
    return path


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await (await b.new_context(viewport={"width": 1280, "height": 860}, device_scale_factor=DPR,
                                        reduced_motion="reduce")).new_page()
        W = 1280

        # 1. Home
        await pg.goto(BASE + "/", wait_until="networkidle")
        raw = await shot(pg, "home")
        hero = await box(pg, ".hero")
        mark(raw, [(1, await box(pg, ".hero-copy .ctas button")), (2, await box(pg, ".hero-copy .ctas a")),
                   (3, await box(pg, ".stats-note a"))], (0, 0, W, hero[1] + hero[3]), "01-home")

        # 2. The sample listing, before any check
        async with pg.expect_navigation():
            await pg.locator(".hero-copy .ctas button").click()
        await pg.wait_for_load_state("networkidle")
        listing = pg.url
        raw = await shot(pg, "listing")
        photos = await box(pg, "#photos")
        mark(raw, [(1, await box(pg, ".alert.sample")), (2, await box(pg, ".progress")), (3, await box(pg, "#code .slip")),
                   (4, await box(pg, "#photos .tiles"))], (0, (await box(pg, ".alert.sample"))[1] - 24, W, photos[1] + photos[3] + 24),
             "02-listing")

        # 3. The check running. The sample answers at once, so the form is kept from leaving the page
        # long enough to show what a seller sees during a live check.
        await pg.evaluate("document.getElementById('check-form').addEventListener('submit', e => e.preventDefault())")
        await pg.locator("#check-form button").click()
        await pg.wait_for_timeout(2600)
        raw = await shot(pg, "checking")
        check = await box(pg, "#check")
        mark(raw, [(1, await box(pg, "#check .checking")), (2, await box(pg, "#check-form button"))],
             (0, check[1] - 24, W, check[1] + check[3] + 24), "03-checking")
        await pg.goto(listing, wait_until="networkidle")
        async with pg.expect_navigation():
            await pg.locator("#check-form button").click()
        await pg.wait_for_load_state("networkidle")

        # 4. Verdicts, and the close-up they point to (the sample has no SAM boxes: it replays Muse Spark only)
        raw = await shot(pg, "checked")
        photos, check = await box(pg, "#photos"), await box(pg, "#check")
        mark(raw, [(1, await box(pg, ".tile:nth-child(3) img")), (2, await box(pg, "#check .verdicts")),
                   (3, await box(pg, "#check .form-actions p"))], (0, photos[1] - 24, W, check[1] + check[3] + 24),
             "04-verdicts")

        # 5. Share
        async with pg.expect_navigation():  # creating the link opens the report; the share block is back on the listing
            await pg.locator("#share button[type=submit]").first.click()
        report = pg.url
        await pg.goto(listing, wait_until="networkidle")
        raw = await shot(pg, "share")
        share = await box(pg, "#share")
        mark(raw, [(1, await box(pg, ".share a")), (2, await box(pg, ".share button")),
                   (3, await box(pg, ".share-block form button"))], (0, share[1] - 24, W, share[1] + share[3] + 24),
             "05-share")

        # 6. The buyer's report
        await pg.set_viewport_size({"width": W, "height": 1180})  # the gallery is one screen tall
        await pg.goto(report, wait_until="networkidle")
        raw = await shot(pg, "report")
        mark(raw, [(1, await box(pg, ".validity")), (2, await box(pg, ".counts")), (3, await box(pg, ".panel .verdicts")),
                   (4, await box(pg, ".thumbs")), (5, await box(pg, "details.fingerprint"))],
             (0, 0, W, (await box(pg, "details.fingerprint"))[1] + (await box(pg, "details.fingerprint"))[3] + 30),
             "06-report")
        await pg.set_viewport_size({"width": W, "height": 860})

        # 7. Change a claim: 4 chairs becomes 6, then check again
        await pg.goto(listing, wait_until="networkidle")
        await pg.locator("details.edit summary").click()
        await pg.fill("details.edit input[name=text0]", "Set of 6 chairs")
        await pg.fill("details.edit input[name=value0]", "6")
        raw = await shot(pg, "edit")
        edit = await box(pg, "details.edit")
        mark(raw, [(1, await box(pg, "details.edit .claim-row")), (2, await box(pg, "details.edit .form-actions button"))],
             (0, edit[1] - 24, W, edit[1] + edit[3] + 24), "07-edit")
        async with pg.expect_navigation():
            await pg.locator("details.edit .form-actions button").click()
        await pg.wait_for_load_state("networkidle")
        async with pg.expect_navigation():
            await pg.locator("#check-form button").click()
        await pg.wait_for_load_state("networkidle")
        raw = await shot(pg, "recheck")
        check = await box(pg, "#check")
        mark(raw, [(1, await box(pg, "#check .verdict.contradicted"))], (0, check[1] - 24, W, check[1] + check[3] + 24),
             "08-recheck")

        # 8. The old report link after the edit
        await pg.goto(report, wait_until="networkidle")
        raw = await shot(pg, "void")
        card = await box(pg, ".state-card")
        mark(raw, [(1, await box(pg, ".state-card .callout"))], (0, 0, W, card[1] + card[3] + 40), "09-void")

        # 9. Starting your own report
        await pg.goto(BASE + "/new", wait_until="networkidle")
        await pg.fill("input[name=title]", "Oak bookshelf")
        raw = await shot(pg, "new")
        rows = await box(pg, ".claim-rows")
        mark(raw, [(1, await box(pg, "input[name=title]")), (2, await box(pg, ".claim-row select")),
                   (3, await box(pg, ".claim-row .text")), (4, await box(pg, ".claim-row .what")),
                   (5, await box(pg, ".claim-row .value")), (6, await box(pg, ".suggest button")),
                   (7, await box(pg, ".film-entry button"))],
             (0, (await box(pg, ".steps"))[1] - 28, W, rows[1] + 300), "10-new")

        # 10. Filming instead (a draft made beforehand: making one calls the model)
        if len(sys.argv) > 2:
            await pg.goto(sys.argv[2], wait_until="networkidle")
            raw = await shot(pg, "film")
            card = await box(pg, "#draft")
            mark(raw, [(1, await box(pg, ".draft-shots")), (2, await box(pg, "#draft .alert")),
                       (3, await box(pg, "#draft .claim-row.suggested")), (4, await box(pg, "#draft-form .big"))],
                 (0, card[1] - 28, W, card[1] + card[3] + 28), "11-film")

        await b.close()
    for f in OUT.glob("raw-*.png"):
        f.unlink()


asyncio.run(main())
