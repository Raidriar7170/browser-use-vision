"""
视觉增强版 Agent

继承 browser-use 原生 Agent，在 DOM 处理阶段注入视觉 Grounding 增强。
设计为无侵入式——不修改原仓库任何代码，通过继承和组合实现增强。

兼容 browser-use 0.12.7 API。
"""

from __future__ import annotations

import logging
from typing import Optional

from browser_use.agent.service import Agent
from browser_use.agent.views import AgentStepInfo

from browser_use_vision.adaptive import AdaptiveVisionStrategy, VisionDecision
from browser_use_vision.grounding import DetectedElement, VisualGroundingBackend

logger = logging.getLogger(__name__)


class VisionEnhancedAgent(Agent):
    """
    视觉增强版 Agent

    在原版 Agent 的基础上增加:
    1. 视觉 Grounding：为 DOM 无法区分的元素生成视觉描述
    2. 自适应策略：仅在需要时调用视觉模型，降低开销

    Usage:
            from browser_use_vision import VisionEnhancedAgent
            from browser_use_vision.grounding.florence import FlorenceBackend

            backend = FlorenceBackend(remote_url="http://gpu-server:8100")
            agent = VisionEnhancedAgent(
                    task="Click the shopping cart icon",
                    llm=my_llm,
                    vision_backend=backend,
            )
            result = await agent.run()
    """

    def __init__(
        self,
        *args,
        vision_backend: Optional[VisualGroundingBackend] = None,
        adaptive_strategy: Optional[AdaptiveVisionStrategy] = None,
        enable_adaptive: bool = True,
        vision_high_threshold: float = 0.8,
        vision_low_threshold: float = 0.5,
        force_vision_after_failures: int = 2,
        **kwargs,
    ):
        """
        Args:
                vision_backend: 视觉 Grounding 后端实例
                adaptive_strategy: 自定义自适应策略（不传则创建默认策略）
                enable_adaptive: 是否启用自适应策略（False=每步都用视觉）
                vision_high_threshold: DOM 置信度高阈值（高于此值跳过视觉）
                vision_low_threshold: DOM 置信度低阈值（低于此值完整视觉）
                force_vision_after_failures: 连续失败多少次后强制视觉
        """
        super().__init__(*args, **kwargs)

        self.vision_backend = vision_backend
        self.enable_adaptive = enable_adaptive

        if adaptive_strategy:
            self.adaptive_strategy = adaptive_strategy
        else:
            self.adaptive_strategy = AdaptiveVisionStrategy(
                high_threshold=vision_high_threshold,
                low_threshold=vision_low_threshold,
                force_vision_after_failures=force_vision_after_failures,
            )

        self._vision_enrichments: list[dict] = []

    async def _prepare_context(self, step_info: AgentStepInfo | None = None):  # type: ignore[override]
        """
        重写 _prepare_context，在原有 DOM 处理后注入视觉增强信息。

        流程:
        1. 调用父类获取 BrowserStateSummary
        2. 评估 DOM 置信度 → 决定是否需要视觉
        3. 如果需要 → 视觉检测 → 将描述注入消息上下文
        4. 返回增强后的上下文
        """
        # 1. 原有流程（返回 BrowserStateSummary）
        browser_state_summary = await super()._prepare_context(step_info)

        if not self.vision_backend:
            return browser_state_summary

        # 2. 获取 DOM 文本用于置信度评估
        dom_text = self._extract_dom_text_from_state(browser_state_summary)

        # 3. 自适应决策
        if self.enable_adaptive:
            # 判断是否处于循环（通过 loop_detector 的重复计数和停滞计数）
            loop_detected = False
            if hasattr(self.state, "loop_detector"):
                ld = self.state.loop_detector
                loop_detected = (
                    getattr(ld, "max_repetition_count", 0) >= 3 or getattr(ld, "consecutive_stagnant_pages", 0) >= 2
                )

            decision = self.adaptive_strategy.decide(
                serialized_dom=dom_text,
                consecutive_failures=getattr(self.state, "consecutive_failures", 0),
                loop_detected=loop_detected,
            )
        else:
            decision = VisionDecision.FULL

        # 4. 执行视觉增强
        if decision != VisionDecision.SKIP:
            try:
                await self._enrich_with_vision(browser_state_summary, decision)
            except Exception as e:
                logger.warning(f"Vision enrichment failed (continuing without): {e}")

        return browser_state_summary

    async def _enrich_with_vision(self, browser_state_summary, decision: VisionDecision) -> None:
        """
        用视觉模型增强 browser_state_summary

        将视觉检测结果作为补充信息注入到 Agent 的上下文消息中。
        """
        if not self.vision_backend:
            return

        if not await self.vision_backend.is_ready():
            await self.vision_backend.load_model()

        # 获取当前截图（从 browser_state_summary）
        screenshot = self._get_screenshot_from_state(browser_state_summary)
        if not screenshot:
            return

        # 视觉检测
        elements = await self.vision_backend.detect_elements(screenshot)
        if not elements:
            return

        # 构建视觉增强文本
        vision_text = self._format_vision_elements(elements)

        # 注入到消息中
        self._inject_vision_context(vision_text)

        # 记录统计
        self._vision_enrichments.append(
            {
                "step": getattr(self.state, "n_steps", 0),
                "decision": decision.value,
                "elements_detected": len(elements),
            }
        )
        logger.info(f"Vision enrichment: {len(elements)} elements detected (decision={decision.value})")

    def _get_screenshot_from_state(self, browser_state_summary) -> Optional[bytes]:
        """从 BrowserStateSummary 获取截图数据"""
        try:
            screenshot = getattr(browser_state_summary, "screenshot", None)
            if screenshot is None:
                return None
            if isinstance(screenshot, str):
                # base64 编码
                import base64

                return base64.b64decode(screenshot)
            return screenshot
        except Exception as e:
            logger.warning(f"Failed to get screenshot from state: {e}")
            return None

    def _format_vision_elements(self, elements: list[DetectedElement]) -> str:
        """将视觉检测结果格式化为 LLM 可读的文本"""
        lines = ["[Visual Detection Results - elements identified by vision model]"]
        for i, el in enumerate(elements):
            x1, y1, x2, y2 = el.bbox
            line = f'  Visual[{i}]: {el.label} at ({x1:.2f},{y1:.2f},{x2:.2f},{y2:.2f}) - "{el.description}"'
            if el.ocr_text:
                line += f' text="{el.ocr_text}"'
            line += f" (conf={el.confidence:.2f})"
            lines.append(line)
        return "\n".join(lines)

    def _inject_vision_context(self, vision_text: str) -> None:
        """
        将视觉增强信息注入到 Agent 的消息上下文中。

        兼容 browser-use 0.12.7 的 _message_manager API。
        """
        # 尝试 0.12.7 的 _message_manager
        msg_mgr = getattr(self, "_message_manager", None)
        if msg_mgr is None:
            # 回退到旧版 message_manager
            msg_mgr = getattr(self, "message_manager", None)

        if msg_mgr and hasattr(msg_mgr, "add_state_message"):
            msg_mgr.add_state_message(
                content=vision_text,
                role="system",
            )
        elif msg_mgr and hasattr(msg_mgr, "_add_message"):
            # 另一种注入方式
            from langchain_core.messages import SystemMessage

            msg_mgr._add_message(SystemMessage(content=vision_text))

    def _extract_dom_text_from_state(self, browser_state_summary) -> str:
        """从 BrowserStateSummary 中提取 DOM 文本用于置信度评估"""
        # 0.12.7: BrowserStateSummary 有 dom_text 或 serialized_dom
        if hasattr(browser_state_summary, "dom_text"):
            return browser_state_summary.dom_text or ""
        if hasattr(browser_state_summary, "serialized_dom"):
            return browser_state_summary.serialized_dom or ""
        if hasattr(browser_state_summary, "element_tree_str"):
            return browser_state_summary.element_tree_str or ""
        # fallback
        return str(browser_state_summary)[:2000]

    @property
    def vision_stats(self) -> dict:
        """返回视觉增强统计"""
        return {
            "adaptive_stats": self.adaptive_strategy.stats,
            "enrichments": self._vision_enrichments,
            "total_vision_calls": len(self._vision_enrichments),
        }
