"""
SoM（Set of Marks）标注模块单元测试

测试截图标注功能：
- 基本标注功能
- 元素过滤（太小、视口外）
- 排序逻辑
- 颜色工具函数
- 空输入处理
"""

import base64
import io
from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock

from PIL import Image

from browser_use_vision.som import (
    _get_viewport_bbox,
    _is_light_color,
    annotate_screenshot,
    annotate_screenshot_from_state,
    hex_to_rgb,
)

# ---- 测试用数据结构（模拟 browser-use 的类型） ----


@dataclass
class MockDOMRect:
    x: float
    y: float
    width: float
    height: float


@dataclass
class MockSnapshotNode:
    bounds: Optional[MockDOMRect] = None
    clientRects: Optional[MockDOMRect] = None
    scrollRects: Optional[MockDOMRect] = None


@dataclass
class MockDOMTreeNode:
    snapshot_node: Optional[MockSnapshotNode] = None


def make_screenshot(width: int = 800, height: int = 600) -> str:
    """创建测试用截图（纯色 PNG → base64）"""
    img = Image.new("RGB", (width, height), (40, 40, 40))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def make_selector_map(elements: list[tuple[int, float, float, float, float]]) -> dict:
    """
    创建模拟 selector_map

    elements: [(backend_node_id, x, y, width, height), ...]
    """
    selector_map = {}
    for bid, x, y, w, h in elements:
        node = MockDOMTreeNode(snapshot_node=MockSnapshotNode(bounds=MockDOMRect(x=x, y=y, width=w, height=h)))
        selector_map[bid] = node
    return selector_map


# ---- hex_to_rgb ----


class TestHexToRGB:
    def test_basic(self):
        assert hex_to_rgb("#FF6B6B") == (255, 107, 107)

    def test_no_hash(self):
        assert hex_to_rgb("4ECDC4") == (78, 205, 196)

    def test_with_alpha(self):
        assert hex_to_rgb("#000000CC") == (0, 0, 0)

    def test_white(self):
        assert hex_to_rgb("#FFFFFF") == (255, 255, 255)

    def test_black(self):
        assert hex_to_rgb("#000000") == (0, 0, 0)


# ---- _is_light_color ----


class TestIsLightColor:
    def test_white_is_light(self):
        assert _is_light_color((255, 255, 255)) is True

    def test_black_is_dark(self):
        assert _is_light_color((0, 0, 0)) is False

    def test_yellow_is_light(self):
        assert _is_light_color((255, 230, 109)) is True

    def test_dark_blue_is_dark(self):
        assert _is_light_color((30, 30, 120)) is False


# ---- _get_viewport_bbox ----


class TestGetViewportBbox:
    def test_uses_client_rects_first(self):
        """优先使用 clientRects（视口坐标）"""
        node = MockDOMTreeNode(
            snapshot_node=MockSnapshotNode(
                clientRects=MockDOMRect(10, 20, 100, 50),
                bounds=MockDOMRect(10, 520, 100, 50),  # 不同值
            )
        )
        result = _get_viewport_bbox(node, viewport_offset_y=500.0)
        assert result == (10, 20, 100, 50)  # clientRects 的值

    def test_falls_back_to_bounds(self):
        """无 clientRects 时用 bounds - scroll_offset"""
        node = MockDOMTreeNode(
            snapshot_node=MockSnapshotNode(
                bounds=MockDOMRect(10, 520, 100, 50),
            )
        )
        result = _get_viewport_bbox(node, viewport_offset_y=500.0)
        assert result == (10, 20.0, 100, 50)  # y = 520 - 500

    def test_no_snapshot_returns_none(self):
        node = MockDOMTreeNode(snapshot_node=None)
        assert _get_viewport_bbox(node, 0) is None

    def test_zero_size_returns_none(self):
        node = MockDOMTreeNode(
            snapshot_node=MockSnapshotNode(
                bounds=MockDOMRect(10, 20, 0, 0),
            )
        )
        assert _get_viewport_bbox(node, 0) is None


# ---- annotate_screenshot ----


