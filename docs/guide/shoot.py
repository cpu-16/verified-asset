"""Take the demo guide's screenshots from a running site and number the parts the guide talks about.

    python3 docs/guide/shoot.py [base url] [draft url]    (needs playwright with its browser, and pillow)

Uses only the sample listing, so it never calls a model and never spends. The optional draft url is the
seller's page of a "Film it instead" listing whose draft is already made; without it, 14-film is skipped.
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
        ctx = await b.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=DPR, reduced_motion="reduce")
        # The fixed Back/Next bar would sit on top of the content in a full-page shot; the guide points at the step tabs.
        await ctx.add_init_script("addEventListener('DOMContentLoaded', () => document.head.insertAdjacentHTML("
                                  "'beforeend', '<style>.wizard-actions{visibility:hidden!important}</style>'))")
        pg = await ctx.new_page()
        W = 1280

        async def step(name):  # the seller's page shows one step at a time; the hash picks it
            await pg.goto(f"{listing}#{name}", wait_until="networkidle")
            await pg.wait_for_timeout(300)

        async def until(sel):  # crop from the step tabs down to the bottom of `sel`
            top, end = await box(pg, ".wizard-bar"), await box(pg, sel)
            return (0, top[1] - 16, W, end[1] + end[3] + 24)

        # 1. Home
        await pg.goto(BASE + "/", wait_until="networkidle")
        raw = await shot(pg, "home")
        hero = await box(pg, ".hero")
        mark(raw, [(1, await box(pg, ".hero-copy .ctas button")), (2, await box(pg, ".hero-copy .ctas a")),
                   (3, await box(pg, ".stats-note a"))], (0, 0, W, hero[1] + hero[3]), "01-home")

        # 2. The sample's code step
        async with pg.expect_navigation():
            await pg.locator(".hero-copy .ctas button").click()
        listing = pg.url.split("#")[0]
        await step("code")
        raw = await shot(pg, "code")
        mark(raw, [(1, await box(pg, ".wizard-links")), (2, await box(pg, ".wizard-info summary")), (3, await box(pg, "#code .slip"))],
             await until("#code"), "02-code")

        # 3. Photos: the sample starts without its close-up
        await step("photos")
        raw = await shot(pg, "photos")
        mark(raw, [(1, await box(pg, "#photos .tile:nth-child(1)")), (2, await box(pg, "#photos .tile:nth-child(3)"))],
             await until("#photos"), "03-photos")

        # 4. The check running. The sample answers at once, so the form is kept from leaving the page
        # long enough to show what a seller sees during a live check.
        await step("check")
        await pg.evaluate("document.getElementById('check-form').addEventListener('submit', e => e.preventDefault())")
        await pg.locator("#check-form button[type=submit]").click()
        await pg.wait_for_timeout(2600)
        raw = await shot(pg, "checking")
        mark(raw, [(1, await box(pg, "#check .checking")), (2, await box(pg, "#check-form button[type=submit]"))],
             await until("#check"), "04-checking")
        await pg.reload(wait_until="networkidle")  # same page: a hash change alone would keep the button disabled
        async with pg.expect_navigation():
            await pg.locator("#check-form button[type=submit]").click()
        await pg.wait_for_load_state("networkidle")

        # 5. First result: two claims the photos can't settle, and the photo Muse Spark asks for
        raw = await shot(pg, "ask")
        mark(raw, [(1, await box(pg, ".verdict-summary")), (2, await box(pg, ".shot-ask .plan-thumb")),
                   (3, await box(pg, ".shot-ask .shot-text")), (4, await box(pg, ".shot-ask .reshoot button"))],
             await until("#check"), "05-ask")

        # 6. Add the close-up it asked for and check again
        async with pg.expect_navigation():
            await pg.locator(".shot-ask .reshoot button").click()
        await pg.wait_for_load_state("networkidle")
        async with pg.expect_navigation():
            await pg.locator("#check-form button[type=submit]").click()
        await pg.wait_for_load_state("networkidle")
        await pg.locator("#check .verdict.contradicted summary").click()
        raw = await shot(pg, "verdicts")
        mark(raw, [(1, await box(pg, "#check .verdict.contradicted")), (2, await box(pg, "#check .verdict.inconclusive"))],
             await until("#check"), "06-verdicts")

        # 7. Share
        await step("share")
        async with pg.expect_navigation():  # creating the link opens the report; the share block is back on the listing
            await pg.locator("#share button[type=submit]").first.click()
        report = pg.url.split("#")[0]
        await step("share")
        await pg.locator("#share details summary").click()
        raw = await shot(pg, "share")
        mark(raw, [(1, await box(pg, ".share")), (2, await box(pg, ".post-head")), (3, await box(pg, ".share-block .soft a")),
                   (4, await box(pg, ".share-block form button"))], await until("#share"), "07-share")

        # 8. The buyer's report
        await pg.set_viewport_size({"width": W, "height": 1180})  # the gallery is one screen tall
        await pg.goto(report, wait_until="networkidle")
        raw = await shot(pg, "report")
        fp = await box(pg, "details.fingerprint")
        mark(raw, [(1, await box(pg, ".validity")), (2, await box(pg, ".counts")), (3, await box(pg, ".panel .verdicts")),
                   (4, await box(pg, ".thumbs")), (5, fp)], (0, 0, W, fp[1] + fp[3] + 30), "08-report")

        # 9. The same report inside a mock listing
        await pg.set_viewport_size({"width": W, "height": 900})
        await pg.goto(report + "/listing", wait_until="networkidle")
        raw = await shot(pg, "buyer")
        card = await box(pg, ".evidence")
        mark(raw, [(1, await box(pg, ".demo")), (2, card)], (0, 0, W, card[1] + card[3] + 40), "09-buyer")

        # 10. Change a claim: 4 chairs becomes 6, then check again
        await step("check")
        await pg.locator("details.edit summary").click()
        await pg.locator("details.edit .claim-phrase").first.click()  # each claim shows as a phrase until tapped
        await pg.fill("details.edit input[name=text0]", "Set of 6 chairs")
        await pg.fill("details.edit input[name=value0]", "6")
        raw = await shot(pg, "edit")
        edit = await box(pg, "details.edit")
        mark(raw, [(1, await box(pg, "details.edit .claim-row")), (2, await box(pg, "details.edit .form-actions button"))],
             (0, edit[1] - 24, W, edit[1] + edit[3] + 24), "10-edit")
        async with pg.expect_navigation():
            await pg.locator("details.edit .form-actions button").click()
        await step("check")
        async with pg.expect_navigation():
            await pg.locator("#check-form button[type=submit]").click()
        await pg.wait_for_load_state("networkidle")
        raw = await shot(pg, "recheck")
        mark(raw, [(1, await box(pg, "#check .verdict.contradicted"))], await until("#check"), "11-recheck")

        # 11. The old report link after the edit
        await pg.goto(report, wait_until="networkidle")
        raw = await shot(pg, "void")
        card = await box(pg, ".state-card")
        mark(raw, [(1, await box(pg, ".state-card .callout"))], (0, 0, W, card[1] + card[3] + 40), "12-void")

        # 12. Starting your own report
        await pg.goto(BASE + "/new", wait_until="networkidle")
        await pg.fill("input[name=title]", "White dining table with 4 chairs")
        await pg.select_option(".category-picker", "Furniture")
        for name in ("Chairs", "Color", "No visible damage"):
            await pg.locator(".attribute-chips").get_by_role("button", name=name, exact=True).click()
        await pg.fill("input[name=value0]", "4")
        await pg.fill("input[name=value1]", "white")
        raw = await shot(pg, "new")
        actions = await box(pg, "#describe .form-actions")
        mark(raw, [(1, await box(pg, ".film-entry button")), (2, await box(pg, "input[name=title]")), (3, await box(pg, ".suggest button")),
                   (4, await box(pg, ".category-picker")), (5, await box(pg, ".attribute-chips")),
                   (6, await box(pg, ".claim-row:not([hidden])"))],
             (0, (await box(pg, ".steps"))[1] - 28, W, actions[1] + actions[3] + 28), "13-new")

        # 13. Filming instead (a draft made beforehand: making one calls the model)
        if len(sys.argv) > 2:
            await pg.goto(sys.argv[2], wait_until="networkidle")
            raw = await shot(pg, "film")
            card = await box(pg, "#draft")
            mark(raw, [(1, await box(pg, ".draft-shots")), (2, await box(pg, "#draft .alert")),
                       (3, await box(pg, "#draft .claim-row.suggested")), (4, await box(pg, "#draft-form .big"))],
                 (0, card[1] - 28, W, card[1] + card[3] + 28), "14-film")

        await b.close()
    for f in OUT.glob("raw-*.png"):
        f.unlink()


asyncio.run(main())
