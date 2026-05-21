"""
Browser-Use Vision Enhancement — 可视化对比 Demo

生成直观的 before/after 对比图：
1. 原始网页截图 vs Florence-2 视觉检测标注图
2. DOM-only 信息 vs Vision-enriched 信息对比
3. 自适应策略决策流程可视化
4. 性能数据图表

输出: /Users/raidriar/browser-use-vision/output/ 目录下的图片
"""

from __future__ import annotations

import asyncio
import base64
import os
import sys
import time
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

VISION_API_URL = os.getenv("VISION_API_URL", "http://localhost:8100")

# 不走代理
for var in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"]:
    os.environ.pop(var, None)

import httpx
import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec
from PIL import Image, ImageDraw

# ──────────────────────────────────────────────
# 测试页面
# ──────────────────────────────────────────────
DEMO_PAGES = [
    {
        "name": "Example.com",
        "url": "https://example.com",
        "description": "简单页面 — DOM 信息充足",
    },
    {
        "name": "Wikipedia",
        "url": "https://en.wikipedia.org/wiki/Python_(programming_language)",
        "description": "复杂页面 — 丰富的表格和多媒体",
    },
    {
        "name": "GitHub",
        "url": "https://github.com/browser-use/browser-use",
        "description": "现代 SPA — 动态交互元素",
    },
]


async def take_screenshot(url: str, name: str) -> Path:
    """用 Playwright 截图"""
    from playwright.async_api import async_playwright

    screenshot_path = OUTPUT_DIR / f"{name}_original.png"

    # 使用完整版 Chromium (非 headless shell)
    chromium_path = str(
        Path.home()
        / "Library/Caches/ms-playwright/chromium-1223/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=chromium_path,
        )
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)
        except Exception:
            pass
        await page.screenshot(path=str(screenshot_path), full_page=False)
        await browser.close()

    print(f"  📸 截图完成: {screenshot_path.name}")
    return screenshot_path


def detect_elements(image_path: Path) -> list[dict]:
    """调用 Florence-2 API 检测元素"""
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    t0 = time.perf_counter()
    resp = httpx.post(
        f"{VISION_API_URL}/detect",
        json={"image": img_b64, "threshold": 0.3},
        timeout=30.0,
    )
    elapsed = time.perf_counter() - t0

    data = resp.json()
    elements = data.get("elements", [])
    print(f"  🔍 Florence-2 检测: {len(elements)} 个元素, 耗时 {elapsed:.2f}s")
    return elements


def draw_detection_overlay(image_path: Path, elements: list[dict], name: str) -> Path:
    """在截图上绘制检测框"""
    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)

    # 颜色方案
    colors = [
        "#FF6B6B",
        "#4ECDC4",
        "#45B7D1",
        "#96CEB4",
        "#FFEAA7",
        "#DDA0DD",
        "#98D8C8",
        "#F7DC6F",
        "#BB8FCE",
        "#85C1E9",
        "#F1948A",
        "#82E0AA",
        "#F8C471",
        "#AED6F1",
        "#D7BDE2",
    ]

    for i, elem in enumerate(elements):
        color = colors[i % len(colors)]
        bbox = elem.get("bbox", [])
        label = elem.get("label", elem.get("description", f"elem_{i}"))

        if len(bbox) == 4:
            x1, y1, x2, y2 = bbox
            # 画框
            draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
            # 标签背景
            label_text = f"{i + 1}. {label[:30]}"
            text_bbox = draw.textbbox((x1, y1 - 18), label_text)
            draw.rectangle(
                [text_bbox[0] - 2, text_bbox[1] - 2, text_bbox[2] + 2, text_bbox[3] + 2],
                fill=color,
            )
            draw.text((x1, y1 - 18), label_text, fill="black")

    output_path = OUTPUT_DIR / f"{name}_detected.png"
    img.save(output_path)
    print(f"  🎨 标注图完成: {output_path.name}")
    return output_path


