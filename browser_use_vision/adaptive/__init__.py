"""
自适应视觉策略

根据 DOM 信息的质量动态决定是否调用视觉模型，降低不必要的开销。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class VisionDecision(Enum):
	"""视觉调用决策"""

	SKIP = 'skip'  # DOM 足够，不需要视觉
	LIGHTWEIGHT = 'lightweight'  # 仅 OCR，不做完整检测
	FULL = 'full'  # 完整视觉 Grounding


@dataclass
class DOMConfidenceSignals:
	"""DOM 置信度信号"""

	total_interactive: int = 0  # 可交互元素总数
	unlabeled_buttons: int = 0  # 无文字的按钮数
	images_without_alt: int = 0  # 缺少 alt 的图片数
	generic_role_count: int = 0  # role=generic 的元素数
	icon_class_count: int = 0  # 类名含 icon/svg 的元素数
	custom_component_count: int = 0  # 自定义 Web 组件数
	total_text_length: int = 0  # DOM 文本总长度


def assess_dom_confidence(serialized_dom: str) -> tuple[float, DOMConfidenceSignals]:
	"""
	评估 DOM 序列化文本的信息充分度

	分析 DOM 文本中是否有足够的语义信息让 LLM 做出正确决策。
	返回 0-1 的置信度分数和详细信号。

	低置信度场景:
	- 大量无文字的按钮/链接 → LLM 无法区分
	- img 标签缺少 alt 属性 → 纯图像无语义
	- 自定义组件占比高 → DOM 结构不反映功能
	- 可交互元素过少 → 可能漏检
	"""
	signals = DOMConfidenceSignals()
	lines = serialized_dom.split('\n')

	for line in lines:
		line_lower = line.lower()

		# 统计可交互元素
		if any(tag in line_lower for tag in ['<button', '<a ', '<input', '<select', '<textarea', 'role="button"']):
			signals.total_interactive += 1

		# 无文字的按钮: <button.../> 或 <button></button> 没有内部文本
		if re.search(r'<button[^>]*/?>\s*$', line_lower) or re.search(r'<button[^>]*>\s*</button>', line_lower):
			signals.unlabeled_buttons += 1

		# 缺少 alt 的图片
		if '<img' in line_lower and 'alt=' not in line_lower:
			signals.images_without_alt += 1

		# generic role
		if 'role="generic"' in line_lower or 'role=generic' in line_lower:
			signals.generic_role_count += 1

		# icon 类名
		if re.search(r'class="[^"]*(?:icon|svg|fa-|material-icon)[^"]*"', line_lower):
			signals.icon_class_count += 1

		# 自定义组件（非标准 HTML 标签）
		custom_match = re.search(r'<([a-z]+-[a-z]+)', line_lower)
		if custom_match:
			signals.custom_component_count += 1

	# 文本总长度
	signals.total_text_length = len(serialized_dom)

	# 计算置信度
	score = 1.0

	# 惩罚项
	if signals.total_interactive > 0:
		unlabeled_ratio = signals.unlabeled_buttons / signals.total_interactive
		score -= unlabeled_ratio * 0.5  # 无标签按钮比例越高，越需要视觉

	if signals.images_without_alt > 1:
		score -= min(0.3, signals.images_without_alt * 0.05)

	if signals.icon_class_count > 3:
		score -= min(0.35, signals.icon_class_count * 0.05)

	if signals.generic_role_count > 5:
		score -= min(0.2, signals.generic_role_count * 0.02)

	if signals.custom_component_count > 3:
		score -= min(0.25, signals.custom_component_count * 0.03)

	# 过少的交互元素也可疑（可能漏检）
	if signals.total_interactive < 3 and signals.total_text_length > 500:
		score -= 0.2

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
			logger.info(f'Forcing FULL vision: {consecutive_failures} consecutive failures')
			self._record(VisionDecision.FULL)
			return VisionDecision.FULL

		if loop_detected:
			logger.info('Forcing FULL vision: loop detected')
			self._record(VisionDecision.FULL)
			return VisionDecision.FULL

		# 基于 DOM 置信度决策
		confidence, signals = assess_dom_confidence(serialized_dom)
		logger.info(f'DOM confidence: {confidence:.2f} | unlabeled_buttons={signals.unlabeled_buttons}, '
			f'no_alt_images={signals.images_without_alt}, icons={signals.icon_class_count}')

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
			'total_steps': total,
			'vision_calls': self._vision_calls,
			'skip_calls': self._skip_calls,
			'vision_ratio': self._vision_calls / total if total > 0 else 0,
			'savings_ratio': self._skip_calls / total if total > 0 else 0,
		}
