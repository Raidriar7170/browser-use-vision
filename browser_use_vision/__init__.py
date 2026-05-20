"""
Browser-Use Vision Enhancement Module
为 browser-use 框架提供视觉理解增强能力
"""

from browser_use_vision.enhanced_agent import VisionEnhancedAgent
from browser_use_vision.grounding.base import DetectedElement, VisualGroundingBackend

__all__ = [
	'VisionEnhancedAgent',
	'DetectedElement',
	'VisualGroundingBackend',
]

__version__ = '0.1.0'
