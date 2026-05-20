"""
Browser-Use Vision Enhancement - Interactive Demo

可视化展示视觉 Grounding 增强效果：
1. 上传网页截图 → Florence-2 检测 UI 元素
2. 输入 DOM 文本 → 评估置信度 → 自适应决策
3. 对比 DOM-only vs Vision-enhanced 的信息差异

启动方式:
    cd /mnt/data/minghongsun/browser-use-vision
    PYTHONPATH=. python3 demo/app.py
"""

import asyncio
import base64
import io
import json
import sys
import time
from pathlib import Path

import gradio as gr
import httpx
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent.parent))

from browser_use_vision.adaptive import AdaptiveVisionStrategy, VisionDecision, assess_dom_confidence
from browser_use_vision.grounding import DetectedElement


VISION_API_URL = "http://localhost:8100"


async def detect_elements_api(image_bytes: bytes, threshold: float = 0.3) -> list[dict]:
    """调用 Vision API 检测元素"""
    img_b64 = base64.b64encode(image_bytes).decode()
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{VISION_API_URL}/detect",
            json={"image": img_b64, "threshold": threshold},
        )
        resp.raise_for_status()
        data = resp.json()
    return data["elements"], data["inference_time_ms"]


async def describe_region_api(image_bytes: bytes, bbox: list[float]) -> str:
    """调用 Vision API 描述区域"""
    img_b64 = base64.b64encode(image_bytes).decode()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{VISION_API_URL}/describe",
            json={"image": img_b64, "bbox": bbox},
        )
        resp.raise_for_status()
        data = resp.json()
    return data["description"]


def draw_detections(image: Image.Image, elements: list[dict]) -> Image.Image:
    """在图片上绘制检测结果"""
    img = image.copy()
    draw = ImageDraw.Draw(img)
    w, h = img.size

    colors = [
        (255, 0, 0), (0, 200, 0), (0, 100, 255),
        (255, 165, 0), (128, 0, 128), (0, 200, 200),
        (255, 192, 203), (165, 42, 42), (128, 128, 0),
    ]

    for i, el in enumerate(elements):
        bbox = el["bbox"]
        x1, y1, x2, y2 = int(bbox[0]*w), int(bbox[1]*h), int(bbox[2]*w), int(bbox[3]*h)
        color = colors[i % len(colors)]

        # 绘制边框
        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)

        # 标签背景
        label = f"[{i}] {el['label']}"
        text_bbox = draw.textbbox((0, 0), label)
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]
        label_y = max(0, y1 - text_h - 4)
        draw.rectangle([x1, label_y, x1 + text_w + 4, label_y + text_h + 4], fill=color)
        draw.text((x1 + 2, label_y + 2), label, fill=(255, 255, 255))

    return img


def analyze_screenshot(image, threshold):
    """分析截图：检测 UI 元素并可视化"""
    if image is None:
        return None, "请上传一张网页截图", ""

    # 转为 bytes
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    try:
        elements, inference_ms = asyncio.get_event_loop().run_until_complete(
            detect_elements_api(img_bytes, threshold)
        )
    except Exception:
        # 如果没有 event loop，创建一个
        loop = asyncio.new_event_loop()
        elements, inference_ms = loop.run_until_complete(
            detect_elements_api(img_bytes, threshold)
        )
        loop.close()

    if not elements:
        return image, "未检测到 UI 元素。尝试降低阈值。", f"推理耗时: {inference_ms:.0f}ms"

    # 绘制检测结果
    result_img = draw_detections(image, elements)

    # 格式化结果文本
    lines = [f"检测到 {len(elements)} 个 UI 元素 (推理: {inference_ms:.0f}ms)\n"]
    for i, el in enumerate(elements):
        bbox = el["bbox"]
        lines.append(f"[{i}] {el['label']}")
        lines.append(f"    位置: ({bbox[0]:.3f}, {bbox[1]:.3f}, {bbox[2]:.3f}, {bbox[3]:.3f})")
        lines.append(f"    描述: {el['description'][:80]}")
        lines.append(f"    置信度: {el['confidence']:.2f}")
        if el.get("ocr_text"):
            lines.append(f"    OCR: {el['ocr_text']}")
        lines.append("")

    stats = f"推理耗时: {inference_ms:.0f}ms | 元素数: {len(elements)}"
    return result_img, "\n".join(lines), stats


