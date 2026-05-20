"""
基准评测框架

定义评测场景和运行器，量化视觉增强的效果。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkScenario:
	"""评测场景定义"""

	name: str
	description: str
	url: str
	task: str
	expected_actions: list[str]  # 期望的动作序列
	difficulty: str = 'medium'  # easy, medium, hard
	category: str = 'general'  # icon_only, complex_spa, dynamic_content, etc.
	max_steps: int = 15
	success_criteria: str = ''  # 成功判定条件描述


@dataclass
class BenchmarkResult:
	"""评测结果"""

	scenario_name: str
	success: bool
	steps_taken: int
	time_seconds: float
	vision_calls: int
	tokens_used: int = 0
	error: Optional[str] = None
	action_trace: list[str] = field(default_factory=list)
	vision_stats: dict = field(default_factory=dict)


# 预定义评测场景
SCENARIOS: dict[str, BenchmarkScenario] = {
	'icon_button_click': BenchmarkScenario(
		name='icon_button_click',
		description='点击仅有图标无文字的按钮（购物车/心形/搜索）',
		url='https://www.amazon.com',
		task='Click the shopping cart icon in the top right',
		expected_actions=['click_cart_icon'],
		difficulty='medium',
		category='icon_only',
	),
	'image_carousel': BenchmarkScenario(
		name='image_carousel',
		description='在图片轮播中找到特定图片并点击',
		url='https://www.airbnb.com',
		task='Click the next arrow on the main photo carousel',
		expected_actions=['click_next_arrow'],
		difficulty='medium',
		category='dynamic_content',
	),
	'icon_menu': BenchmarkScenario(
		name='icon_menu',
		description='识别并点击图标菜单中的特定项',
		url='https://docs.google.com',
		task='Click the bold (B) icon in the toolbar',
		expected_actions=['click_bold_icon'],
		difficulty='easy',
		category='icon_only',
	),
	'canvas_app': BenchmarkScenario(
		name='canvas_app',
		description='在 Canvas 应用中操作（DOM 几乎无信息）',
		url='https://excalidraw.com',
		task='Select the rectangle tool from the toolbar',
		expected_actions=['click_rectangle_tool'],
		difficulty='hard',
		category='canvas',
	),
	'custom_dropdown': BenchmarkScenario(
		name='custom_dropdown',
		description='操作自定义下拉组件（非原生 select）',
		url='https://mui.com/material-ui/react-select/',
		task='Open the first demo select and choose "Twenty"',
		expected_actions=['click_select', 'click_option'],
		difficulty='medium',
		category='complex_spa',
	),
	'svg_icon_grid': BenchmarkScenario(
		name='svg_icon_grid',
		description='在 SVG 图标网格中找到并点击指定图标',
		url='https://fonts.google.com/icons',
		task='Find and click the "home" icon',
		expected_actions=['search_home', 'click_home_icon'],
		difficulty='medium',
		category='icon_only',
	),
	'shadow_dom': BenchmarkScenario(
		name='shadow_dom',
		description='操作 Shadow DOM 内的元素',
		url='https://lit.dev/playground/',
		task='Click the Run button in the playground',
		expected_actions=['click_run'],
		difficulty='hard',
		category='complex_spa',
	),
	'video_player': BenchmarkScenario(
		name='video_player',
		description='操作视频播放器控件',
		url='https://www.youtube.com/watch?v=dQw4w9WgXcQ',
		task='Click the fullscreen button on the video player',
		expected_actions=['click_fullscreen'],
		difficulty='medium',
		category='dynamic_content',
	),
	'cookie_banner': BenchmarkScenario(
		name='cookie_banner',
		description='关闭 Cookie 同意弹窗',
		url='https://www.bbc.com',
		task='Accept or dismiss the cookie consent banner',
		expected_actions=['click_accept'],
		difficulty='easy',
		category='general',
	),
	'dark_theme_icons': BenchmarkScenario(
		name='dark_theme_icons',
		description='暗色主题下识别低对比度图标',
		url='https://github.com',
		task='Click the notifications bell icon',
		expected_actions=['click_notifications'],
		difficulty='medium',
		category='icon_only',
	),
}


class BenchmarkRunner:
	"""评测运行器"""

	def __init__(self, results_dir: str = 'benchmarks/results'):
		self.results_dir = Path(results_dir)
		self.results_dir.mkdir(parents=True, exist_ok=True)

	async def run_scenario(
		self,
		scenario: BenchmarkScenario,
		agent_factory,
		use_vision: bool = True,
	) -> BenchmarkResult:
		"""运行单个评测场景"""
		logger.info(f'Running scenario: {scenario.name} (vision={use_vision})')
		start_time = time.time()

		try:
			agent = agent_factory(
				task=scenario.task,
				use_vision=use_vision,
				max_steps=scenario.max_steps,
			)
			result = await agent.run()
			elapsed = time.time() - start_time

			# 判定成功
			success = result.is_done() if hasattr(result, 'is_done') else bool(result)

			vision_stats = agent.vision_stats if hasattr(agent, 'vision_stats') else {}

			return BenchmarkResult(
				scenario_name=scenario.name,
				success=success,
				steps_taken=agent.state.n_steps if hasattr(agent, 'state') else 0,
				time_seconds=elapsed,
				vision_calls=vision_stats.get('total_vision_calls', 0),
				vision_stats=vision_stats,
			)
		except Exception as e:
			elapsed = time.time() - start_time
			logger.error(f'Scenario {scenario.name} failed: {e}')
			return BenchmarkResult(
				scenario_name=scenario.name,
				success=False,
				steps_taken=0,
				time_seconds=elapsed,
				vision_calls=0,
				error=str(e),
			)

	async def run_all(
		self,
		agent_factory,
		scenarios: Optional[list[str]] = None,
		use_vision: bool = True,
	) -> list[BenchmarkResult]:
		"""运行所有（或指定）评测场景"""
		targets = scenarios or list(SCENARIOS.keys())
		results = []

		for name in targets:
			if name not in SCENARIOS:
				logger.warning(f'Unknown scenario: {name}')
				continue
			result = await self.run_scenario(SCENARIOS[name], agent_factory, use_vision)
			results.append(result)

		# 保存结果
		label = 'vision' if use_vision else 'baseline'
		output_file = self.results_dir / f'{label}_{int(time.time())}.json'
		with open(output_file, 'w') as f:
			json.dump([r.__dict__ for r in results], f, indent=2, default=str)
		logger.info(f'Results saved to {output_file}')

		# 打印摘要
		self._print_summary(results, use_vision)
		return results

	def _print_summary(self, results: list[BenchmarkResult], use_vision: bool) -> None:
		"""打印评测摘要"""
		total = len(results)
		successes = sum(1 for r in results if r.success)
		avg_steps = sum(r.steps_taken for r in results) / total if total > 0 else 0
		avg_time = sum(r.time_seconds for r in results) / total if total > 0 else 0
		total_vision = sum(r.vision_calls for r in results)

		mode = 'Vision Enhanced' if use_vision else 'Baseline (DOM only)'
		print(f'\n{"=" * 60}')
		print(f'  Benchmark Results: {mode}')
		print(f'{"=" * 60}')
		print(f'  Success Rate:    {successes}/{total} ({successes / total * 100:.1f}%)')
		print(f'  Avg Steps:       {avg_steps:.1f}')
		print(f'  Avg Time:        {avg_time:.1f}s')
		print(f'  Vision Calls:    {total_vision}')
		print(f'{"=" * 60}\n')