def create_side_by_side(original_path: Path, detected_path: Path, name: str, desc: str, num_elements: int) -> Path:
    """创建 before/after 并排对比图"""
    fig, axes = plt.subplots(1, 2, figsize=(20, 10))
    fig.suptitle(f"Vision Enhancement — {name}", fontsize=20, fontweight="bold", y=0.98)

    orig = Image.open(original_path)
    detected = Image.open(detected_path)

    axes[0].imshow(np.array(orig))
    axes[0].set_title("Before: DOM-Only (原始截图)", fontsize=14, pad=10)
    axes[0].axis("off")
    axes[0].text(
        0.5,
        -0.05,
        "Agent 仅依赖 DOM 树文本信息",
        transform=axes[0].transAxes,
        ha="center",
        fontsize=11,
        color="gray",
    )

    axes[1].imshow(np.array(detected))
    axes[1].set_title(f"After: Vision-Enhanced (Florence-2 检测到 {num_elements} 个元素)", fontsize=14, pad=10)
    axes[1].axis("off")
    axes[1].text(
        0.5,
        -0.05,
        "Agent 获得视觉 Grounding 信息辅助决策",
        transform=axes[1].transAxes,
        ha="center",
        fontsize=11,
        color="gray",
    )

    fig.text(0.5, 0.02, desc, ha="center", fontsize=12, style="italic", color="#555")
    plt.tight_layout(rect=[0, 0.05, 1, 0.95])

    output_path = OUTPUT_DIR / f"{name}_comparison.png"
    fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  📊 对比图完成: {output_path.name}")
    return output_path


def create_adaptive_strategy_diagram() -> Path:
    """绘制自适应视觉策略决策流程图"""
    fig, ax = plt.subplots(figsize=(16, 10))
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 10)
    ax.axis("off")
    fig.patch.set_facecolor("#1a1a2e")

    title_text = "Adaptive Vision Strategy — 自适应视觉策略"
    ax.text(8, 9.5, title_text, ha="center", fontsize=18, fontweight="bold", color="white")

    def draw_box(x, y, w, h, text, color, fontsize=10):
        rect = patches.FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.2",
            facecolor=color,
            edgecolor="white",
            linewidth=1.5,
            alpha=0.9,
        )
        ax.add_patch(rect)
        ax.text(
            x + w / 2,
            y + h / 2,
            text,
            ha="center",
            va="center",
            fontsize=fontsize,
            color="white",
            fontweight="bold",
            wrap=True,
        )

    def draw_arrow(x1, y1, x2, y2, label="", color="white"):
        ax.annotate(
            "",
            xy=(x2, y2),
            xytext=(x1, y1),
            arrowprops=dict(arrowstyle="->", color=color, lw=2),
        )
        if label:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            ax.text(mx + 0.1, my + 0.15, label, fontsize=8, color="#aaa", style="italic")

    # 起点
    draw_box(6, 8.0, 4, 0.8, "📸 Page Screenshot\n截取页面截图", "#16213e", 10)

    # DOM 分析
    draw_arrow(8, 8.0, 8, 7.2)
    draw_box(5.5, 6.4, 5, 0.8, "🔍 DOM Confidence Analysis\n分析 DOM 置信度", "#0f3460", 10)

    # 判断分支
    draw_arrow(8, 6.4, 4, 5.8, "High\n≥0.7", "#4ECDC4")
    draw_arrow(8, 6.4, 8, 5.8, "Medium\n0.4-0.7", "#FFEAA7")
    draw_arrow(8, 6.4, 12, 5.8, "Low\n<0.4", "#FF6B6B")

    # 三种策略
    draw_box(2, 4.8, 4, 1.0, "✅ DOM-Only\n跳过视觉检测\n最快速度", "#27ae60", 9)
    draw_box(6, 4.8, 4, 1.0, "🔄 Selective Vision\n选择性视觉增强\n平衡方案", "#f39c12", 9)
    draw_box(10, 4.8, 4, 1.0, "👁️ Full Vision\nFlorence-2 全检测\n最高精度", "#e74c3c", 9)

    # 循环检测
    draw_arrow(8, 4.8, 8, 4.0, "", "#FF6B6B")
    draw_box(5.5, 3.0, 5, 1.0, "🔄 Loop Detection\n循环检测: 连续重复动作时\n自动升级为 Full Vision", "#8e44ad", 9)

    # 输出
    draw_arrow(8, 3.0, 8, 2.4)
    draw_box(
        4,
        1.4,
        8,
        1.0,
        "📤 Enriched System Prompt\n注入视觉检测元素信息到 Agent 上下文\n辅助 LLM 更准确地定位和操作页面元素",
        "#16213e",
        9,
    )

    # 指标
    metrics = [
        ("DOM 置信度因子", "unlabeled_buttons | no_alt_images | icon_only"),
        ("检测阈值", "confidence > 0.3 → 保留元素"),
        ("循环触发", "连续 2 次相同 action → 强制 full vision"),
    ]
    for i, (k, v) in enumerate(metrics):
        ax.text(0.5, 0.8 - i * 0.3, f"• {k}: {v}", fontsize=8, color="#888")

    output_path = OUTPUT_DIR / "adaptive_strategy.png"
    fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="#1a1a2e")
    plt.close(fig)
    print(f"  📊 策略流程图完成: {output_path.name}")
    return output_path


