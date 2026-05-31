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
    agent.enable_dense_caption = overrides.get("enable_dense_caption", True)
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

    def test_dom_state_llm_representation(self):
        """主路径: browser-use 0.12.x 把真实 DOM 放在 dom_state.llm_representation()"""
        agent = _make_agent_instance()
        dom_state = SimpleNamespace(llm_representation=lambda: "[4]<button />")
        state = SimpleNamespace(dom_state=dom_state)
        result = agent._extract_dom_text_from_state(state)
        assert result == "[4]<button />"

    def test_fallback_returns_empty(self):
        """读不到真实 DOM 的对象 → 返回空串，绝不拿对象 repr 当 DOM"""
        agent = _make_agent_instance()
        state = {"some": "dict"}
        result = agent._extract_dom_text_from_state(state)
        assert result == ""

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

    def test_dense_caption_disabled_skips_regions(self):
        """enable_dense_caption=False 时 FULL 模式也不调用 dense_region_caption"""

        async def _run():
            backend = AsyncMock()
            backend.is_ready = AsyncMock(return_value=True)
            backend.ocr_with_region = AsyncMock(
                return_value=[{"text": "Play", "bbox": [0.1, 0.1, 0.2, 0.2]}]
            )
            backend.dense_region_caption = AsyncMock(
                return_value=[{"caption": "a button", "bbox": [0.1, 0.1, 0.2, 0.2]}]
            )

            agent = _make_agent_instance(vision_backend=backend, enable_dense_caption=False)
            agent._inject_vision_context = MagicMock()

            state = SimpleNamespace(screenshot=b"fake-png-data")
            await agent._enrich_with_vision(state, VisionDecision.FULL)

            backend.ocr_with_region.assert_awaited_once()
            backend.dense_region_caption.assert_not_awaited()
            agent._inject_vision_context.assert_called_once()

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

    def test_dense_caption_config_default(self):
        agent = _make_agent_instance()
        assert agent.enable_dense_caption is True

    def test_dense_caption_config_disabled(self):
        agent = _make_agent_instance(enable_dense_caption=False)
        assert agent.enable_dense_caption is False


# ===========================================================================
# Test: _match_vision_to_dom / _format_grounded_elements（视觉→DOM 桥）
# ===========================================================================


def _png_bytes(w: int, h: int) -> bytes:
    """生成已知尺寸的 PNG 字节，供 _match_vision_to_dom 解码取尺寸。"""
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _node(x: int, y: int, w: int, h: int):
    """构造带视口 bbox 的合成 DOM 节点（clientRects 路径）。"""
    return SimpleNamespace(
        snapshot_node=SimpleNamespace(clientRects=SimpleNamespace(x=x, y=y, width=w, height=h))
    )


def _state(selector_map: dict, pixels_above: float = 0.0):
    return SimpleNamespace(
        dom_state=SimpleNamespace(selector_map=selector_map),
        pixels_above=pixels_above,
    )


class TestMatchVisionToDom:
    """测试视觉检测 → 可点击 DOM index 的匹配"""

    def test_overlapping_caption_attaches_to_correct_index(self):
        agent = _make_agent_instance()
        # 100x100 截图：元素 42 在 (10,10,30,30)→0.1..0.3，元素 43 远在 (70,70,90,90)
        selector_map = {42: _node(10, 10, 20, 20), 43: _node(70, 70, 20, 20)}
        state = _state(selector_map)
        vision_dets = [{"caption": "skip to next track icon", "bbox": [0.1, 0.1, 0.3, 0.3], "source": "region"}]

        matches = agent._match_vision_to_dom(state, vision_dets, _png_bytes(100, 100))

        idx_to_cap = {m["index"]: m["caption"] for m in matches}
        assert idx_to_cap.get(42) == "skip to next track icon"
        assert 43 not in idx_to_cap  # 远处元素不应匹配

    def test_no_overlap_no_match(self):
        agent = _make_agent_instance()
        selector_map = {42: _node(10, 10, 20, 20)}
        state = _state(selector_map)
        # 视觉检测落在右下角，与 DOM 元素无交集且中心互不含
        vision_dets = [{"caption": "something", "bbox": [0.7, 0.7, 0.9, 0.9], "source": "region"}]

        matches = agent._match_vision_to_dom(state, vision_dets, _png_bytes(100, 100))
        assert matches == []

    def test_center_contained_small_target_matches(self):
        """小图标与「尺寸相当」的检测 IoU 偏低，但中心互含 → 应匹配"""
        agent = _make_agent_instance()
        # 元素 7：小 (50,50,10,10)→0.5..0.6，面积 0.01
        selector_map = {7: _node(50, 50, 10, 10)}
        state = _state(selector_map)
        # 检测略大但在 4x 面积内（0.48..0.62 面积≈0.0196），含元素中心 → 命中
        vision_dets = [{"caption": "eraser tool icon", "bbox": [0.48, 0.48, 0.62, 0.62], "source": "region"}]

        matches = agent._match_vision_to_dom(state, vision_dets, _png_bytes(100, 100))
        assert len(matches) == 1
        assert matches[0]["index"] == 7
        assert matches[0]["caption"] == "eraser tool icon"

    def test_coarse_region_rejected(self):
        """整页/大块 region（面积远大于元素）不应靠中心互含摊到小元素上"""
        agent = _make_agent_instance()
        selector_map = {7: _node(50, 50, 10, 10)}  # 面积 0.01
        state = _state(selector_map)
        # 巨大 region 0.1..0.9 面积 0.64 >> 4*0.01 → 拒绝；IoU 也极低
        vision_dets = [{"caption": "music player app interface", "bbox": [0.1, 0.1, 0.9, 0.9], "source": "region"}]
        matches = agent._match_vision_to_dom(state, vision_dets, _png_bytes(100, 100))
        assert matches == []

    def test_iou_beats_contained_only(self):
        """同一元素有多个候选时，IoU 高者胜出"""
        agent = _make_agent_instance()
        selector_map = {5: _node(10, 10, 20, 20)}  # 0.1..0.3
        state = _state(selector_map)
        vision_dets = [
            {"caption": "loose big region", "bbox": [0.0, 0.0, 0.9, 0.9], "source": "region"},  # 含中心但 IoU 低
            {"caption": "tight play icon", "bbox": [0.1, 0.1, 0.3, 0.3], "source": "region"},  # IoU=1
        ]
        matches = agent._match_vision_to_dom(state, vision_dets, _png_bytes(100, 100))
        assert len(matches) == 1
        assert matches[0]["caption"] == "tight play icon"

    def test_empty_inputs_return_empty(self):
        agent = _make_agent_instance()
        assert agent._match_vision_to_dom(_state({}), [], _png_bytes(100, 100)) == []
        assert agent._match_vision_to_dom(_state({5: _node(10, 10, 20, 20)}), [], _png_bytes(100, 100)) == []

    def test_format_grounded_elements(self):
        agent = _make_agent_instance()
        matches = [
            {"index": 42, "caption": "skip to next track icon", "source": "region", "overlap": 0.61},
            {"index": 37, "caption": "eraser tool icon", "source": "region", "overlap": 0.0},
        ]
        out = agent._format_grounded_elements(matches)
        assert "[Vision→DOM Grounding" in out
        assert "Element [42]" in out
        assert "skip to next track icon" in out
        assert "Element [37]" in out
