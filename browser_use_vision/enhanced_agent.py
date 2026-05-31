"""
视觉增强版 Agent

继承 browser-use 原生 Agent，在 DOM 处理阶段注入视觉 Grounding 增强。
设计为无侵入式——不修改原仓库任何代码，通过继承和组合实现增强。

核心能力:
1. SoM（Set of Marks）标注 — 在截图上画框+编号，帮助 LLM 精准定位元素
2. 视觉 Grounding（Florence-2 OCR） — 识别 DOM 无法区分的视觉内容
3. 自适应策略 — 仅在需要时启用视觉增强，降低开销

兼容 browser-use 0.12.7 API。
"""

from __future__ import annotations

import logging
from typing import Optional

from browser_use.agent.service import Agent
from browser_use.agent.views import AgentStepInfo

from browser_use_vision.adaptive import AdaptiveVisionStrategy, VisionDecision
from browser_use_vision.grounding import DetectedElement, VisualGroundingBackend
from browser_use_vision.som import annotate_screenshot_from_state

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
        enable_som: bool = True,
        enable_dense_caption: bool = False,
        som_max_elements: int = 50,
        som_line_width: int = 2,
        som_font_size: int = 14,
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
                enable_som: 是否启用 SoM 截图标注（在截图上画框+编号）
                enable_dense_caption: 是否启用 Dense Region Caption（False=仅 OCR）
                som_max_elements: SoM 最多标注的元素数量
                som_line_width: SoM 边框线宽
                som_font_size: SoM 标签字体大小
                vision_high_threshold: DOM 置信度高阈值（高于此值跳过视觉）
                vision_low_threshold: DOM 置信度低阈值（低于此值完整视觉）
                force_vision_after_failures: 连续失败多少次后强制视觉
        """
        super().__init__(*args, **kwargs)

        self.vision_backend = vision_backend
        self.enable_adaptive = enable_adaptive
        self.enable_som = enable_som
        self.enable_dense_caption = enable_dense_caption
        self.som_max_elements = som_max_elements
        self.som_line_width = som_line_width
        self.som_font_size = som_font_size

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
        2. 应用 SoM 标注（在截图上画框+编号）
        3. 评估 DOM 置信度 → 决定是否需要视觉 Grounding
        4. 如果需要 → 视觉检测 → 将描述注入消息上下文
        5. 返回增强后的上下文
        """
        # 1. 原有流程（返回 BrowserStateSummary）
        browser_state_summary = await super()._prepare_context(step_info)

        # 2. SoM 标注 — 在截图上为每个可交互元素画框+编号
        if self.enable_som:
            try:
                annotated = annotate_screenshot_from_state(
                    browser_state_summary,
                    line_width=self.som_line_width,
                    font_size=self.som_font_size,
                    max_elements=self.som_max_elements,
                )
                if annotated:
                    browser_state_summary.screenshot = annotated
                    logger.debug("SoM annotation applied to screenshot")
            except Exception as e:
                logger.warning(f"SoM annotation failed (continuing without): {e}")

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

        策略:
        - FULL: OCR + Dense Region Caption（完整视觉信息）
        - LIGHTWEIGHT: 仅 OCR（快速补充文字信息）

        OCR 结果特别有用于:
        - icon-only 按钮（DOM 中无文字，但视觉上有图标含义）
        - canvas/SVG 渲染的文字
        - 图片中嵌入的文字内容
        """
        if not self.vision_backend:
            return

        if not await self.vision_backend.is_ready():
            await self.vision_backend.load_model()

        # 获取当前截图（从 browser_state_summary）
        screenshot = self._get_screenshot_from_state(browser_state_summary)
        if not screenshot:
            return

        vision_parts = []
        total_items = 0
        # 统一收集所有视觉检测（caption + 0-1 bbox），供「视觉→DOM」桥匹配。
        vision_dets: list[dict] = []

        # OCR with Region — 识别页面上所有文字及位置
        if hasattr(self.vision_backend, "ocr_with_region"):
            try:
                ocr_results = await self.vision_backend.ocr_with_region(screenshot)
                if ocr_results:
                    ocr_text = self._format_ocr_results(ocr_results)
                    vision_parts.append(ocr_text)
                    total_items += len(ocr_results)
                    for r in ocr_results:
                        text = (r.get("text") or "").strip()
                        if text:
                            vision_dets.append({"caption": text, "bbox": r.get("bbox"), "source": "ocr"})
            except Exception as e:
                logger.warning(f"OCR failed: {e}")

        # Dense Region Caption — 仅在 FULL 模式下执行
        if decision == VisionDecision.FULL and self.enable_dense_caption and hasattr(self.vision_backend, "dense_region_caption"):
            try:
                region_results = await self.vision_backend.dense_region_caption(screenshot)
                if region_results:
                    region_text = self._format_region_results(region_results)
                    vision_parts.append(region_text)
                    total_items += len(region_results)
                    for r in region_results:
                        cap = (r.get("caption") or "").strip()
                        if cap:
                            vision_dets.append({"caption": cap, "bbox": r.get("bbox"), "source": "region"})
            except Exception as e:
                logger.warning(f"Dense region caption failed: {e}")

        # 回退：如果后端不支持 OCR，用旧的 detect_elements
        if not vision_parts:
            try:
                elements = await self.vision_backend.detect_elements(screenshot)
                if elements:
                    vision_parts.append(self._format_vision_elements(elements))
                    total_items += len(elements)
                    for el in elements:
                        cap = el.description or el.label or ""
                        if el.ocr_text:
                            cap = f"{cap} ({el.ocr_text})".strip()
                        if cap:
                            vision_dets.append({"caption": cap, "bbox": el.bbox, "source": "detect"})
            except Exception as e:
                logger.warning(f"Element detection failed: {e}")

        if not vision_parts:
            return

        # 视觉→DOM 桥：把视觉 caption 按 bbox 匹配回可点击的 DOM 元素 index，
        # 注入「Element [id]: 视觉看到 ...」这类可直接行动的摘要（置于最前）。
        try:
            matches = self._match_vision_to_dom(browser_state_summary, vision_dets, screenshot)
            if matches:
                vision_parts.insert(0, self._format_grounded_elements(matches))
        except Exception as e:
            logger.warning(f"Vision→DOM grounding failed (continuing without): {e}")

        # 合并所有视觉信息并注入
        vision_text = "\n\n".join(vision_parts)
        self._inject_vision_context(vision_text)

        # 记录统计
        self._vision_enrichments.append(
            {
                "step": getattr(self.state, "n_steps", 0),
                "decision": decision.value,
                "items_detected": total_items,
            }
        )
        logger.info(f"Vision enrichment: {total_items} items (decision={decision.value})")

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

    def _format_ocr_results(self, ocr_results: list[dict]) -> str:
        """将 OCR 结果格式化为 LLM 可读的文本"""
        lines = ["[Vision OCR Results - text detected in screenshot by Florence-2]"]
        for i, r in enumerate(ocr_results):
            text = r.get("text", "")
            bbox = r.get("bbox", [0, 0, 0, 0])
            lines.append(f'  OCR[{i}]: "{text}" at ({bbox[0]:.3f},{bbox[1]:.3f},{bbox[2]:.3f},{bbox[3]:.3f})')
        return "\n".join(lines)

    def _format_region_results(self, region_results: list[dict]) -> str:
        """将 Dense Region Caption 结果格式化为 LLM 可读的文本"""
        lines = ["[Vision Region Descriptions - areas identified by Florence-2]"]
        for i, r in enumerate(region_results):
            caption = r.get("caption", "")
            bbox = r.get("bbox", [0, 0, 0, 0])
            lines.append(f'  Region[{i}]: "{caption}" at ({bbox[0]:.3f},{bbox[1]:.3f},{bbox[2]:.3f},{bbox[3]:.3f})')
        return "\n".join(lines)

    def _match_vision_to_dom(
        self,
        browser_state_summary,
        vision_dets: list[dict],
        screenshot: bytes,
        iou_threshold: float = 0.25,
    ) -> list[dict]:
        """把视觉检测（caption + 0-1 bbox）按位置匹配回可点击的 DOM 元素 index。

        视觉管线产出的 caption（"a play button"）若只带裸 bbox，LLM 无法对应到
        browser-use 序列化里的 ``[id]``——只能靠空间邻近猜，密集相似图标必失配。
        本方法用 IoU + 中心互含把每个 DOM 交互元素匹配到最贴合的视觉检测，
        让注入文本能直接给出「点 Element [id]」。

        坐标约定与 SoM 一致：DOM 元素取视口像素 bbox（``_get_viewport_bbox``），
        除以截图像素尺寸归一化到 0-1，再与视觉 0-1 bbox 比较。
        """
        from browser_use_vision.som import _get_viewport_bbox

        dom_state = getattr(browser_state_summary, "dom_state", None)
        selector_map = getattr(dom_state, "selector_map", None) if dom_state is not None else None
        if not selector_map or not vision_dets:
            return []

        import io as _io

        from PIL import Image

        img = Image.open(_io.BytesIO(screenshot))
        img_w, img_h = img.size
        if not img_w or not img_h:
            return []

        offset_y = float(getattr(browser_state_summary, "pixels_above", 0) or 0)

        matches: list[dict] = []
        for backend_node_id, node in selector_map.items():
            vb = _get_viewport_bbox(node, offset_y)
            if vb is None:
                continue
            x, y, w, h = vb
            if w < 5 or h < 5:
                continue
            dom_bbox = (x / img_w, y / img_h, (x + w) / img_w, (y + h) / img_h)
            dom_area = (dom_bbox[2] - dom_bbox[0]) * (dom_bbox[3] - dom_bbox[1])

            best = None
            best_iou = 0.0
            for det in vision_dets:
                vbbox = det.get("bbox")
                if not vbbox or len(vbbox) < 4:
                    continue
                vbbox = tuple(vbbox)
                iou = VisualGroundingBackend._compute_iou(dom_bbox, vbbox)
                # 命中条件：真有重叠（IoU），或一个检测「坐落在」该元素上——
                # 但拒绝面积远大于元素的粗检测（如整页 region），否则会把同一句无用
                # caption 摊到一排按钮上，制造噪声而非 grounding。
                vis_area = max(0.0, (vbbox[2] - vbbox[0])) * max(0.0, (vbbox[3] - vbbox[1]))
                localized = vis_area <= self._GROUNDING_AREA_RATIO * dom_area
                qualifies = iou >= iou_threshold or (localized and self._center_contained(dom_bbox, vbbox))
                if qualifies and (iou > best_iou or best is None):
                    best_iou = iou
                    best = det

            if best is not None:
                matches.append(
                    {
                        "index": backend_node_id,
                        "caption": best["caption"],
                        "source": best.get("source", ""),
                        "overlap": round(best_iou, 2),
                    }
                )

        return matches

    # 视觉检测面积相对 DOM 元素的上限倍数：超过则视为「过粗」（整页/大块 region），
    # 不通过中心互含判定命中——避免把粗 caption 摊到一排相似元素上。
    _GROUNDING_AREA_RATIO = 4.0

    @staticmethod
    def _center_contained(box_a: tuple, box_b: tuple) -> bool:
        """任一 box 的中心点落在另一 box 内即视为命中（小图标 bbox 常不严格重叠）。"""
        ax = (box_a[0] + box_a[2]) / 2
        ay = (box_a[1] + box_a[3]) / 2
        bx = (box_b[0] + box_b[2]) / 2
        by = (box_b[1] + box_b[3]) / 2
        a_has_b = box_a[0] <= bx <= box_a[2] and box_a[1] <= by <= box_a[3]
        b_has_a = box_b[0] <= ax <= box_b[2] and box_b[1] <= ay <= box_b[3]
        return a_has_b or b_has_a

    def _format_grounded_elements(self, matches: list[dict]) -> str:
        """把「视觉→DOM」匹配结果格式化为 LLM 可直接行动的摘要。"""
        lines = ["[Vision→DOM Grounding — click these element indices]"]
        for m in matches:
            src = f", {m['source']}" if m.get("source") else ""
            lines.append(f'  Element [{m["index"]}]: vision sees "{m["caption"]}" (overlap {m["overlap"]:.2f}{src})')
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
        """从 BrowserStateSummary 中提取序列化 DOM 文本用于置信度评估。

        browser-use 0.12.x 把 DOM 放在 ``dom_state.llm_representation()``（索引格式
        ``*[id]<button ...>``），BrowserStateSummary 本身并没有 dom_text/serialized_dom
        等属性。早期版本错误地按这些不存在的属性查找并回退到 ``str(state)[:2000]``——
        一个截断的对象 repr，导致置信度评估永远拿不到真实 DOM、恒判 SKIP。
        """
        dom_state = getattr(browser_state_summary, "dom_state", None)
        if dom_state is not None and hasattr(dom_state, "llm_representation"):
            try:
                return dom_state.llm_representation() or ""
            except Exception:  # noqa: BLE001
                return ""

        # 后向兼容：旧版本可能直接暴露这些属性
        for attr in ("dom_text", "serialized_dom", "element_tree_str"):
            if hasattr(browser_state_summary, attr):
                return getattr(browser_state_summary, attr) or ""

        # 读不到真实 DOM 时返回空串，绝不拿对象 repr 当 DOM——
        # 空串由 assess_dom_confidence 判为低置信（倾向 FULL）。
        return ""

    @property
    def vision_stats(self) -> dict:
        """返回视觉增强统计"""
        return {
            "adaptive_stats": self.adaptive_strategy.stats,
            "enrichments": self._vision_enrichments,
            "total_vision_calls": len(self._vision_enrichments),
        }
