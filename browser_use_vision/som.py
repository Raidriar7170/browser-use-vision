"""
Set of Marks (SoM) — 截图标注模块

在页面截图上为每个可交互元素绘制彩色边框和编号标签，
帮助 LLM 将视觉位置与 DOM 元素精准对应。

参考: WebArena SoM, SeeAct, OmniParser 等工作

用法:
    from browser_use_vision.som import annotate_screenshot
    annotated_b64 = annotate_screenshot(screenshot_b64, selector_map)
"""

from __future__ import annotations

import base64
import io
import logging
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

if TYPE_CHECKING:
    from browser_use.dom.views import DOMSelectorMap

logger = logging.getLogger(__name__)

# 配色方案：高对比度、色盲友好
COLORS = [
    "#FF6B6B",  # 红
    "#4ECDC4",  # 青
    "#FFE66D",  # 黄
    "#95E1D3",  # 浅绿
    "#F38181",  # 珊瑚
    "#AA96DA",  # 紫
    "#A8D8EA",  # 天蓝
    "#FCBAD3",  # 粉
    "#F6A623",  # 橙
    "#7BED9F",  # 翠绿
    "#70A1FF",  # 蓝
    "#FFA502",  # 金
    "#FF4757",  # 深红
    "#2ED573",  # 绿
    "#1E90FF",  # 道奇蓝
    "#ECCC68",  # 土黄
]

# 标签背景色（深色，确保文字可读）
LABEL_BG = "#000000CC"  # 半透明黑


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """将 hex 颜色转换为 RGB"""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 8:  # with alpha
        hex_color = hex_color[:6]
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return (r, g, b)


def annotate_screenshot(
    screenshot_b64: str,
    selector_map: "DOMSelectorMap",
    viewport_offset_y: float = 0.0,
    line_width: int = 2,
    font_size: int = 14,
    max_elements: int = 50,
) -> str:
    """
    在截图上标注可交互元素

    Args:
        screenshot_b64: base64 编码的 PNG 截图
        selector_map: browser-use 的 DOMSelectorMap (backend_node_id -> EnhancedDOMTreeNode)
        viewport_offset_y: 当前页面滚动偏移（CSS pixels）
        line_width: 边框线宽
        font_size: 标签字体大小
        max_elements: 最多标注的元素数量

    Returns:
        标注后的 base64 编码 PNG
    """
    # 解码截图
    img_bytes = base64.b64decode(screenshot_b64)
    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    img_width, img_height = img.size

    # 创建透明叠加层
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # 尝试加载字体
    font = _get_font(font_size)

    # 收集有 bbox 的交互元素
    elements_with_bbox = []
    for backend_node_id, node in selector_map.items():
        bbox = _get_viewport_bbox(node, viewport_offset_y)
        if bbox is None:
            continue

        x, y, w, h = bbox

        # 过滤不在视口内的元素
        if x + w < 0 or y + h < 0 or x > img_width or y > img_height:
            continue

        # 过滤太小的元素（可能是隐藏的）
        if w < 5 or h < 5:
            continue

        elements_with_bbox.append((backend_node_id, x, y, w, h, node))

    # 按位置排序（从上到下，从左到右），让标注更直观
    elements_with_bbox.sort(key=lambda e: (e[2], e[1]))

    # 限制数量
    elements_with_bbox = elements_with_bbox[:max_elements]

    annotated_count = 0
    for idx, (backend_node_id, x, y, w, h, node) in enumerate(elements_with_bbox):
        color = COLORS[idx % len(COLORS)]
        rgb = hex_to_rgb(color)

        # 画边框（带透明度）
        draw.rectangle(
            [x, y, x + w, y + h],
            outline=(*rgb, 200),
            width=line_width,
        )

        # 画标签背景
        label = str(backend_node_id)
        label_bbox = _get_text_bbox(draw, label, font)
        label_w = label_bbox[2] - label_bbox[0] + 6
        label_h = label_bbox[3] - label_bbox[1] + 4

        # 标签放在左上角（如果空间不够则放内部）
        label_x = max(0, x)
        label_y = max(0, y - label_h - 1)
        if label_y < 0:
            label_y = y + 1

        draw.rectangle(
            [label_x, label_y, label_x + label_w, label_y + label_h],
            fill=(*rgb, 220),
        )

        # 画标签文字
        text_color = (0, 0, 0, 255) if _is_light_color(rgb) else (255, 255, 255, 255)
        draw.text(
            (label_x + 3, label_y + 1),
            label,
            fill=text_color,
            font=font,
        )

        annotated_count += 1

    # 合并叠加层
    img = Image.alpha_composite(img, overlay)

    # 转回 RGB 并编码为 base64
    img_rgb = img.convert("RGB")
    buffer = io.BytesIO()
    img_rgb.save(buffer, format="PNG", optimize=True)
    result_b64 = base64.b64encode(buffer.getvalue()).decode()

    logger.info(f"SoM annotation: {annotated_count} elements marked on screenshot")
    return result_b64


