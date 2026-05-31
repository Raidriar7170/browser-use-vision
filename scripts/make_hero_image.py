"""Generate the README hero image: original vs SoM-annotated, side by side.

GPU-free. Uses browser-use's BrowserSession (the same path the benchmark uses)
to grab a screenshot + DOM selector_map, then applies the project's own
`annotate_screenshot_from_state` to draw numbered Set-of-Mark boxes.

Usage:
  python scripts/make_hero_image.py \
    --url http://localhost:8088/icon_only_player.html \
    --out docs/assets/som_icons.png
"""

import argparse
import asyncio
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import base64

import benchmark_common as bc  # noqa: E402

bc.setup_env()

from PIL import Image, ImageDraw  # noqa: E402

from browser_use.browser.session import BrowserSession  # noqa: E402
from browser_use_vision.som import annotate_screenshot_from_state  # noqa: E402


async def build(url: str, out: Path):
    session = BrowserSession(headless=True, keep_alive=True)
    await session.start()
    page = await session.get_current_page()
    await page.goto(url)
    await asyncio.sleep(2)

    state = await session.get_browser_state_summary()
    n = len(state.dom_state.selector_map or {})
    orig = Image.open(io.BytesIO(base64.b64decode(state.screenshot)))

    annotated_b64 = annotate_screenshot_from_state(state, line_width=3, font_size=16)
    if not annotated_b64:
        raise SystemExit("annotation failed — empty screenshot or selector_map")
    anno = Image.open(io.BytesIO(base64.b64decode(annotated_b64)))

    gap, top = 24, 44
    W = orig.width + anno.width + gap
    H = max(orig.height, anno.height) + top
    canvas = Image.new("RGB", (W, H), (24, 24, 27))
    d = ImageDraw.Draw(canvas)
    d.text((orig.width // 2 - 70, 14), "DOM-only sees no labels", fill=(228, 228, 231))
    d.text((orig.width + gap + anno.width // 2 - 120, 14),
           f"Set-of-Mark: {n} clickable elements numbered", fill=(110, 231, 183))
    canvas.paste(orig, (0, top))
    canvas.paste(anno, (orig.width + gap, top))

    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    await session.close()
    print(f"saved {out}  ({W}x{H}, {n} elements annotated)")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8088/icon_only_player.html")
    ap.add_argument("--out", default="docs/assets/som_icons.png")
    args = ap.parse_args()
    await build(args.url, ROOT / args.out)


if __name__ == "__main__":
    asyncio.run(main())
