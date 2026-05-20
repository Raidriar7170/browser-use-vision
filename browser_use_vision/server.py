"""
视觉 Grounding 远程 API 服务

在 A100 服务器上启动此服务，暴露 HTTP API 供本地 Agent 调用。
支持 Florence-2 和 OmniParser 两种后端。

启动方式:
    python -m browser_use_vision.server --backend florence --port 8100
    python -m browser_use_vision.server --backend omniparser --model-dir /path/to/weights --port 8100
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import logging
import time

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

logger = logging.getLogger(__name__)
app = FastAPI(title='Browser-Use Vision API', version='0.1.0')

# 全局后端实例
_backend = None


class DetectRequest(BaseModel):
	image: str  # base64 encoded PNG
	threshold: float = 0.3


class DescribeRequest(BaseModel):
	image: str  # base64 encoded PNG
	bbox: list[float]  # [x1, y1, x2, y2] normalized


class DetectResponse(BaseModel):
	elements: list[dict]
	inference_time_ms: float


class DescribeResponse(BaseModel):
	description: str
	inference_time_ms: float


@app.get('/health')
async def health():
	if _backend and await _backend.is_ready():
		return {'status': 'ok', 'backend': _backend.__class__.__name__}
	return {'status': 'loading'}


@app.post('/detect', response_model=DetectResponse)
async def detect(req: DetectRequest):
	if not _backend:
		raise HTTPException(503, 'Backend not loaded')

	img_bytes = base64.b64decode(req.image)
	start = time.time()
	elements = await _backend.detect_elements(img_bytes, threshold=req.threshold)
	elapsed = (time.time() - start) * 1000

	return DetectResponse(
		elements=[el.model_dump() for el in elements],
		inference_time_ms=elapsed,
	)


@app.post('/describe', response_model=DescribeResponse)
async def describe(req: DescribeRequest):
	if not _backend:
		raise HTTPException(503, 'Backend not loaded')

	img_bytes = base64.b64decode(req.image)
	bbox = tuple(req.bbox)
	start = time.time()
	desc = await _backend.describe_region(img_bytes, bbox)
	elapsed = (time.time() - start) * 1000

	return DescribeResponse(description=desc, inference_time_ms=elapsed)


async def startup(backend_type: str, model_name: str = None, model_dir: str = None):
	global _backend

	if backend_type == 'florence':
		from browser_use_vision.grounding.florence import FlorenceBackend

		_backend = FlorenceBackend(model_name=model_name or 'microsoft/Florence-2-large', device='cuda')
	elif backend_type == 'omniparser':
		from browser_use_vision.grounding.omniparser import OmniParserBackend

		if not model_dir:
			raise ValueError('--model-dir required for omniparser backend')
		_backend = OmniParserBackend(model_dir=model_dir, device='cuda')
	else:
		raise ValueError(f'Unknown backend: {backend_type}')

	await _backend.load_model()
	logger.info(f'Vision API ready with {backend_type} backend')


def main():
	parser = argparse.ArgumentParser(description='Browser-Use Vision API Server')
	parser.add_argument('--backend', choices=['florence', 'omniparser'], default='florence')
	parser.add_argument('--model-name', default='microsoft/Florence-2-large')
	parser.add_argument('--model-dir', default=None, help='OmniParser weights directory')
	parser.add_argument('--port', type=int, default=8100)
	parser.add_argument('--host', default='0.0.0.0')
	args = parser.parse_args()

	logging.basicConfig(level=logging.INFO)

	@app.on_event('startup')
	async def on_startup():
		await startup(args.backend, args.model_name, args.model_dir)

	uvicorn.run(app, host=args.host, port=args.port)


if __name__ == '__main__':
	main()
