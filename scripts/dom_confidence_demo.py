"""
Browser-Use Vision Enhancement — 视觉增强优势场景对比

场景设计：
1. Icon-only 按钮页面 — DOM 里只有 <button class="icon"><svg>...</svg></button>，无文字
2. Canvas 渲染页面 — DOM 几乎没有可交互信息
3. 复杂 SPA dashboard — 大量动态元素

对比维度：
- Florence-2 能检测出多少额外信息
- DOM 置信度分数对比
- Agent 上下文信息量对比
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from browser_use_vision.adaptive import AdaptiveVisionStrategy, VisionDecision, assess_dom_confidence

# =====================================================
#  测试不同页面的 DOM 置信度
# =====================================================

# 场景 1: 正常的 example.com — DOM 信息充足
GOOD_DOM = """
<h1>Example Domain</h1>
<p>This domain is for use in illustrative examples in documents.</p>
<a href="https://www.iana.org/domains/example">More information...</a>
"""

# 场景 2: Icon-only 按钮 — 典型的现代 SPA sidebar
ICON_ONLY_DOM = """
<nav class="sidebar">
  <button class="icon-btn"><svg class="icon fa-home"></svg></button>
  <button class="icon-btn"><svg class="icon fa-search"></svg></button>
  <button class="icon-btn"><svg class="icon fa-settings"></svg></button>
  <button class="icon-btn"><svg class="icon fa-user"></svg></button>
  <button class="icon-btn"><svg class="icon fa-bell"></svg></button>
  <button></button>
  <button></button>
  <button class="material-icon-btn"><svg class="material-icon"></svg></button>
</nav>
<div role="generic">
  <div role="generic">
    <div role="generic">
      <img src="chart1.png">
      <img src="chart2.png">
      <img src="chart3.png">
      <img src="avatar.png">
    </div>
  </div>
</div>
"""

# 场景 3: 自定义组件密集页面 — 如 Angular/React 应用
CUSTOM_COMPONENT_DOM = """
<app-root>
  <app-header>
    <app-nav>
      <app-menu-item></app-menu-item>
      <app-menu-item></app-menu-item>
    </app-nav>
  </app-header>
  <app-dashboard>
    <widget-chart></widget-chart>
    <widget-table></widget-table>
    <custom-button></custom-button>
    <custom-input></custom-input>
  </app-dashboard>
</app-root>
"""

# 场景 4: 混合页面 — 部分元素有标签，部分没有
MIXED_DOM = """
<header>
  <nav>
    <a href="/home">Home</a>
    <a href="/about">About</a>
    <button>Login</button>
    <button class="icon-btn"><svg class="icon fa-menu"></svg></button>
    <button></button>
  </nav>
</header>
<main>
  <h1>Dashboard</h1>
  <p>Welcome to your dashboard</p>
  <img src="profile.png" alt="User profile picture">
  <img src="chart.png">
  <img src="logo.png">
  <div role="generic">
    <button>Submit</button>
    <button class="icon-only"><svg class="fa-trash"></svg></button>
  </div>
</main>
"""


def main():
    scenarios = [
        ("example.com (简单页面)", GOOD_DOM),
        ("Icon-Only SPA (图标按钮)", ICON_ONLY_DOM),
        ("Custom Components (Angular)", CUSTOM_COMPONENT_DOM),
        ("Mixed (混合页面)", MIXED_DOM),
    ]

    print("=" * 72)
    print("  Browser-Use Vision — DOM 置信度分析对比")
    print("=" * 72)

    strategy = AdaptiveVisionStrategy(high_threshold=0.8, low_threshold=0.5)

    for name, dom in scenarios:
        score, signals = assess_dom_confidence(dom)
        decision = strategy.decide(dom)

        print(f"\n{'─' * 72}")
        print(f"  场景: {name}")
        print(f"{'─' * 72}")
        print(f"  DOM 置信度: {score:.2f}")
        print(f"  决策: {decision.value}")
        print(f"  ├─ 可交互元素: {signals.total_interactive}")
        print(f"  ├─ 无标签按钮: {signals.unlabeled_buttons}")
        print(f"  ├─ 无alt图片 : {signals.images_without_alt}")
        print(f"  ├─ icon类元素 : {signals.icon_class_count}")
        print(f"  ├─ generic角色: {signals.generic_role_count}")
        print(f"  ├─ 自定义组件 : {signals.custom_component_count}")
        print(f"  └─ 文本长度   : {signals.total_text_length}")

        # 判断什么信息 LLM 拿不到
        if decision == VisionDecision.SKIP:
            print("\n  ✅ DOM 信息充足，不需要视觉增强")
            print("     → 直接用 DOM 文本就能完成任务")
        elif decision == VisionDecision.LIGHTWEIGHT:
            print("\n  ⚡ 建议轻量视觉 (OCR)")
            print("     → 部分元素缺乏语义，视觉能补充")
        elif decision == VisionDecision.FULL:
            print("\n  🔍 需要完整视觉检测")
            print("     → DOM 信息严重不足，Agent 仅靠 DOM 可能无法正确操作")
            if signals.unlabeled_buttons > 0:
                print(f"     → {signals.unlabeled_buttons} 个按钮没有文字标签")
            if signals.images_without_alt > 0:
                print(f"     → {signals.images_without_alt} 张图片没有 alt 描述")
            if signals.icon_class_count > 0:
                print(f"     → {signals.icon_class_count} 个纯图标元素")

    print(f"\n{'=' * 72}")
    print(f"  策略统计: {json.dumps(strategy.stats, indent=2)}")
    print(f"{'=' * 72}")

    # 生成对比表
    print(f"\n{'─' * 72}")
    print("  结论：自适应策略如何节省开销")
    print(f"{'─' * 72}")
    print("  • 简单页面 (example.com)     → SKIP   → 省掉 ~2s 视觉调用")
    print("  • 图标按钮页面 (SPA)         → FULL   → 视觉增强关键！")
    print("  • 自定义组件 (Angular/React) → FULL   → DOM 结构不反映功能")
    print("  • 混合页面                   → 看情况 → 选择性增强")
    print()


if __name__ == "__main__":
    main()