def analyze_dom_confidence(dom_text):
    """评估 DOM 置信度并给出视觉调用建议"""
    if not dom_text.strip():
        return "请输入 DOM 文本", "", ""

    confidence, signals = assess_dom_confidence(dom_text)
    strategy = AdaptiveVisionStrategy()
    decision = strategy.decide(dom_text)

    # 格式化信号
    signal_lines = [
        f"DOM 置信度: {confidence:.2f} / 1.00",
        "",
        "信号分析:",
        f"  可交互元素总数: {signals.total_interactive}",
        f"  无标签按钮数: {signals.unlabeled_buttons}",
        f"  缺 alt 图片数: {signals.images_without_alt}",
        f"  generic role 数: {signals.generic_role_count}",
        f"  图标类名数: {signals.icon_class_count}",
        f"  自定义组件数: {signals.custom_component_count}",
        f"  文本总长度: {signals.total_text_length}",
    ]

    # 决策
    decision_map = {
        VisionDecision.SKIP: "✅ SKIP - DOM 信息充足，跳过视觉模型（节省推理开销）",
        VisionDecision.LIGHTWEIGHT: "⚡ LIGHTWEIGHT - DOM 信息部分缺失，仅做 OCR 补充",
        VisionDecision.FULL: "🔍 FULL - DOM 信息严重不足，需要完整视觉 Grounding",
    }
    decision_text = decision_map.get(decision, str(decision))

    # 建议
    suggestions = []
    if signals.unlabeled_buttons > 0:
        suggestions.append(f"⚠️ 发现 {signals.unlabeled_buttons} 个无文字按钮，视觉模型可帮助识别图标含义")
    if signals.images_without_alt > 2:
        suggestions.append(f"⚠️ 发现 {signals.images_without_alt} 张无 alt 的图片，需要视觉描述")
    if signals.icon_class_count > 3:
        suggestions.append(f"⚠️ 发现 {signals.icon_class_count} 个图标元素，DOM 无法表达其功能")
    if signals.custom_component_count > 3:
        suggestions.append(f"⚠️ 发现 {signals.custom_component_count} 个自定义组件，DOM 结构可能不反映功能")
    if not suggestions:
        suggestions.append("✅ DOM 信息充足，无需额外视觉辅助")

    return "\n".join(signal_lines), decision_text, "\n".join(suggestions)


def describe_region(image, x1, y1, x2, y2):
    """为指定区域生成视觉描述"""
    if image is None:
        return "请先上传图片"

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    bbox = [x1, y1, x2, y2]

    try:
        loop = asyncio.new_event_loop()
        desc = loop.run_until_complete(describe_region_api(img_bytes, bbox))
        loop.close()
    except Exception as e:
        return f"描述失败: {e}"

    return desc


# 示例 DOM 文本
EXAMPLE_DOM_GOOD = """<nav>
  <a href="/">Home</a>
  <a href="/about">About Us</a>
  <a href="/contact">Contact</a>
</nav>
<button type="submit">Submit Form</button>
<button type="button">Cancel</button>
<input type="text" placeholder="Enter your name" aria-label="Name">
<img src="logo.png" alt="Company Logo">"""

EXAMPLE_DOM_BAD = """<div class="toolbar">
  <button class="icon-btn"><svg viewBox="0 0 24 24"></svg></button>
  <button class="icon-btn"></button>
  <button></button>
  <button class="material-icon"></button>
  <div class="fa-icon action-btn"></div>
  <div class="svg-icon"></div>
</div>
<img src="banner.jpg">
<img src="icon1.svg">
<img src="icon2.svg">
<img src="photo.jpg">
<custom-dropdown></custom-dropdown>
<app-sidebar></app-sidebar>
<my-button>Click</my-button>"""


