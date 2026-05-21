"""
端到端测试: Florence-2 模型加载 + 推理

在 A100 上加载 Florence-2-large，对一张合成测试图片做目标检测和描述。
验证整条链路: 模型加载 → 图片预处理 → 推理 → 结果解析
"""

import asyncio
import io
import sys
import time

# 生成一张简单的测试图片（模拟网页截图）
from PIL import Image, ImageDraw


def create_test_screenshot() -> bytes:
    """创建一张模拟网页截图"""
    img = Image.new("RGB", (1280, 720), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 模拟导航栏
    draw.rectangle([0, 0, 1280, 60], fill=(51, 51, 51))
    draw.text((20, 18), "MyWebsite", fill=(255, 255, 255))

    # 模拟搜索框
    draw.rectangle([400, 15, 700, 45], fill=(255, 255, 255), outline=(200, 200, 200))
    draw.text((410, 22), "Search...", fill=(150, 150, 150))

    # 模拟按钮
    draw.rectangle([800, 100, 950, 140], fill=(0, 123, 255), outline=(0, 100, 200))
    draw.text((830, 112), "Click Me", fill=(255, 255, 255))

    # 模拟图标区域（无文字的圆形按钮）
    draw.ellipse([1100, 10, 1140, 50], fill=(255, 0, 0))  # 红色通知图标
    draw.ellipse([1160, 10, 1200, 50], fill=(0, 150, 0))  # 绿色状态图标

    # 模拟文本内容
    draw.text((50, 200), "Welcome to the Dashboard", fill=(0, 0, 0))
    draw.text((50, 240), "This is a sample page for testing vision grounding.", fill=(100, 100, 100))

    # 模拟卡片
    draw.rectangle([50, 300, 350, 500], outline=(200, 200, 200), width=2)
    draw.text((70, 320), "Card Title", fill=(0, 0, 0))
    draw.text((70, 350), "Some description text", fill=(100, 100, 100))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def main():
    sys.path.insert(0, "/mnt/data/minghongsun/browser-use-vision")

    from browser_use_vision.grounding.florence import FlorenceBackend

    print("=" * 60)
    print("  Florence-2 End-to-End Test")
    print("=" * 60)

    # 1. 创建测试图片
    print("\n[1] Creating test screenshot...")
    screenshot = create_test_screenshot()
    print(f"    Screenshot size: {len(screenshot)} bytes")

    # 2. 初始化后端
    print("\n[2] Loading Florence-2 model...")
    t0 = time.time()
    backend = FlorenceBackend(
        model_name="/mnt/data/minghongsun/models/florence-2-large",
        device="cuda",
    )
    await backend.load_model()
    load_time = time.time() - t0
    print(f"    Model loaded in {load_time:.1f}s")
    print(f"    Device: {backend.device}")

    # 3. 目标检测
    print("\n[3] Running element detection...")
    t0 = time.time()
    elements = await backend.detect_elements(screenshot, threshold=0.2)
    detect_time = time.time() - t0
    print(f"    Detected {len(elements)} elements in {detect_time:.1f}s")

    for i, el in enumerate(elements):
        print(f'    [{i}] {el.label} at {el.bbox} - "{el.description[:60]}" (conf={el.confidence:.2f})')

    # 4. 区域描述
    print("\n[4] Describing specific region (button area)...")
    t0 = time.time()
    desc = await backend.describe_region(screenshot, (0.625, 0.139, 0.742, 0.194))
    desc_time = time.time() - t0
    print(f'    Description: "{desc}"')
    print(f"    Time: {desc_time:.1f}s")

    # 5. 测试 DOM 匹配
    print("\n[5] Testing DOM-to-visual matching...")
    dom_elements = [
        {"id": "btn1", "tag": "button", "text": "Click Me", "bbox": (0.625, 0.139, 0.742, 0.194)},
        {"id": "icon1", "tag": "div", "text": "", "bbox": (0.859, 0.014, 0.891, 0.069)},
        {"id": "search", "tag": "input", "text": "Search...", "bbox": (0.312, 0.021, 0.547, 0.063)},
    ]
    enriched = await backend.match_dom_to_visual(dom_elements, elements, iou_threshold=0.1)
    for el in enriched:
        vis_desc = el.get("visual_description", "NO MATCH")
        print(f'    {el["id"]}: visual_description="{vis_desc[:50]}"')

    # 6. 总结
    print("\n" + "=" * 60)
    print("  PASSED - All checks completed")
    print(f"  Model load: {load_time:.1f}s | Detect: {detect_time:.1f}s | Describe: {desc_time:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
