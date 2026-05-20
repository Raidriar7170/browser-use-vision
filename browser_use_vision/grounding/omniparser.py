"""
OmniParser V2 视觉 Grounding 后端

使用微软 OmniParser V2 专门做 UI 元素检测。
OmniParser 专为 UI 理解设计，检测精度高于通用视觉模型。

部署方式：在 A100 服务器上启动 OmniParser API 服务，本地通过 HTTP 调用。
"""

from __future__ import annotations

import asyncio
import io
import logging
from pathlib import Path
from typing import Optional

from PIL import Image

from browser_use_vision.grounding import DetectedElement, VisualGroundingBackend

logger = logging.getLogger(__name__)


class OmniParserBackend(VisualGroundingBackend):
    """
    OmniParser V2 后端

    OmniParser 对 UI 元素的检测优于通用目标检测模型，特别擅长：
    - 图标/logo 检测与分类
    - 可交互元素识别
    - 文字区域 OCR

    支持两种模式：
    1. 本地模式：直接加载模型
    2. 远程模式：通过 HTTP API 调用（推荐，在 A100 上部署）

    Usage:
            # 远程模式（推荐）
            backend = OmniParserBackend(remote_url="http://gpu-server:8100")

            # 本地模式
            backend = OmniParserBackend(model_dir="/path/to/omniparser/weights")
            await backend.load_model()
    """

    def __init__(
        self,
        model_dir: Optional[str] = None,
        remote_url: Optional[str] = None,
        device: str = "auto",
    ):
        self.model_dir = model_dir
        self.remote_url = remote_url
        self.device = device
        self._model = None
        self._loaded = False

    async def load_model(self) -> None:
        """加载 OmniParser 模型"""
        if self.remote_url:
            # 远程模式：验证连接
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                try:
                    resp = await client.get(f"{self.remote_url}/health")
                    resp.raise_for_status()
                    self._loaded = True
                    logger.info(f"OmniParser remote endpoint ready: {self.remote_url}")
                except Exception as e:
                    raise ConnectionError(f"Cannot connect to OmniParser at {self.remote_url}: {e}")
            return

        if not self.model_dir:
            raise ValueError("Must provide model_dir for local mode or remote_url for remote mode")

        logger.info(f"Loading OmniParser from {self.model_dir}")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._load_model_sync)
        self._loaded = True
        logger.info("OmniParser loaded")

    def _load_model_sync(self) -> None:
        """同步加载 OmniParser（在线程中执行）"""
        import torch

        if self.device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # OmniParser V2 使用 YOLO 做检测 + icon caption 模型做描述
        from ultralytics import YOLO

        model_path = Path(self.model_dir)

        # 加载 UI 元素检测模型
        det_weights = model_path / "icon_detect" / "best.pt"
        if det_weights.exists():
            self._det_model = YOLO(str(det_weights))
            logger.info("OmniParser detection model loaded")
        else:
            raise FileNotFoundError(f"Detection weights not found: {det_weights}")

        # 加载 icon caption 模型（用于描述图标）
        caption_path = model_path / "icon_caption"
        if caption_path.exists():
            from transformers import AutoModelForCausalLM, AutoProcessor

            self._caption_processor = AutoProcessor.from_pretrained(str(caption_path), trust_remote_code=True)
            self._caption_model = AutoModelForCausalLM.from_pretrained(
                str(caption_path),
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                trust_remote_code=True,
            ).to(self.device)
            self._caption_model.eval()
            logger.info("OmniParser caption model loaded")
        else:
            self._caption_processor = None
            self._caption_model = None
            logger.warning(f"Caption model not found at {caption_path}, descriptions will be limited")

    async def is_ready(self) -> bool:
        return self._loaded

    async def detect_elements(self, screenshot: bytes, threshold: float = 0.3) -> list[DetectedElement]:
        """检测截图中的 UI 元素"""
        if not self._loaded:
            await self.load_model()

        if self.remote_url:
            return await self._detect_remote(screenshot, threshold)

        return await self._detect_local(screenshot, threshold)

    async def _detect_local(self, screenshot: bytes, threshold: float) -> list[DetectedElement]:
        """本地推理"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._detect_local_sync, screenshot, threshold)

    def _detect_local_sync(self, screenshot: bytes, threshold: float) -> list[DetectedElement]:
        """同步本地检测"""
        image = Image.open(io.BytesIO(screenshot)).convert("RGB")
        w, h = image.size

        # YOLO 检测
        results = self._det_model(image, conf=threshold, verbose=False)
        elements = []

        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for i in range(len(boxes)):
                xyxy = boxes.xyxy[i].cpu().numpy()
                conf = float(boxes.conf[i].cpu())
                cls_id = int(boxes.cls[i].cpu())
                label = result.names.get(cls_id, "unknown")

                # 归一化坐标
                norm_bbox = (xyxy[0] / w, xyxy[1] / h, xyxy[2] / w, xyxy[3] / h)

                # 生成描述
                desc = label
                if self._caption_model and self._caption_processor:
                    crop = image.crop([int(v) for v in xyxy])
                    desc = self._generate_caption(crop)

                elements.append(
                    DetectedElement(
                        bbox=norm_bbox,
                        label=label,
                        description=desc,
                        confidence=conf,
                    )
                )

        logger.info(f"OmniParser detected {len(elements)} elements")
        return elements

    def _generate_caption(self, crop: Image.Image) -> str:
        """为图标裁剪区域生成描述"""
        import torch

        inputs = self._caption_processor(images=crop, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            output = self._caption_model.generate(**inputs, max_new_tokens=50)

        text = self._caption_processor.decode(output[0], skip_special_tokens=True)
        return text.strip()

    async def describe_region(self, screenshot: bytes, bbox: tuple[float, float, float, float]) -> str:
        """描述指定区域"""
        if not self._loaded:
            await self.load_model()

        if self.remote_url:
            return await self._describe_remote(screenshot, bbox)

        image = Image.open(io.BytesIO(screenshot)).convert("RGB")
        w, h = image.size
        pixel_bbox = (int(bbox[0] * w), int(bbox[1] * h), int(bbox[2] * w), int(bbox[3] * h))
        crop = image.crop(pixel_bbox)

        if self._caption_model:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._generate_caption, crop)
        return "icon element"

    async def _detect_remote(self, screenshot: bytes, threshold: float) -> list[DetectedElement]:
        """远程 API 检测"""
        import base64

        import httpx

        img_b64 = base64.b64encode(screenshot).decode()
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.remote_url}/detect",
                json={"image": img_b64, "threshold": threshold},
            )
            resp.raise_for_status()
            data = resp.json()
        return [DetectedElement(**el) for el in data.get("elements", [])]

    async def _describe_remote(self, screenshot: bytes, bbox: tuple) -> str:
        """远程 API 描述"""
        import base64

        import httpx

        img_b64 = base64.b64encode(screenshot).decode()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.remote_url}/describe",
                json={"image": img_b64, "bbox": list(bbox)},
            )
            resp.raise_for_status()
            return resp.json().get("description", "")
