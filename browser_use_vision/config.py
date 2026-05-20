"""
配置管理

统一管理 browser-use-vision 的配置项。
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class VisionConfig(BaseModel):
	"""视觉增强配置"""

	# 后端选择
	backend: Literal['florence', 'omniparser'] = Field(
		default='florence', description='视觉 Grounding 后端类型'
	)

	# Florence 配置
	florence_model: str = Field(
		default='microsoft/Florence-2-large', description='Florence-2 模型名称'
	)
	florence_device: str = Field(
		default='auto', description='推理设备 (auto, cuda, mps, cpu)'
	)

	# OmniParser 配置
	omniparser_model_dir: Optional[str] = Field(
		default=None, description='OmniParser 权重目录路径'
	)

	# 远程模式
	remote_url: Optional[str] = Field(
		default=None, description='远程推理服务 URL，设置后不加载本地模型'
	)

	# 自适应策略
	enable_adaptive: bool = Field(
		default=True, description='是否启用自适应策略'
	)
	high_threshold: float = Field(
		default=0.8, ge=0.0, le=1.0, description='DOM 置信度高阈值（高于跳过视觉）'
	)
	low_threshold: float = Field(
		default=0.5, ge=0.0, le=1.0, description='DOM 置信度低阈值（低于完整视觉）'
	)
	force_vision_after_failures: int = Field(
		default=2, ge=1, description='连续失败多少次强制视觉'
	)

	# 服务器配置
	server_port: int = Field(
		default=8100, description='Vision API 服务端口'
	)
	server_host: str = Field(
		default='0.0.0.0', description='Vision API 服务绑定地址'
	)

	def create_backend(self):
		"""根据配置创建后端实例"""
		if self.backend == 'florence':
			from browser_use_vision.grounding.florence import FlorenceBackend
			return FlorenceBackend(
				model_name=self.florence_model,
				device=self.florence_device,
				remote_url=self.remote_url,
			)
		elif self.backend == 'omniparser':
			from browser_use_vision.grounding.omniparser import OmniParserBackend
			return OmniParserBackend(
				model_dir=self.omniparser_model_dir,
				remote_url=self.remote_url,
				device=self.florence_device,  # 共用设备配置
			)
		else:
			raise ValueError(f'Unknown backend: {self.backend}')
