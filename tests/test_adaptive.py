"""
单元测试: 自适应视觉策略

样例串均采用 browser-use ``dom_state.llm_representation()`` 的真实索引格式
（``[id]<tag ...>``，``*``=新元素，文本子节点缩进显示），而非原始 HTML——
因为生产中门控评估的就是这种序列化文本。
"""

from browser_use_vision.adaptive import (
    AdaptiveVisionStrategy,
    VisionDecision,
    assess_dom_confidence,
)

# ── 真实格式样例 ──────────────────────────────────────────────

# icon-only 播放器：清一色裸 [id]<button />，DOM 无任何可读标签 → 需视觉
ICON_ONLY_DOM = "\n".join(
    [
        "[4]<button />",
        "[5]<button />",
        "[6]<button />",
        "[7]<button />",
        "[8]<button />",
        "[9]<button />",
    ]
)

# 文本/aria 丰富页：链接带文本子节点、输入带属性 → DOM 足够，可跳过视觉
TEXT_RICH_DOM = "\n".join(
    [
        "[73]<a />",
        "\tBooks to Scrape",
        "[94]<a />",
        "\tHome",
        "[552]<a title=A Light in the Attic />",
        "\tA Light in the ...",
        "[570]<button type=submit />",
        "\tAdd to basket",
        "[9]<input type=checkbox checked=false />",
        "checkbox 1",
    ]
)

# 混合页：少量带文本按钮 + 多个裸 div 色块 → 倾向视觉（非 SKIP）
MIXED_DOM = "\n".join(
    [
        "[3]<div />",
        "[4]<div />",
        "[5]<div />",
        "[6]<div />",
        "[9]<button />",
        "\tApply Theme",
        "[10]<button />",
        "\tReset",
    ]
)


class TestDOMConfidenceAssessment:
    """DOM 置信度评估测试（真实索引格式）"""

    def test_icon_only_low_confidence(self):
        """清一色裸图标按钮 → 低置信度、全 icon_only"""
        confidence, signals = assess_dom_confidence(ICON_ONLY_DOM)
        assert confidence < 0.5
        assert signals.total_interactive == 6
        assert signals.labeled_elements == 0
        assert signals.icon_only_elements == 6

    def test_text_rich_high_confidence(self):
        """链接带文本、输入带属性 → 高置信度"""
        confidence, signals = assess_dom_confidence(TEXT_RICH_DOM)
        assert confidence >= 0.8
        assert signals.labeled_elements == signals.total_interactive
        assert signals.icon_only_elements == 0

    def test_mixed_moderate_confidence(self):
        """混合页 → 中等置信度（既非全高也非全低）"""
        confidence, signals = assess_dom_confidence(MIXED_DOM)
        assert 0.4 <= confidence < 0.8
        assert signals.icon_only_elements >= 3
        assert signals.labeled_elements >= 2

    def test_empty_dom_low_confidence(self):
        """空串（读不到真实 DOM）→ 低分，绝不误判为高置信"""
        confidence, signals = assess_dom_confidence("")
        assert confidence < 0.5
        assert signals.total_interactive == 0

    def test_collapsed_svg_counts_as_icon(self):
        """折叠的 <svg> 计入 svg_collapsed 与 icon_only"""
        dom = "[50]<svg /> <!-- SVG content collapsed -->\n[5]<button />\n[6]<button />"
        _confidence, signals = assess_dom_confidence(dom)
        assert signals.svg_collapsed == 1
        assert signals.icon_only_elements == 3

    def test_decorative_i_excluded(self):
        """装饰性 <i>（评分星标）不计入交互统计，避免拖低文本页"""
        dom = "\n".join(
            [
                "[552]<a title=A Light in the Attic />",
                "\tA Light in the ...",
                "[562]<i />",
                "[563]<i />",
                "[564]<i />",
            ]
        )
        confidence, signals = assess_dom_confidence(dom)
        assert signals.total_interactive == 1  # 仅 <a>，三个 <i> 被排除
        assert confidence >= 0.8


class TestAdaptiveStrategy:
    """自适应策略测试"""

    def test_skip_on_text_rich(self):
        """文本丰富 DOM → SKIP"""
        strategy = AdaptiveVisionStrategy(high_threshold=0.8, low_threshold=0.5)
        assert strategy.decide(TEXT_RICH_DOM) == VisionDecision.SKIP

    def test_full_on_icon_only(self):
        """icon-only DOM → FULL"""
        strategy = AdaptiveVisionStrategy(high_threshold=0.8, low_threshold=0.5)
        assert strategy.decide(ICON_ONLY_DOM) == VisionDecision.FULL

    def test_non_skip_on_mixed(self):
        """混合页 → 至少 LIGHTWEIGHT（不 SKIP）"""
        strategy = AdaptiveVisionStrategy(high_threshold=0.8, low_threshold=0.5)
        assert strategy.decide(MIXED_DOM) in (VisionDecision.FULL, VisionDecision.LIGHTWEIGHT)

    def test_non_skip_on_empty(self):
        """空串 → 非 SKIP（读不到 DOM 时倾向视觉）"""
        strategy = AdaptiveVisionStrategy(high_threshold=0.8, low_threshold=0.5)
        assert strategy.decide("") != VisionDecision.SKIP

    def test_force_on_failures(self):
        """连续失败 → 强制 FULL（即便 DOM 高置信）"""
        strategy = AdaptiveVisionStrategy(force_vision_after_failures=2)
        assert strategy.decide(TEXT_RICH_DOM, consecutive_failures=3) == VisionDecision.FULL

    def test_force_on_loop(self):
        """循环检测 → 强制 FULL"""
        strategy = AdaptiveVisionStrategy()
        assert strategy.decide(TEXT_RICH_DOM, loop_detected=True) == VisionDecision.FULL

    def test_stats_tracking(self):
        """统计追踪"""
        strategy = AdaptiveVisionStrategy(high_threshold=0.8, low_threshold=0.5)
        strategy.decide(TEXT_RICH_DOM)  # SKIP
        strategy.decide(ICON_ONLY_DOM)  # FULL
        stats = strategy.stats
        assert stats["total_steps"] == 2
        assert stats["vision_calls"] >= 1
        assert stats["skip_calls"] >= 1
