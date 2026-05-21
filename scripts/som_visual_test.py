"""
SoM 标注可视化验证脚本

直接用 Playwright 获取截图，用 CDP 获取 DOM 元素 bbox，
然后应用 SoM 标注，保存标注前后的对比图片。

不依赖 browser-use 的 BrowserSession。

Usage:
    python scripts/som_visual_test.py [--url URL] [--output DIR]
"""

import argparse
import asyncio
import base64
import io
import os
import sys
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw


@dataclass
class SimpleDOMRect:
    x: float
    y: float
    width: float
    height: float


@dataclass
class SimpleSnapshotNode:
    bounds: Optional[SimpleDOMRect] = None
    clientRects: Optional[SimpleDOMRect] = None


@dataclass
class SimpleNode:
    snapshot_node: Optional[SimpleSnapshotNode] = None


async def get_interactive_elements(page) -> dict[int, SimpleNode]:
    """
    用 JS 获取页面上所有可交互元素的 bounding box，
    返回模拟 browser-use selector_map 格式的字典
    """
    elements_data = await page.evaluate("""
    () => {
        const interactive = document.querySelectorAll(
            'a, button, input, select, textarea, [role="button"], [role="link"], ' +
            '[role="checkbox"], [role="radio"], [role="tab"], [role="menuitem"], ' +
            '[onclick], [tabindex]:not([tabindex="-1"])'
        );
        const results = [];
        for (let i = 0; i < interactive.length; i++) {
            const el = interactive[i];
            const rect = el.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
                results.push({
                    id: i + 1,
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height,
                    tag: el.tagName.toLowerCase(),
                    text: (el.textContent || '').trim().substring(0, 50),
                });
            }
        }
        return results;
    }
    """)

    selector_map = {}
    for el in elements_data:
        node = SimpleNode(
            snapshot_node=SimpleSnapshotNode(
                clientRects=SimpleDOMRect(x=el["x"], y=el["y"], width=el["width"], height=el["height"])
            )
        )
        selector_map[el["id"]] = node

    return selector_map


async def main(url: str, output_dir: str):
    from playwright.async_api import async_playwright

    from browser_use_vision.som import annotate_screenshot

    os.makedirs(output_dir, exist_ok=True)

    print("[1/5] 启动浏览器...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=os.path.expanduser(
                "~/Library/Caches/ms-playwright/chromium-1223/chrome-mac-arm64/"
                "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
            ),
        )
        context = await browser.new_context(viewport={"width": 1280, "height": 720})
        page = await context.new_page()

        print(f"[2/5] 打开页面: {url}")
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(1)

        print("[3/5] 截图 + 获取 DOM...")
        screenshot_bytes = await page.screenshot(type="png", full_page=False)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode()

        selector_map = await get_interactive_elements(page)
        print(f"     找到 {len(selector_map)} 个可交互元素")

        # 保存原始截图
        original_path = os.path.join(output_dir, "som_original.png")
        with open(original_path, "wb") as f:
            f.write(screenshot_bytes)
        print(f"     原始截图: {original_path}")

        print("[4/5] 应用 SoM 标注...")
        annotated_b64 = annotate_screenshot(
            screenshot_b64=screenshot_b64,
            selector_map=selector_map,
            viewport_offset_y=0,
            line_width=2,
            font_size=14,
            max_elements=50,
        )

        annotated_path = os.path.join(output_dir, "som_annotated.png")
        annotated_bytes = base64.b64decode(annotated_b64)
        with open(annotated_path, "wb") as f:
            f.write(annotated_bytes)
        print(f"     标注截图: {annotated_path}")

        # 创建对比图
        print("[5/5] 生成对比图...")
        orig_img = Image.open(io.BytesIO(screenshot_bytes))
        anno_img = Image.open(io.BytesIO(annotated_bytes))

        total_width = orig_img.width + anno_img.width + 20
        max_height = max(orig_img.height, anno_img.height) + 40
        comparison = Image.new("RGB", (total_width, max_height), (30, 30, 30))

        draw = ImageDraw.Draw(comparison)
        draw.text((orig_img.width // 2 - 30, 5), "Original", fill=(200, 200, 200))
        draw.text((orig_img.width + 10 + anno_img.width // 2 - 60, 5), "SoM Annotated", fill=(200, 200, 200))

        comparison.paste(orig_img, (0, 35))
        comparison.paste(anno_img, (orig_img.width + 20, 35))

        comparison_path = os.path.join(output_dir, "som_comparison.png")
        comparison.save(comparison_path)
        print(f"     对比图: {comparison_path}")

        # 打印元素统计
        print("\n📊 SoM 标注统计:")
        print(f"   页面: {url}")
        print(f"   可交互元素: {len(selector_map)}")

        await browser.close()

    print(f"\n✅ 完成！查看 {output_dir}/ 目录下的图片")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SoM 标注可视化测试")
    parser.add_argument("--url", default="https://www.google.com", help="测试页面 URL")
    parser.add_argument("--output", default="output/som_test", help="输出目录")
    args = parser.parse_args()

    asyncio.run(main(args.url, args.output))