def create_performance_chart() -> Path:
    """绘制性能对比图表"""
    fig = plt.figure(figsize=(18, 10))
    fig.patch.set_facecolor("#1a1a2e")
    gs = GridSpec(2, 2, figure=fig, hspace=0.35, wspace=0.3)

    # 数据（来自实际测试结果）
    scenarios = ["Extract Title\n(example.com)", "Wikipedia Info\n(Python)"]
    baseline_time = [67.8, 134.8]
    enhanced_time = [200.0, 164.4]
    baseline_steps = [3, 11]
    enhanced_steps = [10, 8]

    colors_baseline = "#4ECDC4"
    colors_enhanced = "#FF6B6B"

    # 1. 耗时对比
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_facecolor("#16213e")
    x = np.arange(len(scenarios))
    w = 0.35
    bars1 = ax1.bar(x - w / 2, baseline_time, w, label="Baseline", color=colors_baseline, alpha=0.9)
    bars2 = ax1.bar(x + w / 2, enhanced_time, w, label="Vision Enhanced", color=colors_enhanced, alpha=0.9)
    ax1.set_ylabel("Time (seconds)", color="white")
    ax1.set_title("⏱️ 耗时对比", color="white", fontsize=14, fontweight="bold")
    ax1.set_xticks(x)
    ax1.set_xticklabels(scenarios, color="white", fontsize=9)
    ax1.tick_params(colors="white")
    ax1.legend(facecolor="#16213e", edgecolor="white", labelcolor="white")
    ax1.bar_label(bars1, fmt="%.1fs", color="white", fontsize=9)
    ax1.bar_label(bars2, fmt="%.1fs", color="white", fontsize=9)
    ax1.spines[:].set_color("#444")

    # 2. 步数对比
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.set_facecolor("#16213e")
    bars3 = ax2.bar(x - w / 2, baseline_steps, w, label="Baseline", color=colors_baseline, alpha=0.9)
    bars4 = ax2.bar(x + w / 2, enhanced_steps, w, label="Vision Enhanced", color=colors_enhanced, alpha=0.9)
    ax2.set_ylabel("Steps", color="white")
    ax2.set_title("🦶 步数对比", color="white", fontsize=14, fontweight="bold")
    ax2.set_xticks(x)
    ax2.set_xticklabels(scenarios, color="white", fontsize=9)
    ax2.tick_params(colors="white")
    ax2.legend(facecolor="#16213e", edgecolor="white", labelcolor="white")
    ax2.bar_label(bars3, color="white", fontsize=11)
    ax2.bar_label(bars4, color="white", fontsize=11)
    ax2.spines[:].set_color("#444")

    # 3. DOM 置信度 vs 策略选择
    ax3 = fig.add_subplot(gs[1, 0])
    ax3.set_facecolor("#16213e")
    confidence_levels = ["High (≥0.7)\nDOM 充足", "Medium (0.4-0.7)\n部分缺失", "Low (<0.4)\nDOM 不足"]
    strategies = ["DOM-Only\n跳过视觉", "Selective\n选择性增强", "Full Vision\n全量检测"]
    strategy_colors = ["#27ae60", "#f39c12", "#e74c3c"]
    proportions = [0.6, 0.25, 0.15]  # 典型分布

    bars5 = ax3.barh(confidence_levels, proportions, color=strategy_colors, alpha=0.9, height=0.6)
    for bar, strat in zip(bars5, strategies):
        ax3.text(
            bar.get_width() + 0.02, bar.get_y() + bar.get_height() / 2, strat, va="center", color="white", fontsize=10
        )
    ax3.set_xlabel("Proportion", color="white")
    ax3.set_title("🎯 自适应策略分布 (典型场景)", color="white", fontsize=14, fontweight="bold")
    ax3.set_xlim(0, 1.0)
    ax3.tick_params(colors="white")
    ax3.spines[:].set_color("#444")

    # 4. 架构优势总结
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.set_facecolor("#16213e")
    ax4.axis("off")
    ax4.set_title("🏗️ Vision Enhancement 优势", color="white", fontsize=14, fontweight="bold")

    advantages = [
        ("🔍 视觉 Grounding", "Florence-2 检测页面元素\n提供精确坐标和描述"),
        ("🧠 自适应策略", "根据 DOM 质量自动决策\n避免不必要的视觉开销"),
        ("🔄 循环检测", "自动发现 Agent 卡死\n升级视觉策略突破困境"),
        ("⚡ 即插即用", "兼容 browser-use 0.12.7\n无侵入式集成"),
    ]

    for i, (title, desc) in enumerate(advantages):
        y_pos = 0.85 - i * 0.22
        ax4.text(0.05, y_pos, title, fontsize=13, fontweight="bold", color="#4ECDC4", transform=ax4.transAxes)
        ax4.text(0.05, y_pos - 0.08, desc, fontsize=10, color="#aaa", transform=ax4.transAxes, linespacing=1.5)

    fig.suptitle(
        "Browser-Use Vision Enhancement — Performance Analysis",
        fontsize=18,
        fontweight="bold",
        color="white",
        y=0.98,
    )

    output_path = OUTPUT_DIR / "performance_chart.png"
    fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="#1a1a2e")
    plt.close(fig)
    print(f"  📊 性能图表完成: {output_path.name}")
    return output_path


