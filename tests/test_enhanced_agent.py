"""
单元测试: VisionEnhancedAgent

测试核心逻辑，不需要真实浏览器或 LLM。
所有外部依赖（browser-use Agent, vision backend）均 mock。
"""

from __future__ import annotations

import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from browser_use_vision.adaptive import AdaptiveVisionStrategy, VisionDecision
from browser_use_vision.grounding import DetectedElement

# ---------------------------------------------------------------------------
# Helpers — 我们不能真正构造 VisionEnhancedAgent（需要 LLM + browser 实例），
# 所以直接实例化方法所在的类、或 import 方法单独测试。
# ---------------------------------------------------------------------------


def _make_agent_instance(**overrides):
    """
    用 mock 构造一个 VisionEnhancedAgent 实例（绕过 Agent.__init__）
    """
    from browser_use_vision.enhanced_agent import VisionEnhancedAgent

    # 绕过 parent __init__，直接设置属性
    agent = object.__new__(VisionEnhancedAgent)

    # 默认属性
    agent.vision_backend = overrides.get("vision_backend", None)
    agent.enable_adaptive = overrides.get("enable_adaptive", True)
    agent.enable_som = overrides.get("enable_som", True)
    agent.som_max_elements = overrides.get("som_max_elements", 50)
    agent.som_line_width = overrides.get("som_line_width", 2)
    agent.som_font_size = overrides.get("som_font_size", 14)
    agent.adaptive_strategy = overrides.get(
        "adaptive_strategy",
        AdaptiveVisionStrategy(
            high_threshold=0.8,
            low_threshold=0.5,
            force_vision_after_failures=2,
        ),
    )
    agent._vision_enrichments = []
    agent.state = SimpleNamespace(n_steps=0, consecutive_failures=0)

    return agent


# ===========================================================================
# Test: _format_vision_elements
# ===========================================================================


class TestFormatVisionElements:
    """测试视觉检测结果格式化"""

    def test_single_element(self):
        agent = _make_agent_instance()
        elements = [
            DetectedElement(
                bbox=(0.1, 0.2, 0.3, 0.4),
                label="button",
                description="A blue submit button",
                confidence=0.95,
            )
        ]
        result = agent._format_vision_elements(elements)
        assert "Visual[0]" in result
        assert "button" in result
        assert "A blue submit button" in result
        assert "0.95" in result

    def test_multiple_elements(self):
        agent = _make_agent_instance()
        elements = [
            DetectedElement(
                bbox=(0.0, 0.0, 0.5, 0.5),
                label="icon",
                description="play icon",
                confidence=0.8,
            ),
            DetectedElement(
                bbox=(0.5, 0.0, 1.0, 0.5),
                label="icon",
                description="pause icon",
                confidence=0.7,
            ),
        ]
        result = agent._format_vision_elements(elements)
        assert "Visual[0]" in result
        assert "Visual[1]" in result
        assert "play icon" in result
        assert "pause icon" in result

    def test_element_with_ocr_text(self):
        agent = _make_agent_instance()
        elements = [
            DetectedElement(
                bbox=(0.1, 0.1, 0.5, 0.3),
                label="text",
                description="text region",
                confidence=0.9,
                ocr_text="Submit Order",
            )
        ]
        result = agent._format_vision_elements(elements)
        assert 'text="Submit Order"' in result

    def test_empty_elements(self):
        agent = _make_agent_instance()
        result = agent._format_vision_elements([])
        assert "[Visual Detection Results" in result
        assert "Visual[0]" not in result


# ===========================================================================
# Test: _format_ocr_results
# ===========================================================================


class TestFormatOCRResults:
    """测试 OCR 结果格式化"""

    def test_basic_ocr(self):
        agent = _make_agent_instance()
        ocr_results = [
            {"text": "Next Track", "bbox": [0.1, 0.2, 0.3, 0.4]},
            {"text": "Volume Up", "bbox": [0.5, 0.6, 0.7, 0.8]},
        ]
        result = agent._format_ocr_results(ocr_results)
        assert "OCR[0]" in result
        assert "OCR[1]" in result
        assert '"Next Track"' in result
        assert '"Volume Up"' in result

    def test_empty_ocr(self):
        agent = _make_agent_instance()
        result = agent._format_ocr_results([])
        assert "[Vision OCR Results" in result
        assert "OCR[0]" not in result

    def test_ocr_missing_fields(self):
        """bbox 缺失时应有默认值"""
        agent = _make_agent_instance()
        ocr_results = [{"text": "Hello"}]
        result = agent._format_ocr_results(ocr_results)
        assert '"Hello"' in result


# ===========================================================================
# Test: _format_region_results
# ===========================================================================


