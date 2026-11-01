"""Make the README's hero.jpg and walkthrough.gif from a running site.

    python3 docs/media/make.py [base url]    (needs playwright with its browser, pillow and ffmpeg)

Uses only the sample listing, so it never calls a model and never spends.
"""
import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.async_api import async_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://verified.adwentech.com").rstrip("/")
OUT = Path(__file__).parent
HIDE_BAR = "<style>.wizard-actions{visibility:hidden!important}</style>"
CAPTION = """(([n, text]) => {
  document.querySelector('.wizard-actions')?.style.setProperty('visibility', 'hidden');
  const c = document.createElement('div');
  c.style.cssText = 'position:fixed;left:24px;bottom:22px;z-index:99;display:flex;align-items:center;gap:12px;'
    + 'padding:10px 20px 10px 10px;border-radius:999px;background:#6d3df5;color:#fff;font:600 19px/1.2 var(--sans, sans-serif);'
    + 'box-shadow:0 10px 30px rgba(0,0,0,.45)';
  c.innerHTML = '<b style="display:grid;place-items:center;width:30px;height:30px;border-radius:50%;background:#fff;color:#6d3df5">'
    + n + '</b>' + text;
  document.body.appendChild(c);
})"""

HERO = """<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500&display=swap" rel="stylesheet">
<style>
  body { margin: 0; width: 1200px; height: 655px; overflow: hidden; font-family: 'DM Sans', sans-serif;
         background: radial-gradient(900px 520px at 78% 0%, rgba(124,77,255,.32), transparent 70%),
                     radial-gradient(700px 420px at 0% 100%, rgba(63,224,198,.16), transparent 70%), #08070c; }
  .browser { position: absolute; left: 364px; top: 60px; width: 800px; border-radius: 14px; overflow: hidden;
             background: #15131c; box-shadow: 0 40px 90px rgba(0,0,0,.6), 0 0 0 1px rgba(255,255,255,.08); }
  .bar { height: 34px; display: flex; align-items: center; gap: 7px; padding: 0 14px; background: #1c1a24; }
  .bar i { width: 10px; height: 10px; border-radius: 50%; background: #3a3746; }
  .bar span { margin-left: 18px; flex: 0 0 320px; padding: 4px 14px; border-radius: 99px; background: #100e16;
              color: #b9b4c8; font-size: 12px; }
  .browser img { display: block; width: 100%; }
  .phone { position: absolute; left: 44px; top: 34px; width: 286px; height: 588px; padding: 9px; box-sizing: border-box;
           border-radius: 46px; background: #121117; box-shadow: 0 40px 80px rgba(0,0,0,.7), 0 0 0 1.5px rgba(255,255,255,.12) inset; }
  .phone img { display: block; width: 100%; height: 100%; object-fit: cover; object-position: top; border-radius: 37px; }
</style></head><body>
<div class="browser"><div class="bar"><i></i><i></i><i></i><span>verified.adwentech.com</span></div><img src="desk.png"></div>
<div class="phone"><img src="phone.png"></div>
</body></html>"""