async def main():
    print("=" * 60)
    print("  Browser-Use Vision Enhancement — 可视化对比")
    print("=" * 60)

    all_comparisons = []

    for page in DEMO_PAGES:
        print(f"\n{'─' * 60}")
        print(f"  {page['name']} — {page['description']}")
        print(f"  URL: {page['url']}")
        print(f"{'─' * 60}")

        # 1. 截图
        screenshot = await take_screenshot(page["url"], page["name"])

        # 2. Florence-2 检测
        elements = detect_elements(screenshot)

        # 3. 绘制检测标注
        annotated = draw_detection_overlay(screenshot, elements, page["name"])

        # 4. 生成并排对比
        comparison = create_side_by_side(
            screenshot,
            annotated,
            page["name"],
            page["description"],
            len(elements),
        )
        all_comparisons.append(comparison)

    # 5. 自适应策略流程图
    print(f"\n{'─' * 60}")
    print("  生成自适应策略流程图...")
    print(f"{'─' * 60}")
    create_adaptive_strategy_diagram()

    # 6. 性能对比图表
    print(f"\n{'─' * 60}")
    print("  生成性能对比图表...")
    print(f"{'─' * 60}")
    create_performance_chart()

    # 汇总
    print(f"\n{'=' * 60}")
    print("  ✅ 所有可视化图片已生成!")
    print(f"{'=' * 60}")
    print(f"\n  输出目录: {OUTPUT_DIR}")
    for f in sorted(OUTPUT_DIR.glob("*.png")):
        size_kb = f.stat().st_size / 1024
        print(f"    📄 {f.name} ({size_kb:.0f} KB)")
    print()


if __name__ == "__main__":
    asyncio.run(main())