# 构建 Gradio UI
with gr.Blocks(
    title="Browser-Use Vision Enhancement Demo",
) as demo:
    gr.Markdown("""
    # 🔍 Browser-Use Vision Enhancement Demo

    为 [browser-use](https://github.com/browser-use/browser-use) Agent 框架提供视觉 Grounding 增强能力。
    通过 Florence-2 模型识别网页中的 UI 元素，弥补 DOM 解析的信息缺失。
    """)

    with gr.Tabs():
        # Tab 1: 截图分析
        with gr.TabItem("📸 截图元素检测"):
            gr.Markdown("上传网页截图，Florence-2 自动检测所有 UI 元素并生成描述。")
            with gr.Row():
                with gr.Column(scale=1):
                    input_image = gr.Image(type="pil", label="上传网页截图")
                    threshold_slider = gr.Slider(0.1, 0.9, value=0.3, step=0.05, label="检测阈值")
                    detect_btn = gr.Button("🔍 检测 UI 元素", variant="primary")
                with gr.Column(scale=1):
                    output_image = gr.Image(type="pil", label="检测结果")
                    output_text = gr.Textbox(label="元素详情", lines=12)
                    output_stats = gr.Textbox(label="统计信息", lines=1)

            detect_btn.click(
                analyze_screenshot,
                inputs=[input_image, threshold_slider],
                outputs=[output_image, output_text, output_stats],
            )

        # Tab 2: DOM 置信度评估
        with gr.TabItem("📊 DOM 置信度评估"):
            gr.Markdown("输入 DOM 文本，自适应策略评估是否需要调用视觉模型。")
            with gr.Row():
                with gr.Column(scale=1):
                    dom_input = gr.Textbox(
                        label="DOM 文本 (序列化的 HTML)",
                        lines=12,
                        placeholder="粘贴 DOM 文本...",
                    )
                    with gr.Row():
                        example_good_btn = gr.Button("📗 示例: 信息充足的 DOM")
                        example_bad_btn = gr.Button("📕 示例: 信息缺失的 DOM")
                    assess_btn = gr.Button("📊 评估置信度", variant="primary")
                with gr.Column(scale=1):
                    confidence_output = gr.Textbox(label="置信度分析", lines=8)
                    decision_output = gr.Textbox(label="自适应决策", lines=2)
                    suggestion_output = gr.Textbox(label="建议", lines=4)

            example_good_btn.click(lambda: EXAMPLE_DOM_GOOD, outputs=[dom_input])
            example_bad_btn.click(lambda: EXAMPLE_DOM_BAD, outputs=[dom_input])
            assess_btn.click(
                analyze_dom_confidence,
                inputs=[dom_input],
                outputs=[confidence_output, decision_output, suggestion_output],
            )

        # Tab 3: 区域描述
        with gr.TabItem("💬 区域描述"):
            gr.Markdown("选择截图中的一个区域，Florence-2 生成自然语言描述。")
            with gr.Row():
                with gr.Column(scale=1):
                    region_image = gr.Image(type="pil", label="上传截图")
                    with gr.Row():
                        x1_input = gr.Number(value=0.0, label="x1 (0-1)", minimum=0, maximum=1, step=0.01)
                        y1_input = gr.Number(value=0.0, label="y1 (0-1)", minimum=0, maximum=1, step=0.01)
                        x2_input = gr.Number(value=1.0, label="x2 (0-1)", minimum=0, maximum=1, step=0.01)
                        y2_input = gr.Number(value=1.0, label="y2 (0-1)", minimum=0, maximum=1, step=0.01)
                    describe_btn = gr.Button("💬 生成描述", variant="primary")
                with gr.Column(scale=1):
                    region_description = gr.Textbox(label="区域描述", lines=6)

            describe_btn.click(
                describe_region,
                inputs=[region_image, x1_input, y1_input, x2_input, y2_input],
                outputs=[region_description],
            )

    gr.Markdown("""
    ---
    **技术栈**: Florence-2-large | browser-use 0.12.7 | PyTorch 2.1 + CUDA 12.2 | FastAPI

    **GitHub**: browser-use-vision (Visual Grounding Enhancement for browser-use)
    """)


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
    )