async def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        async with async_playwright() as p:
            b = await p.chromium.launch()

            # Hero: the home page on a laptop, and on a phone the photo Muse Spark asks the seller for
            desk = await (await b.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)).new_page()
            await desk.goto(BASE + "/", wait_until="networkidle")
            await desk.wait_for_timeout(2500)
            await desk.screenshot(path=str(tmp / "desk.png"))
            phone_ctx = await b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True, has_touch=True)
            phone = await phone_ctx.new_page()
            await phone.goto(BASE + "/", wait_until="networkidle")
            async with phone.expect_navigation():
                await phone.locator(".hero-copy .ctas button").click()
            async with phone.expect_navigation():
                await phone.locator("#check-form button[type=submit]").click()
            await phone.wait_for_load_state("networkidle")
            await phone.evaluate("scrollTo(0, 0)")
            await phone.wait_for_timeout(600)
            await phone.screenshot(path=str(tmp / "phone.png"))
            (tmp / "hero.html").write_text(HERO)
            comp = await (await b.new_context(viewport={"width": 1200, "height": 655}, device_scale_factor=2)).new_page()
            await comp.goto((tmp / "hero.html").as_uri(), wait_until="networkidle")
            await comp.screenshot(path=str(OUT / "hero.jpg"), type="jpeg", quality=88)

            # Walkthrough: one captioned frame per step of the sample
            ctx = await b.new_context(viewport={"width": 1280, "height": 800}, reduced_motion="reduce")
            await ctx.add_init_script(f"addEventListener('DOMContentLoaded', () => document.head.insertAdjacentHTML('beforeend', '{HIDE_BAR}'))")
            pg = await ctx.new_page()
            frames = []

            async def frame(text):
                await pg.wait_for_timeout(400)
                await pg.evaluate(CAPTION, [len(frames) + 1, text])
                path = tmp / f"f{len(frames)}.png"
                await pg.screenshot(path=str(path))
                frames.append(path)

            async def go(url):
                await pg.goto(url, wait_until="networkidle")

            await go(BASE + "/")
            await frame("Sellers back up what their listing claims")
            async with pg.expect_navigation():
                await pg.locator(".hero-copy .ctas button").click()
            listing = pg.url.split("#")[0]
            await go(listing + "#photos")
            await frame("Guided photos with the listing's code. The close-up is missing")
            await go(listing + "#check")
            await pg.evaluate("document.getElementById('check-form').addEventListener('submit', e => e.preventDefault())")
            await pg.locator("#check-form button[type=submit]").click()
            await pg.wait_for_timeout(2400)
            await frame("Muse Spark describes the photos without seeing the claims")
            await pg.reload(wait_until="networkidle")
            async with pg.expect_navigation():
                await pg.locator("#check-form button[type=submit]").click()
            await pg.wait_for_load_state("networkidle")
            await pg.evaluate("scrollTo(0, document.querySelector('.verdict-summary').getBoundingClientRect().top + scrollY - 140)")
            await frame("Fixed rules decide. Muse Spark asks for the exact photo missing")
            async with pg.expect_navigation():
                await pg.locator(".shot-ask .reshoot button").click()
            async with pg.expect_navigation():
                await pg.locator("#check-form button[type=submit]").click()
            await pg.wait_for_load_state("networkidle")
            await pg.locator("#check .verdict.contradicted summary").click()
            await frame("With the close-up, “No scratches or stains” is contradicted")
            await go(listing + "#share")
            async with pg.expect_navigation():
                await pg.locator("#share button[type=submit]").first.click()
            report = pg.url.split("#")[0]
            await go(report)
            await frame("Buyers open the report: a verdict per claim, with the photos")
            await go(listing + "#check")
            await pg.locator("details.edit summary").click()
            await pg.locator("details.edit .claim-phrase").first.click()
            await pg.fill("details.edit input[name=text0]", "Set of 6 chairs")
            await pg.fill("details.edit input[name=value0]", "6")
            async with pg.expect_navigation():
                await pg.locator("details.edit .form-actions button").click()
            await go(report)
            await frame("Edit the listing and the old report stops vouching for it")
            await b.close()

        # 2.4 s per frame with a 0.35 s crossfade, 12 fps, one palette for the whole loop
        hold, fade, fps = 2.4, 0.35, 12
        args, chain, last = [], [], "0:v"
        for f in frames:
            args += ["-loop", "1", "-t", str(hold + fade), "-i", str(f)]
        for i in range(1, len(frames)):
            out = f"x{i}"
            chain.append(f"[{last}][{i}:v]xfade=transition=fade:duration={fade}:offset={i * hold:.2f}[{out}]")
            last = out
        graph = ";".join(chain) + f";[{last}]fps={fps},scale=1000:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=full[p];[b][p]paletteuse=dither=sierra2_4a"
        subprocess.run(["ffmpeg", "-v", "error", "-y", *args, "-filter_complex", graph, "-loop", "0", str(OUT / "walkthrough.gif")], check=True)
    for name in ("hero.jpg", "walkthrough.gif"):
        print(name, (OUT / name).stat().st_size // 1024, "KB")


asyncio.run(main())
