"""
单元测试: Grounding 基础模块
"""

import pytest

from browser_use_vision.grounding import DetectedElement, VisualGroundingBackend


class TestDetectedElement:
    """DetectedElement 模型测试"""

    def test_basic_creation(self):
        el = DetectedElement(
            bbox=(0.1, 0.2, 0.3, 0.4),
            label="button",
            description="A blue submit button",
            confidence=0.95,
        )
        assert el.label == "button"
        assert el.confidence == 0.95

    def test_center_property(self):
        el = DetectedElement(
            bbox=(0.0, 0.0, 1.0, 1.0),
            label="button",
            description="test",
            confidence=0.5,
        )
        assert el.center == (0.5, 0.5)

    def test_area_property(self):
        el = DetectedElement(
            bbox=(0.0, 0.0, 0.5, 0.5),
            label="button",
            description="test",
            confidence=0.5,
        )
        assert abs(el.area - 0.25) < 1e-6

    def test_ocr_text_default(self):
        el = DetectedElement(
            bbox=(0.1, 0.1, 0.2, 0.2),
            label="text",
            description="text region",
            confidence=0.8,
        )
        assert el.ocr_text == ""

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            DetectedElement(
                bbox=(0, 0, 1, 1),
                label="x",
                description="x",
                confidence=1.5,  # 超出范围
            )


class TestIoUComputation:
    """IoU 计算测试"""

    def test_perfect_overlap(self):
        iou = VisualGroundingBackend._compute_iou((0, 0, 1, 1), (0, 0, 1, 1))
        assert abs(iou - 1.0) < 1e-6

    def test_no_overlap(self):
        iou = VisualGroundingBackend._compute_iou((0, 0, 0.5, 0.5), (0.6, 0.6, 1, 1))
        assert iou == 0.0

    def test_partial_overlap(self):
        iou = VisualGroundingBackend._compute_iou((0, 0, 0.5, 0.5), (0.25, 0.25, 0.75, 0.75))
        # intersection = 0.25*0.25 = 0.0625
        # area_a = 0.25, area_b = 0.25, union = 0.25+0.25-0.0625 = 0.4375
        expected = 0.0625 / 0.4375
        assert abs(iou - expected) < 1e-6

    def test_contained(self):
        iou = VisualGroundingBackend._compute_iou((0, 0, 1, 1), (0.25, 0.25, 0.75, 0.75))
        # intersection = 0.5*0.5 = 0.25
        # area_a = 1.0, area_b = 0.25, union = 1.0
        assert abs(iou - 0.25) < 1e-6