def annotate_screenshot_from_state(
    browser_state_summary,
    line_width: int = 2,
    font_size: int = 14,
    max_elements: int = 50,
) -> str | None:
    """
    从 BrowserStateSummary 中提取信息并标注截图

    Returns:
        标注后的 base64 PNG，或 None（如果无法标注）
    """
    screenshot_b64 = browser_state_summary.screenshot
    if not screenshot_b64:
        return None

    selector_map = browser_state_summary.dom_state.selector_map
    if not selector_map:
        return None

    # 获取滚动偏移
    viewport_offset_y = float(browser_state_summary.pixels_above or 0)

    return annotate_screenshot(
        screenshot_b64=screenshot_b64,
        selector_map=selector_map,
        viewport_offset_y=viewport_offset_y,
        line_width=line_width,
        font_size=font_size,
        max_elements=max_elements,
    )


def _get_viewport_bbox(
    node, viewport_offset_y: float
) -> tuple[float, float, float, float] | None:
    """
    获取元素在视口中的 bounding box (x, y, width, height)

    优先使用 clientRects（视口坐标），其次用 bounds（文档坐标 - 滚动偏移）
    """
    snapshot = getattr(node, "snapshot_node", None)
    if snapshot is None:
        return None

    # 优先 clientRects（已经是视口坐标）
    client_rects = getattr(snapshot, "clientRects", None)
    if client_rects and client_rects.width > 0 and client_rects.height > 0:
        return (client_rects.x, client_rects.y, client_rects.width, client_rects.height)

    # 其次 bounds（文档坐标，需要减去滚动偏移）
    bounds = getattr(snapshot, "bounds", None)
    if bounds and bounds.width > 0 and bounds.height > 0:
        return (bounds.x, bounds.y - viewport_offset_y, bounds.width, bounds.height)

    return None


def _get_font(size: int):
    """获取字体，优先系统字体，回退到默认"""
    font_paths = [
        "/System/Library/Fonts/Menlo.ttc",  # macOS
        "/System/Library/Fonts/SFNSMono.ttf",  # macOS
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",  # Linux
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",  # Linux
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    # 回退到默认字体
    try:
        return ImageFont.truetype("DejaVuSansMono.ttf", size)
    except (OSError, IOError):
        return ImageFont.load_default()


def _get_text_bbox(draw: ImageDraw.ImageDraw, text: str, font) -> tuple:
    """获取文字边界框"""
    try:
        return draw.textbbox((0, 0), text, font=font)
    except Exception:
        # 估算
        return (0, 0, len(text) * 8, 14)


def _is_light_color(rgb: tuple[int, int, int]) -> bool:
    """判断颜色是否为浅色（用于决定文字颜色）"""
    r, g, b = rgb
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return luminance > 160
