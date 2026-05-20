"""
视觉 Grounding 抽象接口（base 模块）

re-export from grounding package for clean imports:
    from browser_use_vision.grounding.base import DetectedElement, VisualGroundingBackend
"""

from browser_use_vision.grounding import DetectedElement, VisualGroundingBackend

__all__ = ["DetectedElement", "VisualGroundingBackend"]