class TestFormatRegionResults:
    """测试 Dense Region Caption 格式化"""

    def test_basic_regions(self):
        agent = _make_agent_instance()
        regions = [
            {"caption": "a red play button icon", "bbox": [0.1, 0.2, 0.3, 0.4]},
            {"caption": "navigation sidebar", "bbox": [0.0, 0.0, 0.2, 1.0]},
        ]
        result = agent._format_region_results(regions)
        assert "Region[0]" in result
        assert "Region[1]" in result
        assert "red play button" in result
        assert "navigation sidebar" in result

    def test_empty_regions(self):
        agent = _make_agent_instance()
        result = agent._format_region_results([])
        assert "[Vision Region Descriptions" in result


# ===========================================================================
# Test: _extract_dom_text_from_state
# ===========================================================================


class TestExtractDOMText:
    """测试从 BrowserStateSummary 提取 DOM 文本"""

    def test_dom_text_attr(self):
        agent = _make_agent_instance()
        state = SimpleNamespace(dom_text="<button>Click me</button>")
        result = agent._extract_dom_text_from_state(state)
        assert result == "<button>Click me</button>"

    def test_serialized_dom_attr(self):
        agent = _make_agent_instance()
        state = SimpleNamespace(serialized_dom="[button] Click me")
        result = agent._extract_dom_text_from_state(state)
        assert result == "[button] Click me"

    def test_element_tree_str_attr(self):
        agent = _make_agent_instance()
        state = SimpleNamespace(element_tree_str="<div><button/></div>")
        result = agent._extract_dom_text_from_state(state)
        assert result == "<div><button/></div>"

    def test_fallback_to_str(self):
        agent = _make_agent_instance()
        state = {"some": "dict"}
        result = agent._extract_dom_text_from_state(state)
        assert len(result) > 0
        assert len(result) <= 2000

    def test_none_attr(self):
        agent = _make_agent_instance()
        state = SimpleNamespace(dom_text=None, serialized_dom=None)
        result = agent._extract_dom_text_from_state(state)
        assert isinstance(result, str)


# ===========================================================================
# Test: _get_screenshot_from_state
# ===========================================================================


class TestGetScreenshotFromState:
    """测试截图提取"""

    def test_bytes_screenshot(self):
        agent = _make_agent_instance()
        raw = b"\x89PNG\r\n\x1a\n"
        state = SimpleNamespace(screenshot=raw)
        result = agent._get_screenshot_from_state(state)
        assert result == raw

    def test_base64_screenshot(self):
        agent = _make_agent_instance()
        raw = b"test-image-data"
        b64 = base64.b64encode(raw).decode()
        state = SimpleNamespace(screenshot=b64)
        result = agent._get_screenshot_from_state(state)
        assert result == raw

    def test_none_screenshot(self):
        agent = _make_agent_instance()
        state = SimpleNamespace(screenshot=None)
        result = agent._get_screenshot_from_state(state)
        assert result is None

    def test_no_screenshot_attr(self):
        agent = _make_agent_instance()
        state = SimpleNamespace()
        result = agent._get_screenshot_from_state(state)
        assert result is None


# ===========================================================================
# Test: vision_stats property
# ===========================================================================


class TestVisionStats:
    """测试统计属性"""

    def test_empty_stats(self):
        agent = _make_agent_instance()
        stats = agent.vision_stats
        assert stats["total_vision_calls"] == 0
        assert stats["enrichments"] == []

    def test_stats_after_enrichment(self):
        agent = _make_agent_instance()
        agent._vision_enrichments.append({"step": 1, "decision": "full", "items_detected": 5})
        agent._vision_enrichments.append({"step": 3, "decision": "lightweight", "items_detected": 2})
        stats = agent.vision_stats
        assert stats["total_vision_calls"] == 2
        assert len(stats["enrichments"]) == 2


# ===========================================================================
# Test: _enrich_with_vision (async, with mock backend)
# ===========================================================================


