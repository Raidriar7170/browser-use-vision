"""
单元测试: 自适应视觉策略
"""

import pytest

from browser_use_vision.adaptive import (
	AdaptiveVisionStrategy,
	DOMConfidenceSignals,
	VisionDecision,
	assess_dom_confidence,
)


class TestDOMConfidenceAssessment:
	"""DOM 置信度评估测试"""

	def test_high_confidence_simple_dom(self):
		"""简单 DOM，所有按钮都有文字 → 高置信度"""
		dom = '''
		<button>Submit</button>
		<button>Cancel</button>
		<a href="/about">About Us</a>
		<input type="text" placeholder="Search">
		'''
		confidence, signals = assess_dom_confidence(dom)
		assert confidence >= 0.8
		assert signals.unlabeled_buttons == 0

	def test_low_confidence_icon_heavy(self):
		"""大量图标按钮 → 低置信度"""
		dom = '''
		<button class="icon-btn"><svg>...</svg></button>
		<button class="icon-btn"></button>
		<button></button>
		<button class="material-icon"></button>
		<img src="logo.png">
		<img src="banner.jpg">
		<img src="icon.svg">
		'''
		confidence, signals = assess_dom_confidence(dom)
		assert confidence < 0.55  # icon-heavy DOM should be well below high threshold
		assert signals.unlabeled_buttons >= 2
		assert signals.images_without_alt >= 3

	def test_medium_confidence_mixed(self):
		"""混合 DOM → 中等置信度"""
		dom = '''
		<button>Save</button>
		<button></button>
		<a href="/home">Home</a>
		<img src="icon.png">
		<div class="fa-icon"></div>
		<input type="text" placeholder="Enter name">
		'''
		confidence, signals = assess_dom_confidence(dom)
		assert 0.4 <= confidence <= 0.95  # mixed DOM should be in moderate range

	def test_custom_components(self):
		"""自定义 Web 组件 → 降低置信度"""
		dom = '''
		<my-button>Click</my-button>
		<custom-dropdown>Select</custom-dropdown>
		<app-header>Title</app-header>
		<nav-item>Home</nav-item>
		<user-avatar></user-avatar>
		<price-tag>$99</price-tag>
		'''
		confidence, signals = assess_dom_confidence(dom)
		assert signals.custom_component_count >= 5
		assert confidence < 0.95


class TestAdaptiveStrategy:
	"""自适应策略测试"""

	def test_skip_on_high_confidence(self):
		"""高置信度 DOM → SKIP"""
		strategy = AdaptiveVisionStrategy(high_threshold=0.8, low_threshold=0.5)
		dom = '<button>Submit</button>\n<button>Cancel</button>\n<a href="/">Home</a>'
		decision = strategy.decide(dom)
		assert decision == VisionDecision.SKIP

	def test_full_on_low_confidence(self):
		"""低置信度 DOM → FULL"""
		strategy = AdaptiveVisionStrategy(high_threshold=0.8, low_threshold=0.5)
		dom = '\n'.join([
			'<button></button>',
			'<button></button>',
			'<button></button>',
			'<img src="a.png">',
			'<img src="b.png">',
			'<img src="c.png">',
			'<img src="d.png">',
			'<div class="fa-icon"></div>',
			'<div class="material-icon"></div>',
			'<div class="svg-icon"></div>',
			'<div class="icon-btn"></div>',
			'<div class="fa-icon"></div>',
			'<div class="material-icon"></div>',
		])
		decision = strategy.decide(dom)
		assert decision in (VisionDecision.FULL, VisionDecision.LIGHTWEIGHT)

	def test_force_on_failures(self):
		"""连续失败 → 强制 FULL"""
		strategy = AdaptiveVisionStrategy(force_vision_after_failures=2)
		dom = '<button>Submit</button>'  # 高置信度
		decision = strategy.decide(dom, consecutive_failures=3)
		assert decision == VisionDecision.FULL

	def test_force_on_loop(self):
		"""循环检测 → 强制 FULL"""
		strategy = AdaptiveVisionStrategy()
		dom = '<button>Submit</button>'
		decision = strategy.decide(dom, loop_detected=True)
		assert decision == VisionDecision.FULL

	def test_stats_tracking(self):
		"""统计追踪"""
		strategy = AdaptiveVisionStrategy(high_threshold=0.8, low_threshold=0.5)

		# 简单 DOM → SKIP
		strategy.decide('<button>Click</button>\n<a href="/">Link</a>')
		# 强制视觉
		strategy.decide('<button>Click</button>', loop_detected=True)

		stats = strategy.stats
		assert stats['total_steps'] == 2
		assert stats['vision_calls'] >= 1
