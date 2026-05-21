"""
Florence-2 视觉 Grounding 后端

使用微软 Florence-2 模型进行 UI 元素检测和描述。
支持本地推理（M5 Pro / A100）和远程 API 调用。
"""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Optional

from PIL import Image

from browser_use_vision.grounding import DetectedElement, VisualGroundingBackend

logger = logging.getLogger(__name__)


class FlorenceBackend(VisualGroundingBackend):
    """
    Florence-2 视觉 Grounding 后端

    Florence-2 支持多种视觉任务:
    - <OD> 目标检测
    - <CAPTION_TO_PHRASE_GROUNDING> 文本定位
    - <MORE_DETAILED_CAPTION> 详细描述
    - <OCR_WITH_REGION> 带区域的 OCR

    Usage:
            backend = FlorenceBackend(model_name="microsoft/Florence-2-large")
            await backend.load_model()
            elements = await backend.detect_elements(screenshot_bytes)
    """

    def __init__(
        self,
        model_name: str = "microsoft/Florence-2-large",
        device: str = "auto",
        remote_url: Optional[str] = None,
    ):
        """
        Args:
                model_name: HuggingFace 模型名称
                device: 推理设备 ('auto', 'cuda', 'mps', 'cpu')
                remote_url: 远程推理服务 URL（设置后走 HTTP 调用，不加载本地模型）
        """
        self.model_name = model_name
        self.device = device
        self.remote_url = remote_url
        self._model = None
        self._processor = None
        self._loaded = False

    async def load_model(self) -> None:
        """加载模型到内存（在远程模式下跳过）"""
        if self.remote_url:
            self._loaded = True
            logger.info(f"Florence-2 using remote endpoint: {self.remote_url}")
            return

        logger.info(f"Loading Florence-2 model: {self.model_name}")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._load_model_sync)
        self._loaded = True
        logger.info(f"Florence-2 loaded on device: {self.device}")

    def _load_model_sync(self) -> None:
        """同步加载模型（在线程中执行）"""
        import torch
        from transformers import AutoModelForCausalLM, AutoProcessor

        if self.device == "auto":
            if torch.cuda.is_available():
                self.device = "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                self.device = "mps"
            else:
                self.device = "cpu"

        dtype = torch.float16 if self.device == "cuda" else torch.float32

        self._processor = AutoProcessor.from_pretrained(self.model_name, trust_remote_code=True)
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            torch_dtype=dtype,
            trust_remote_code=True,
        ).to(self.device)
        self._model.eval()

    async def is_ready(self) -> bool:
        return self._loaded

    async def detect_elements(self, screenshot: bytes, threshold: float = 0.3) -> list[DetectedElement]:
        """
        使用 Florence-2 的 <OD> 任务检测 UI 元素，
        然后对每个检测区域用 <MORE_DETAILED_CAPTION> 生成描述。
        """
        if not self._loaded:
            await self.load_model()

        image = Image.open(io.BytesIO(screenshot)).convert("RGB")
        w, h = image.size

        if self.remote_url:
            return await self._detect_remote(screenshot, threshold)

        # 1. 目标检测
        od_result = await self._run_inference(image, "<OD>")
        parsed = od_result.get("<OD>", {})
        bboxes = parsed.get("bboxes", [])
        labels = parsed.get("labels", [])

        elements = []
        for bbox_raw, label in zip(bboxes, labels):
            # Florence-2 返回像素坐标，归一化到 [0,1]
            x1, y1, x2, y2 = bbox_raw
            norm_bbox = (x1 / w, y1 / h, x2 / w, y2 / h)

            # 2. 为每个元素生成描述
            desc = await self._describe_crop(image, bbox_raw)

            element = DetectedElement(
                bbox=norm_bbox,
                label=label.lower(),
                description=desc,
                confidence=0.8,  # Florence-2 不直接输出置信度，用默认值
            )
            if element.area > 0.001:  # 过滤太小的元素
                elements.append(element)

        logger.info(f"Florence-2 detected {len(elements)} elements")
        return elements

    async def describe_region(self, screenshot: bytes, bbox: tuple[float, float, float, float]) -> str:
        """为指定区域生成描述"""
        if not self._loaded:
            await self.load_model()

        image = Image.open(io.BytesIO(screenshot)).convert("RGB")
        w, h = image.size

        # 反归一化
        pixel_bbox = (bbox[0] * w, bbox[1] * h, bbox[2] * w, bbox[3] * h)
        return await self._describe_crop(image, pixel_bbox)

    async def _describe_crop(self, image: Image.Image, pixel_bbox: tuple) -> str:
        """裁剪区域并生成描述"""
        x1, y1, x2, y2 = [int(v) for v in pixel_bbox]
        # 稍微扩大裁剪区域以获取上下文
        pad = 10
        x1 = max(0, x1 - pad)
        y1 = max(0, y1 - pad)
        x2 = min(image.width, x2 + pad)
        y2 = min(image.height, y2 + pad)

        crop = image.crop((x1, y1, x2, y2))
        result = await self._run_inference(crop, "<MORE_DETAILED_CAPTION>")
        return result.get("<MORE_DETAILED_CAPTION>", "unknown element")

    async def _run_inference(self, image: Image.Image, task_prompt: str) -> dict:
        """执行 Florence-2 推理"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._run_inference_sync, image, task_prompt)

    def _run_inference_sync(self, image: Image.Image, task_prompt: str) -> dict:
        """同步推理（在线程中执行）"""
        import torch

        inputs = self._processor(text=task_prompt, images=image, return_tensors="pt")
        # 确保 dtype 匹配模型（float16 on cuda, float32 on cpu/mps）
        dtype = torch.float16 if self.device == "cuda" else torch.float32
        inputs = {
            k: v.to(self.device, dtype=dtype) if v.is_floating_point() else v.to(self.device) for k, v in inputs.items()
        }

        with torch.no_grad():
            generated_ids = self._model.generate(
                **inputs,
                max_new_tokens=512,
                num_beams=3,
            )

        generated_text = self._processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
        result = self._processor.post_process_generation(generated_text, task=task_prompt, image_size=image.size)
        return result

    async def _detect_remote(self, screenshot: bytes, threshold: float) -> list[DetectedElement]:
        """通过远程 API 调用检测"""
        import base64

        import httpx

        img_b64 = base64.b64encode(screenshot).decode()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.remote_url}/detect",
                json={"image": img_b64, "threshold": threshold},
            )
            resp.raise_for_status()
            data = resp.json()

        return [DetectedElement(**el) for el in data.get("elements", [])]

    async def ocr_with_region(self, screenshot: bytes) -> list[dict]:
        """
        使用 Florence-2 <OCR_WITH_REGION> 识别截图中的文字及位置

        Returns:
            [{text: str, bbox: [x1, y1, x2, y2]}]  坐标归一化到 [0,1]
        """
        if not self._loaded:
            await self.load_model()

        if self.remote_url:
            return await self._ocr_remote(screenshot)

        image = Image.open(io.BytesIO(screenshot)).convert("RGB")
        w, h = image.size

        result = await self._run_inference(image, "<OCR_WITH_REGION>")
        parsed = result.get("<OCR_WITH_REGION>", {})
        quad_boxes = parsed.get("quad_boxes", [])
        labels = parsed.get("labels", [])

        text_regions = []
        for quad, label in zip(quad_boxes, labels):
            if len(quad) >= 8:
                x1 = min(quad[0], quad[6]) / w
                y1 = min(quad[1], quad[3]) / h
                x2 = max(quad[2], quad[4]) / w
                y2 = max(quad[5], quad[7]) / h
                text_regions.append(
                    {
                        "text": label.strip(),
                        "bbox": [x1, y1, x2, y2],
                    }
                )

        logger.info(f"Florence-2 OCR: {len(text_regions)} text regions found")
        return text_regions

    async def dense_region_caption(self, screenshot: bytes) -> list[dict]:
        """
        使用 Florence-2 <DENSE_REGION_CAPTION> 生成区域描述

        Returns:
            [{caption: str, bbox: [x1, y1, x2, y2]}]  坐标归一化到 [0,1]
        """
        if not self._loaded:
            await self.load_model()

        if self.remote_url:
            return await self._regions_remote(screenshot)

        image = Image.open(io.BytesIO(screenshot)).convert("RGB")
        w, h = image.size

        result = await self._run_inference(image, "<DENSE_REGION_CAPTION>")
        parsed = result.get("<DENSE_REGION_CAPTION>", {})
        bboxes = parsed.get("bboxes", [])
        labels = parsed.get("labels", [])

        regions = []
        for bbox, label in zip(bboxes, labels):
            if len(bbox) >= 4:
                x1, y1, x2, y2 = bbox[0] / w, bbox[1] / h, bbox[2] / w, bbox[3] / h
                regions.append(
                    {
                        "caption": label.strip(),
                        "bbox": [x1, y1, x2, y2],
                    }
                )

        logger.info(f"Florence-2 Dense Caption: {len(regions)} regions found")
        return regions

    async def _ocr_remote(self, screenshot: bytes) -> list[dict]:
        """通过远程 API 调用 OCR"""
        import base64

        import httpx

        img_b64 = base64.b64encode(screenshot).decode()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.remote_url}/ocr",
                json={"image": img_b64},
            )
            resp.raise_for_status()
            data = resp.json()

        return data.get("text_regions", [])

    async def _regions_remote(self, screenshot: bytes) -> list[dict]:
        """通过远程 API 调用 Dense Region Caption"""
        import base64

        import httpx

        img_b64 = base64.b64encode(screenshot).decode()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.remote_url}/regions",
                json={"image": img_b64},
            )
            resp.raise_for_status()
            data = resp.json()

        return data.get("regions", [])
