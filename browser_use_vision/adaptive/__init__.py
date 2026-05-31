"""
自适应视觉策略

根据 DOM 信息的质量动态决定是否调用视觉模型，降低不必要的开销。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class VisionDecision(Enum):
    """视觉调用决策"""

    SKIP = "skip"  # DOM 足够，不需要视觉
    LIGHTWEIGHT = "lightweight"  # 仅 OCR，不做完整检测
    FULL = "full"  # 完整视觉 Grounding


@dataclass
class DOMConfidenceSignals:
    """DOM 置信度信号（基于 browser-use 索引序列化格式）"""

    total_interactive: int = 0  # 可交互/被索引元素总数
    labeled_elements: int = 0  # 有 label 属性或文本子节点的元素数
    icon_only_elements: int = 0  # 纯图标元素数（无 label 属性、无文本子节点）
    svg_collapsed: int = 0  # 被折叠的 <svg> 元素数
    total_text_length: int = 0  # DOM 文本总长度


# browser-use 索引序列化的一行交互元素形如:
#   [4]<button />
#   \t[45]<div />
#   |SHADOW(open)|*[137]<input type=range ... />
#   [50]<svg /> <!-- SVG content collapsed -->
# 即: 可选缩进 + 可选 |SHADOW...| 前缀 + 可选 * + [数字] + <标签 属性...>
_INTERACTIVE_RE = re.compile(
    r"^(?P<indent>\s*)(?:\|[^|]*\|)?\*?\[\d+\]<(?P<tag>[a-zA-Z][a-zA-Z0-9-]*)(?P<attrs>[^>]*)"
)

# 表明元素自带语义标签的属性（出现任一即视为 labeled）
_LABEL_ATTRS = (
    "aria-label=",
    "alt=",
    "title=",
    "placeholder=",
    "value=",
    "name=",
    "compound_components=",
    "type=",
    "checked=",
)


def _indent_width(s: str) -> int:
    return len(s) - len(s.lstrip())


def _has_label_attr(attrs: str) -> bool:
    low = attrs.lower()
    return any(a in low for a in _LABEL_ATTRS)


def assess_dom_confidence(serialized_dom: str) -> tuple[float, DOMConfidenceSignals]:
    """
    评估 browser-use 序列化 DOM（``dom_state.llm_representation()`` 的索引格式）的信息充分度。

    返回 0-1 的置信度分数与详细信号。分数越高表示 DOM 文本本身越能让 LLM 正确定位，
    越低表示越依赖视觉（icon-only 按钮、折叠的 svg 等）。

    判别逻辑（按真实索引格式，而非原始 HTML）:
    - 一行匹配 ``[id]<tag ...>`` 视为一个被索引的交互元素。
    - 该元素若带 label 属性（aria-label/alt/title/placeholder/value/type/compound_components 等），
      或其后续缩进子节点中存在可读文本 / 带 label 的子元素 → labeled。
    - 否则（裸 ``[id]<button />`` / 折叠的 ``<svg>``）→ icon-only，强烈指示需要视觉。
    - 空串（读不到真实 DOM）→ 低分，倾向 FULL，绝不因「读不到」而误判 SKIP。
    """
    signals = DOMConfidenceSignals()
    signals.total_text_length = len(serialized_dom)

    if not serialized_dom.strip():
        # 读不到真实 DOM：宁可多调一次视觉，也不要盲目 SKIP。
        return 0.3, signals

    lines = serialized_dom.split("\n")

    # 预解析每行：是否交互、缩进、属性、是否为纯文本行。
    parsed = []  # (is_interactive, indent, attrs, tag, is_text)
    for line in lines:
        m = _INTERACTIVE_RE.match(line)
        if m:
            parsed.append((True, _indent_width(line), m.group("attrs"), m.group("tag").lower(), False))
        else:
            is_text = bool(line.strip())
            parsed.append((False, _indent_width(line), "", "", is_text))

    n = len(parsed)
    for i, (is_inter, indent, attrs, tag, _is_text) in enumerate(parsed):
        if not is_inter:
            continue
        # 装饰性图标标签（如 font-awesome 评分星标 <i>）几乎从不是动作目标，
        # 计入会让文本丰富页（books 的星标）被噪声拖低分。排除之。
        if tag == "i":
            continue
        signals.total_interactive += 1
        if tag == "svg" or "svg content collapsed" in lines[i].lower():
            signals.svg_collapsed += 1

        labeled = _has_label_attr(attrs)
        if not labeled:
            # 扫描所有缩进更深的后代行：任一可读文本 / 带 label 的交互子元素 → labeled。
            for j in range(i + 1, n):
                cj_inter, cj_indent, cj_attrs, _cj_tag, cj_text = parsed[j]
                if cj_indent <= indent:
                    break  # 回到同级/上级，后代扫描结束
                if cj_text:
                    labeled = True
                    break
                if cj_inter and _has_label_attr(cj_attrs):
                    labeled = True
                    break

        if labeled:
            signals.labeled_elements += 1
        else:
            signals.icon_only_elements += 1

    if signals.total_interactive == 0:
        # 有文本但无任何被索引的交互元素：可能是纯阅读页，也可能解析异常。
        # 给中等偏低分，避免无脑 SKIP。
        return 0.4, signals

    labeled_ratio = signals.labeled_elements / signals.total_interactive
    # 基线 0.4，labeled 占比线性抬升至 1.0；折叠 svg 额外小幅惩罚。
    score = 0.4 + 0.6 * labeled_ratio
    score -= min(0.15, signals.svg_collapsed * 0.05)
    score = max(0.0, min(1.0, score))
    return score, signals


class AdaptiveVisionStrategy:
    """
    自适应视觉策略

    根据 DOM 置信度和 Agent 执行状态决定是否调用视觉模型。

    策略:
    - DOM 置信度 > high_threshold → SKIP（纯 DOM 足够）
    - DOM 置信度在 low~high 之间 → LIGHTWEIGHT（仅 OCR）
    - DOM 置信度 < low_threshold → FULL（完整视觉 Grounding）
    - Agent 连续失败 → 强制 FULL
    - Agent 检测到循环 → 强制 FULL
    """

    def __init__(
        self,
        high_threshold: float = 0.8,
        low_threshold: float = 0.5,
        force_vision_after_failures: int = 2,
    ):
        self.high_threshold = high_threshold
        self.low_threshold = low_threshold
        self.force_vision_after_failures = force_vision_after_failures
        self._consecutive_failures = 0
        self._step_decisions: list[VisionDecision] = []
        self._vision_calls = 0
        self._skip_calls = 0

    def decide(
        self,
        serialized_dom: str,
        consecutive_failures: int = 0,
        loop_detected: bool = False,
    ) -> VisionDecision:
        """
        决定当前步是否需要视觉模型

        Args:
                serialized_dom: 序列化的 DOM 文本
                consecutive_failures: Agent 连续失败次数
                loop_detected: 是否检测到操作循环

        Returns:
                VisionDecision
        """
        # 强制视觉的条件
        if consecutive_failures >= self.force_vision_after_failures:
            logger.info(f"Forcing FULL vision: {consecutive_failures} consecutive failures")
            self._record(VisionDecision.FULL)
            return VisionDecision.FULL

        if loop_detected:
            logger.info("Forcing FULL vision: loop detected")
            self._record(VisionDecision.FULL)
            return VisionDecision.FULL

        # 基于 DOM 置信度决策
        confidence, signals = assess_dom_confidence(serialized_dom)
        logger.info(
            f"DOM confidence: {confidence:.2f} | interactive={signals.total_interactive}, "
            f"labeled={signals.labeled_elements}, icon_only={signals.icon_only_elements}, "
            f"svg_collapsed={signals.svg_collapsed}"
        )

        if confidence >= self.high_threshold:
            self._record(VisionDecision.SKIP)
            return VisionDecision.SKIP
        elif confidence >= self.low_threshold:
            self._record(VisionDecision.LIGHTWEIGHT)
            return VisionDecision.LIGHTWEIGHT
        else:
            self._record(VisionDecision.FULL)
            return VisionDecision.FULL

    def _record(self, decision: VisionDecision) -> None:
        self._step_decisions.append(decision)
        if decision == VisionDecision.SKIP:
            self._skip_calls += 1
        else:
            self._vision_calls += 1

    @property
    def stats(self) -> dict:
        """返回统计数据"""
        total = len(self._step_decisions)
        return {
            "total_steps": total,
            "vision_calls": self._vision_calls,
            "skip_calls": self._skip_calls,
            "vision_ratio": self._vision_calls / total if total > 0 else 0,
            "savings_ratio": self._skip_calls / total if total > 0 else 0,
        }
