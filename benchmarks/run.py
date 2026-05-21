"""
评测运行脚本

对比 baseline (DOM-only) vs vision-enhanced 在多种网页场景上的表现。
需要先启动:
1. Vision API: python -m browser_use_vision.server --port 8100
2. LLM API: python scripts/llm_server.py --port 8200

运行:
    cd /mnt/data/minghongsun/browser-use-vision
    PYTHONPATH=. python3 benchmarks/run.py --mode both
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from browser_use_vision.adaptive import AdaptiveVisionStrategy, VisionDecision, assess_dom_confidence


def run_dom_confidence_benchmark():
    """
    不需要浏览器/LLM 的纯计算评测:
    对各种 DOM 样本评估自适应策略的决策质量
    """
    print("\n" + "=" * 70)
    print("  自适应视觉策略评测 — DOM 置信度分析")
    print("=" * 70)

    # 模拟不同类型网页的 DOM 文本
    dom_samples = {
        "simple_form": {
            "dom": """
            <form>
              <label for="name">Name</label>
              <input id="name" type="text" placeholder="Enter name">
              <label for="email">Email</label>
              <input id="email" type="email" placeholder="Enter email">
              <button type="submit">Submit</button>
              <button type="reset">Clear</button>
            </form>
            """,
            "expected": VisionDecision.SKIP,
            "description": "简单表单 — DOM 信息充足",
        },
        "icon_toolbar": {
            "dom": """
            <div class="toolbar">
              <button class="icon-btn"><svg viewBox="0 0 24 24"></svg></button>
              <button class="icon-btn"><svg viewBox="0 0 24 24"></svg></button>
              <button class="icon-btn"></button>
              <button></button>
              <button class="material-icon"></button>
              <div class="fa-icon action"></div>
              <div class="svg-icon"></div>
              <div class="fa-icon"></div>
              <img src="tool1.svg">
              <img src="tool2.svg">
              <img src="tool3.svg">
              <img src="tool4.svg">
            </div>
            """,
            "expected": VisionDecision.FULL,
            "description": "图标工具栏 — DOM 严重缺失语义",
        },
        "ecommerce_grid": {
            "dom": """
            <div class="product-grid">
              <div class="product-card">
                <img src="product1.jpg">
                <h3>Wireless Headphones</h3>
                <span class="price">$49.99</span>
                <button>Add to Cart</button>
              </div>
              <div class="product-card">
                <img src="product2.jpg">
                <h3>Bluetooth Speaker</h3>
                <span class="price">$29.99</span>
                <button>Add to Cart</button>
              </div>
              <div class="product-card">
                <img src="product3.jpg" alt="USB Cable">
                <h3>USB-C Cable</h3>
                <span class="price">$9.99</span>
                <button>Add to Cart</button>
              </div>
            </div>
            """,
            "expected": VisionDecision.LIGHTWEIGHT,
            "description": "电商网格 — 部分图片缺 alt",
        },
        "custom_spa": {
            "dom": """
            <app-header>
              <nav-menu>
                <menu-item></menu-item>
                <menu-item></menu-item>
              </nav-menu>
              <user-avatar></user-avatar>
            </app-header>
            <app-sidebar>
              <sidebar-item icon="home"></sidebar-item>
              <sidebar-item icon="settings"></sidebar-item>
              <sidebar-item icon="help"></sidebar-item>
            </app-sidebar>
            <app-content>
              <custom-dropdown></custom-dropdown>
              <data-table></data-table>
            </app-content>
            """,
            "expected": VisionDecision.FULL,
            "description": "自定义 SPA — 大量自定义组件",
        },
        "news_article": {
            "dom": """
            <article>
              <h1>Breaking News: AI Advances</h1>
              <p class="author">By John Smith</p>
              <p class="date">May 19, 2026</p>
              <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit.</p>
              <p>Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.</p>
              <a href="/comments">View Comments (42)</a>
              <button>Share</button>
              <button>Bookmark</button>
            </article>
            """,
            "expected": VisionDecision.SKIP,
            "description": "新闻文章 — 纯文本内容充足",
        },
        "mixed_dashboard": {
            "dom": """
            <div class="dashboard">
              <div class="stats-card">
                <h3>Revenue</h3>
                <span>$12,345</span>
              </div>
              <button>Export</button>
              <button class="icon-btn"></button>
              <button></button>
              <img src="chart.png">
              <img src="graph.svg">
              <div class="fa-icon notification-bell"></div>
              <a href="/settings">Settings</a>
              <input type="search" placeholder="Search...">
            </div>
            """,
            "expected": VisionDecision.LIGHTWEIGHT,
            "description": "管理面板 — 混合内容",
        },
        "canvas_app": {
            "dom": """
            <div class="canvas-container" role="generic">
              <canvas id="main-canvas" width="1920" height="1080"></canvas>
              <div class="floating-toolbar" role="generic">
                <button></button>
                <button></button>
                <button></button>
                <button></button>
                <button></button>
              </div>
            </div>
            """,
            "expected": VisionDecision.FULL,
            "description": "Canvas 应用 — DOM 几乎无信息",
        },
        "accessible_site": {
            "dom": """
            <nav aria-label="Main navigation">
              <a href="/" aria-current="page">Home</a>
              <a href="/products">Products</a>
              <a href="/about">About</a>
              <a href="/contact">Contact</a>
            </nav>
            <main>
              <h1>Welcome</h1>
              <img src="hero.jpg" alt="Beautiful landscape with mountains">
              <button aria-label="Open menu">Menu</button>
              <button aria-label="Search">Search</button>
            </main>
            """,
            "expected": VisionDecision.SKIP,
            "description": "无障碍网站 — ARIA 标签完善",
        },
    }

    strategy = AdaptiveVisionStrategy(high_threshold=0.8, low_threshold=0.5)
    results = []

    for name, sample in dom_samples.items():
        confidence, signals = assess_dom_confidence(sample["dom"])
        decision = strategy.decide(sample["dom"])
        match = decision == sample["expected"]

        results.append(
            {
                "name": name,
                "confidence": confidence,
                "decision": decision.value,
                "expected": sample["expected"].value,
                "match": match,
                "description": sample["description"],
                "signals": {
                    "interactive": signals.total_interactive,
                    "unlabeled_buttons": signals.unlabeled_buttons,
                    "no_alt_images": signals.images_without_alt,
                    "icons": signals.icon_class_count,
                    "custom_components": signals.custom_component_count,
                },
            }
        )

        status = "✅" if match else "❌"
        print(f"\n  {status} {name}: {sample['description']}")
        print(f"     置信度: {confidence:.2f} | 决策: {decision.value} | 期望: {sample['expected'].value}")
        print(
            f"     信号: buttons={signals.total_interactive} unlabeled={signals.unlabeled_buttons} "
            f"no_alt={signals.images_without_alt} icons={signals.icon_class_count} "
            f"custom={signals.custom_component_count}"
        )

    # 汇总
    correct = sum(1 for r in results if r["match"])
    total = len(results)
    print(f"\n{'=' * 70}")
    print(f"  准确率: {correct}/{total} ({correct / total * 100:.0f}%)")

    # 统计各决策的分布
    decision_counts = {}
    for r in results:
        d = r["decision"]
        decision_counts[d] = decision_counts.get(d, 0) + 1
    print(f"  决策分布: {decision_counts}")
    print(f"  预期节省率: {decision_counts.get('skip', 0)}/{total} 的场景不需要视觉模型")
    print(f"{'=' * 70}")

    # 保存结果
    output_dir = Path("benchmarks/results")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"adaptive_strategy_{int(time.time())}.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n  结果保存到: {output_file}")

    return results


def run_vision_api_benchmark():
    """
    测试 Vision API 的推理性能
    """
    import base64
    import io

    import httpx
    from PIL import Image, ImageDraw

    print("\n" + "=" * 70)
    print("  Vision API 性能评测")
    print("=" * 70)

    # 生成不同复杂度的测试图
    test_cases = [
        ("simple_page", 640, 480, 5),
        ("medium_page", 1280, 720, 15),
        ("complex_page", 1920, 1080, 30),
    ]

    results = []
    for name, w, h, n_elements in test_cases:
        img = Image.new("RGB", (w, h), (255, 255, 255))
        draw = ImageDraw.Draw(img)

        # 绘制模拟 UI 元素
        for i in range(n_elements):
            x = (i * 120) % (w - 100)
            y = ((i * 120) // (w - 100)) * 60 + 20
            if y + 40 > h:
                break
            color = ((i * 37) % 256, (i * 73) % 256, (i * 113) % 256)
            draw.rectangle([x, y, x + 100, y + 40], fill=color, outline=(0, 0, 0))
            draw.text((x + 10, y + 12), f"Btn {i}", fill=(255, 255, 255))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        img_bytes = buf.getvalue()
        img_b64 = base64.b64encode(img_bytes).decode()

        # 调用 API
        try:
            t0 = time.time()
            resp = httpx.post(
                "http://localhost:8100/detect",
                json={"image": img_b64, "threshold": 0.2},
                timeout=60,
            )
            total_time = (time.time() - t0) * 1000
            data = resp.json()
            n_detected = len(data.get("elements", []))
            api_time = data.get("inference_time_ms", 0)

            results.append(
                {
                    "name": name,
                    "resolution": f"{w}x{h}",
                    "ui_elements": n_elements,
                    "detected": n_detected,
                    "api_time_ms": api_time,
                    "total_time_ms": total_time,
                }
            )
            print(f"\n  {name} ({w}x{h}, {n_elements} elements):")
            print(f"    检测到: {n_detected} 元素 | 推理: {api_time:.0f}ms | 总耗时: {total_time:.0f}ms")

        except Exception as e:
            print(f"\n  ❌ {name}: {e}")
            results.append({"name": name, "error": str(e)})

    # 保存
    output_dir = Path("benchmarks/results")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"vision_api_perf_{int(time.time())}.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  结果保存到: {output_file}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Browser-Use Vision Benchmark")
    parser.add_argument(
        "--mode",
        choices=["adaptive", "vision", "both"],
        default="both",
        help="评测模式: adaptive(自适应策略) / vision(Vision API) / both",
    )
    args = parser.parse_args()

    if args.mode in ("adaptive", "both"):
        run_dom_confidence_benchmark()

    if args.mode in ("vision", "both"):
        run_vision_api_benchmark()

    print("\n\n✅ 评测完成！结果在 benchmarks/results/ 目录下。")


if __name__ == "__main__":
    main()
