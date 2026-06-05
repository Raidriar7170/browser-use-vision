"""
Browser-Use Vision Enhancement Module
为 browser-use 框架提供视觉理解增强能力
"""

from browser_use_vision.grounding.base import DetectedElement, VisualGroundingBackend
from browser_use_vision.som import annotate_screenshot, annotate_screenshot_from_state


def __getattr__(name: str):
    """Lazy imports to avoid requiring browser_use or heavy deps at import time."""
    if name == "VisionEnhancedAgent":
        from browser_use_vision.enhanced_agent import VisionEnhancedAgent

        return VisionEnhancedAgent
    if name == "BrowserUseVisionGrounder":
        from browser_use_vision.adapter import BrowserUseVisionGrounder

        return BrowserUseVisionGrounder
    if name == "ground":
        from browser_use_vision.adapter import ground

        return ground
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "VisionEnhancedAgent",
    "BrowserUseVisionGrounder",
    "ground",
    "DetectedElement",
    "VisualGroundingBackend",
    "annotate_screenshot",
    "annotate_screenshot_from_state",
]

__version__ = "0.4.0"