class TestEnrichWithVision:
    """测试视觉增强流程"""

    def test_full_enrichment_with_ocr_and_regions(self):
        """FULL 模式: OCR + Dense Region Caption"""

        async def _run():
            backend = AsyncMock()
            backend.is_ready = AsyncMock(return_value=True)
            backend.ocr_with_region = AsyncMock(
                return_value=[
                    {"text": "Play", "bbox": [0.1, 0.1, 0.2, 0.2]},
                    {"text": "Next", "bbox": [0.3, 0.1, 0.4, 0.2]},
                ]
            )
            backend.dense_region_caption = AsyncMock(
                return_value=[
                    {"caption": "a play button", "bbox": [0.1, 0.1, 0.2, 0.2]},
                ]
            )

            agent = _make_agent_instance(vision_backend=backend)
            agent._inject_vision_context = MagicMock()

            state = SimpleNamespace(screenshot=b"fake-png-data")
            await agent._enrich_with_vision(state, VisionDecision.FULL)

            # 验证: OCR 和 region 都被调用
            backend.ocr_with_region.assert_awaited_once()
            backend.dense_region_caption.assert_awaited_once()

            # 验证: 注入了视觉上下文
            agent._inject_vision_context.assert_called_once()
            injected_text = agent._inject_vision_context.call_args[0][0]
            assert "OCR[0]" in injected_text
            assert "Region[0]" in injected_text

            # 验证: 统计记录
            assert len(agent._vision_enrichments) == 1
            assert agent._vision_enrichments[0]["decision"] == "full"
            assert agent._vision_enrichments[0]["items_detected"] == 3

        asyncio.run(_run())

    def test_lightweight_skips_regions(self):
        """LIGHTWEIGHT 模式: 仅 OCR，不做 Dense Region"""

        async def _run():
            backend = AsyncMock()
            backend.is_ready = AsyncMock(return_value=True)
            backend.ocr_with_region = AsyncMock(return_value=[{"text": "Settings", "bbox": [0.5, 0.5, 0.6, 0.6]}])
            backend.dense_region_caption = AsyncMock()

            agent = _make_agent_instance(vision_backend=backend)
            agent._inject_vision_context = MagicMock()

            state = SimpleNamespace(screenshot=b"fake-png-data")
            await agent._enrich_with_vision(state, VisionDecision.LIGHTWEIGHT)

            backend.ocr_with_region.assert_awaited_once()
            backend.dense_region_caption.assert_not_awaited()

        asyncio.run(_run())

    def test_no_screenshot_returns_early(self):
        """没有截图时应该直接返回"""

        async def _run():
            backend = AsyncMock()
            backend.is_ready = AsyncMock(return_value=True)

            agent = _make_agent_instance(vision_backend=backend)
            state = SimpleNamespace(screenshot=None)
            await agent._enrich_with_vision(state, VisionDecision.FULL)

            assert len(agent._vision_enrichments) == 0

        asyncio.run(_run())

    def test_fallback_to_detect_elements(self):
        """OCR 不可用时回退到 detect_elements"""

        async def _run():
            backend = AsyncMock()
            backend.is_ready = AsyncMock(return_value=True)
            # 没有 ocr_with_region 方法
            del backend.ocr_with_region
            del backend.dense_region_caption
            backend.detect_elements = AsyncMock(
                return_value=[
                    DetectedElement(
                        bbox=(0.1, 0.1, 0.3, 0.3),
                        label="button",
                        description="submit button",
                        confidence=0.9,
                    )
                ]
            )

            agent = _make_agent_instance(vision_backend=backend)
            agent._inject_vision_context = MagicMock()

            state = SimpleNamespace(screenshot=b"fake-png-data")
            await agent._enrich_with_vision(state, VisionDecision.FULL)

            backend.detect_elements.assert_awaited_once()
            agent._inject_vision_context.assert_called_once()

        asyncio.run(_run())

    def test_no_backend_returns_immediately(self):
        """没有 backend 时应立即返回"""

        async def _run():
            agent = _make_agent_instance(vision_backend=None)
            state = SimpleNamespace(screenshot=b"fake-png-data")
            await agent._enrich_with_vision(state, VisionDecision.FULL)
            assert len(agent._vision_enrichments) == 0

        asyncio.run(_run())

    def test_backend_error_handled_gracefully(self):
        """后端出错时不应崩溃"""

        async def _run():
            backend = AsyncMock()
            backend.is_ready = AsyncMock(return_value=True)
            backend.ocr_with_region = AsyncMock(side_effect=Exception("Connection refused"))
            backend.dense_region_caption = AsyncMock(side_effect=Exception("Also broken"))
            backend.detect_elements = AsyncMock(side_effect=Exception("Everything broken"))

            agent = _make_agent_instance(vision_backend=backend)
            agent._inject_vision_context = MagicMock()

            state = SimpleNamespace(screenshot=b"fake-png-data")
            await agent._enrich_with_vision(state, VisionDecision.FULL)

            # 全部出错时不应崩溃，也不应注入上下文
            agent._inject_vision_context.assert_not_called()

        asyncio.run(_run())


# ===========================================================================
# Test: Adaptive strategy integration
# ===========================================================================


class TestAdaptiveIntegration:
    """测试自适应策略与 Agent 的集成"""

    def test_default_strategy_created(self):
        agent = _make_agent_instance()
        assert isinstance(agent.adaptive_strategy, AdaptiveVisionStrategy)

    def test_custom_strategy(self):
        custom = AdaptiveVisionStrategy(high_threshold=0.9, low_threshold=0.3, force_vision_after_failures=5)
        agent = _make_agent_instance(adaptive_strategy=custom)
        assert agent.adaptive_strategy is custom
        assert agent.adaptive_strategy.high_threshold == 0.9

    def test_som_config_defaults(self):
        agent = _make_agent_instance()
        assert agent.som_max_elements == 50
        assert agent.som_line_width == 2
        assert agent.som_font_size == 14

    def test_som_config_custom(self):
        agent = _make_agent_instance(som_max_elements=20, som_line_width=3, som_font_size=18)
        assert agent.som_max_elements == 20
        assert agent.som_line_width == 3
        assert agent.som_font_size == 18