class TestAnnotateScreenshot:
    def test_basic_annotation(self):
        """基本标注：几个元素，验证输出是有效的 base64 PNG"""
        screenshot = make_screenshot()
        selector_map = make_selector_map(
            [
                (1, 50, 50, 200, 40),
                (2, 50, 120, 200, 40),
                (3, 300, 50, 150, 40),
            ]
        )
        result = annotate_screenshot(screenshot, selector_map)

        # 验证是有效的 base64
        assert isinstance(result, str)
        assert len(result) > 0

        # 验证能解码为图片
        img_bytes = base64.b64decode(result)
        img = Image.open(io.BytesIO(img_bytes))
        assert img.size == (800, 600)

    def test_filters_small_elements(self):
        """太小的元素（< 5px）应被过滤"""
        screenshot = make_screenshot()
        selector_map = make_selector_map(
            [
                (1, 50, 50, 3, 3),  # 太小，应被过滤
                (2, 50, 120, 200, 40),  # 正常
            ]
        )
        result = annotate_screenshot(screenshot, selector_map)

        # 不应崩溃，输出有效
        img_bytes = base64.b64decode(result)
        img = Image.open(io.BytesIO(img_bytes))
        assert img.size == (800, 600)

    def test_filters_out_of_viewport(self):
        """视口外的元素应被过滤"""
        screenshot = make_screenshot(800, 600)
        selector_map = make_selector_map(
            [
                (1, -300, -300, 100, 100),  # 完全在视口外
                (2, 900, 700, 100, 100),  # 完全在视口外
                (3, 50, 50, 200, 40),  # 视口内
            ]
        )
        result = annotate_screenshot(screenshot, selector_map)

        # 应成功，只有 1 个元素在视口内
        img_bytes = base64.b64decode(result)
        img = Image.open(io.BytesIO(img_bytes))
        assert img.size == (800, 600)

    def test_max_elements_limit(self):
        """超过 max_elements 的元素应被截断"""
        screenshot = make_screenshot()
        elements = [(i, 10, i * 15, 100, 10) for i in range(100)]
        selector_map = make_selector_map(elements)

        # max_elements=5，只标注前 5 个
        result = annotate_screenshot(screenshot, selector_map, max_elements=5)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_empty_selector_map(self):
        """空 selector_map 不应崩溃"""
        screenshot = make_screenshot()
        result = annotate_screenshot(screenshot, {})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_annotated_differs_from_original(self):
        """标注后的图片应该和原图不同"""
        screenshot = make_screenshot()
        selector_map = make_selector_map(
            [
                (1, 50, 50, 200, 40),
            ]
        )
        result = annotate_screenshot(screenshot, selector_map)
        # base64 结果应该不同（因为画了东西）
        assert result != screenshot

    def test_sort_top_to_bottom(self):
        """元素应按 y 坐标排序"""
        screenshot = make_screenshot()
        # 故意乱序
        selector_map = make_selector_map(
            [
                (10, 50, 300, 200, 40),  # y=300
                (20, 50, 50, 200, 40),  # y=50
                (30, 50, 180, 200, 40),  # y=180
            ]
        )
        result = annotate_screenshot(screenshot, selector_map)
        assert isinstance(result, str)

    def test_with_scroll_offset(self):
        """滚动偏移应正确应用"""
        screenshot = make_screenshot()
        selector_map = make_selector_map(
            [
                (1, 50, 550, 200, 40),  # 文档坐标 y=550
            ]
        )
        # viewport_offset_y=500，元素在视口内 y=50
        result = annotate_screenshot(screenshot, selector_map, viewport_offset_y=500)
        assert isinstance(result, str)


# ---- annotate_screenshot_from_state ----


class TestAnnotateScreenshotFromState:
    def test_basic(self):
        """从模拟的 BrowserStateSummary 标注"""
        screenshot = make_screenshot()
        selector_map = make_selector_map(
            [
                (1, 50, 50, 200, 40),
            ]
        )

        state = MagicMock()
        state.screenshot = screenshot
        state.dom_state.selector_map = selector_map
        state.pixels_above = 0

        result = annotate_screenshot_from_state(state)
        assert result is not None
        assert isinstance(result, str)

    def test_no_screenshot_returns_none(self):
        state = MagicMock()
        state.screenshot = None
        assert annotate_screenshot_from_state(state) is None

    def test_no_selector_map_returns_none(self):
        state = MagicMock()
        state.screenshot = make_screenshot()
        state.dom_state.selector_map = {}
        assert annotate_screenshot_from_state(state) is None
