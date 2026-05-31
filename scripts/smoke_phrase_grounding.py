import asyncio
import base64
import sys
from pathlib import Path

import httpx

ROOT = Path("/Users/raidriar/browser-use-vision")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import benchmark_common as bc  # noqa: E402

bc.setup_env()
from browser_use.browser.session import BrowserSession  # noqa: E402
from browser_use_vision.grounding import VisualGroundingBackend  # noqa: E402
from browser_use_vision.som import _get_viewport_bbox  # noqa: E402

VISION = "http://localhost:8100"


def center_contained(a, b):
    ax, ay = (a[0] + a[2]) / 2, (a[1] + a[3]) / 2
    bx, by = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    a_has_b = a[0] <= bx <= a[2] and a[1] <= by <= a[3]
    b_has_a = b[0] <= ax <= b[2] and b[1] <= ay <= b[3]
    return a_has_b or b_has_a


async def probe(url, phrase, target_action):
    print(f"\n{'='*70}\nURL: {url}\nPHRASE: {phrase!r}  TARGET data-action={target_action!r}")
    session = BrowserSession(headless=True, keep_alive=True)
    await session.start()
    page = await session.get_current_page()
    await page.goto(url)
    await asyncio.sleep(2)
    state = await session.get_browser_state_summary()
    sm = state.dom_state.selector_map
    offset_y = float(getattr(state, "pixels_above", 0) or 0)

    shot_b64 = state.screenshot
    img_bytes = base64.b64decode(shot_b64)
    from PIL import Image
    import io as _io

    img = Image.open(_io.BytesIO(img_bytes))
    W, H = img.size
    print(f"screenshot {W}x{H}, pixels_above={offset_y}, selector_map={len(sm)} nodes")

    # build DOM normalized bboxes, find target by data-action attr
    dom = {}
    target_id = None
    for nid, node in sm.items():
        vb = _get_viewport_bbox(node, offset_y)
        if vb is None:
            continue
        x, y, w, h = vb
        if w < 5 or h < 5:
            continue
        nb = (x / W, y / H, (x + w) / W, (y + h) / H)
        attrs = getattr(node, "attributes", {}) or {}
        da = attrs.get("data-action") or attrs.get("data-tool")
        dom[nid] = (nb, da)
        if da == target_action:
            target_id = nid
    print(f"target DOM index = {target_id}  bbox={dom.get(target_id, ('?',))[0]}")

    # call phrase grounding
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{VISION}/phrase_grounding", json={"image": shot_b64, "phrase": phrase})
        resp.raise_for_status()
        data = resp.json()
    regions = data.get("regions", [])
    print(f"phrase_grounding returned {len(regions)} region(s) in {data.get('inference_time_ms', 0):.0f}ms:")
    for r in regions:
        print(f"   caption={r.get('caption')!r} bbox={[round(v,3) for v in r['bbox']]}")

    if not regions:
        print(">>> NO-GO signal: empty grounding")
        await session.close()
        return

    # For each grounded region, find best DOM match by IoU; report whether target wins
    for ri, r in enumerate(regions):
        vb = tuple(r["bbox"])
        scores = []
        for nid, (nb, da) in dom.items():
            iou = VisualGroundingBackend._compute_iou(nb, vb)
            cc = center_contained(nb, vb)
            scores.append((iou, cc, nid, da))
        scores.sort(reverse=True)
        print(f"\n region[{ri}] top DOM matches by IoU:")
        for iou, cc, nid, da in scores[:5]:
            mark = " <-- TARGET" if nid == target_id else ""
            print(f"     [{nid}] iou={iou:.3f} center_contained={cc} action={da}{mark}")
        # verdict
        best = scores[0]
        if best[2] == target_id and best[0] > 0:
            print(f"   VERDICT region[{ri}]: GO (target is top IoU match, iou={best[0]:.3f})")
        elif target_id is not None:
            t_iou = next((s[0] for s in scores if s[2] == target_id), 0.0)
            t_cc = next((s[1] for s in scores if s[2] == target_id), False)
            print(f"   VERDICT region[{ri}]: target iou={t_iou:.3f} cc={t_cc}; top is [{best[2]}] action={best[3]}")

    await session.close()


async def main():
    await probe(
        "http://localhost:8088/icon_only_player.html",
        "Next Track button",
        "next",
    )
    await probe(
        "http://localhost:8088/toolbar_app.html",
        "eraser tool",
        "eraser",
    )


asyncio.run(main())
