"""
视觉 Grounding 抽象接口

定义视觉检测后端的统一接口，支持 OmniParser / Florence-2 等多种后端实现。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class DetectedElement(BaseModel):
    """视觉检测到的 UI 元素"""

    bbox: tuple[float, float, float, float] = Field(description="归一化坐标 (x1, y1, x2, y2)，值域 [0, 1]")
    label: str = Field(description="元素类型: button, icon, image, text, input, link, etc.")
    description: str = Field(description='自然语言描述，如 "红色购物车图标按钮"')
    confidence: float = Field(ge=0.0, le=1.0, description="检测置信度")
    ocr_text: str = Field(default="", description="OCR 识别出的文字内容")

    @property
    def center(self) -> tuple[float, float]:
        """返回元素中心点坐标（归一化）"""
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2, (y1 + y2) / 2)

    @property
    def area(self) -> float:
        """返回元素面积（归一化）"""
        x1, y1, x2, y2 = self.bbox
        return (x2 - x1) * (y2 - y1)


class VisualGroundingBackend(ABC):
    """
    视觉 Grounding 后端抽象基类

    所有视觉检测后端（OmniParser, Florence-2 等）都需要实现此接口。
    """

    @abstractmethod
    async def detect_elements(self, screenshot: bytes, threshold: float = 0.3) -> list[DetectedElement]:
        """
        检测截图中的所有 UI 元素

        Args:
                screenshot: PNG 格式的截图字节
                threshold: 置信度阈值，低于此值的检测结果会被过滤

        Returns:
                检测到的 UI 元素列表
        """
        ...

    @abstractmethod
    async def describe_region(self, screenshot: bytes, bbox: tuple[float, float, float, float]) -> str:
        """
        为截图中指定区域生成自然语言描述

        Args:
                screenshot: PNG 格式的截图字节
                bbox: 目标区域坐标 (x1, y1, x2, y2)，归一化

        Returns:
                自然语言描述字符串
        """
        ...

    @abstractmethod
    async def is_ready(self) -> bool:
        """检查后端是否就绪（模型已加载等）"""
        ...

    async def match_dom_to_visual(
        self,
        dom_elements: list[dict],
        visual_elements: list[DetectedElement],
        iou_threshold: float = 0.3,
    ) -> list[dict]:
        """
        将 DOM 元素与视觉检测元素进行匹配

        通过 IoU（交并比）将 DOM 提取的元素与视觉检测的元素对应起来，
        为 DOM 元素补充视觉描述信息。

        Args:
                dom_elements: DOM 元素列表，每个元素需包含 'bbox' 字段
                visual_elements: 视觉检测到的元素列表
                iou_threshold: IoU 匹配阈值

        Returns:
                增强后的 DOM 元素列表，匹配成功的元素会新增 'visual_description' 字段
        """
        enriched = []
        for dom_el in dom_elements:
            dom_bbox = dom_el.get("bbox")
            if not dom_bbox:
                enriched.append(dom_el)
                continue

            best_match = None
            best_iou = 0.0
            for vis_el in visual_elements:
                iou = self._compute_iou(dom_bbox, vis_el.bbox)
                if iou > best_iou and iou >= iou_threshold:
                    best_iou = iou
                    best_match = vis_el

            result = dict(dom_el)
            if best_match:
                result["visual_description"] = best_match.description
                result["visual_label"] = best_match.label
                result["visual_confidence"] = best_match.confidence
                if best_match.ocr_text:
                    result["visual_ocr"] = best_match.ocr_text
            enriched.append(result)

        return enriched

    @staticmethod
    def _compute_iou(box_a: tuple, box_b: tuple) -> float:
        """计算两个 bbox 的 IoU"""
        x1 = max(box_a[0], box_b[0])
        y1 = max(box_a[1], box_b[1])
        x2 = min(box_a[2], box_b[2])
        y2 = min(box_a[3], box_b[3])

        intersection = max(0, x2 - x1) * max(0, y2 - y1)
        if intersection == 0:
            return 0.0

        area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
        area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
        union = area_a + area_b - intersection

        return intersection / union if union > 0 else 0.0
