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
import base64
import io
import logging
import time

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
app = FastAPI(title="Browser-Use Vision API", version="0.1.0")

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


class OCRRequest(BaseModel):
    image: str  # base64 encoded PNG


class OCRResponse(BaseModel):
    text_regions: list[dict]  # [{text, bbox: [x1,y1,x2,y2]}]
    inference_time_ms: float


class RegionCaptionRequest(BaseModel):
    image: str  # base64 encoded PNG


class RegionCaptionResponse(BaseModel):
    regions: list[dict]  # [{caption, bbox: [x1,y1,x2,y2]}]
    inference_time_ms: float


class PhraseGroundingRequest(BaseModel):
    image: str  # base64 encoded PNG
    phrase: str  # natural-language phrase to ground (e.g. task instruction)


class PhraseGroundingResponse(BaseModel):
    regions: list[dict]  # [{caption, bbox: [x1,y1,x2,y2]}]
    inference_time_ms: float


@app.get("/health")
async def health():
    if _backend and await _backend.is_ready():
        return {"status": "ok", "backend": _backend.__class__.__name__}
    return {"status": "loading"}


@app.post("/detect", response_model=DetectResponse)
async def detect(req: DetectRequest):
    if not _backend:
        raise HTTPException(503, "Backend not loaded")

    img_bytes = base64.b64decode(req.image)
    start = time.time()
    elements = await _backend.detect_elements(img_bytes, threshold=req.threshold)
    elapsed = (time.time() - start) * 1000

    return DetectResponse(
        elements=[el.model_dump() for el in elements],
        inference_time_ms=elapsed,
    )


@app.post("/describe", response_model=DescribeResponse)
async def describe(req: DescribeRequest):
    if not _backend:
        raise HTTPException(503, "Backend not loaded")

    img_bytes = base64.b64decode(req.image)
    bbox = tuple(req.bbox)
    start = time.time()
    desc = await _backend.describe_region(img_bytes, bbox)
    elapsed = (time.time() - start) * 1000

    return DescribeResponse(description=desc, inference_time_ms=elapsed)


@app.post("/ocr", response_model=OCRResponse)
async def ocr(req: OCRRequest):
    """OCR with region detection using Florence-2 <OCR_WITH_REGION> task"""
    if not _backend:
        raise HTTPException(503, "Backend not loaded")
    if not hasattr(_backend, "_run_inference"):
        raise HTTPException(400, "OCR only supported with Florence backend")

    from PIL import Image as PILImage

    img_bytes = base64.b64decode(req.image)
    image = PILImage.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = image.size

    start = time.time()
    result = await _backend._run_inference(image, "<OCR_WITH_REGION>")
    elapsed = (time.time() - start) * 1000

    parsed = result.get("<OCR_WITH_REGION>", {})
    quad_boxes = parsed.get("quad_boxes", [])
    labels = parsed.get("labels", [])

    text_regions = []
    for quad, label in zip(quad_boxes, labels):
        # quad_boxes: [x1,y1,x2,y1,x2,y2,x1,y2] -> normalize to [x1,y1,x2,y2]
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

    return OCRResponse(text_regions=text_regions, inference_time_ms=elapsed)


@app.post("/regions", response_model=RegionCaptionResponse)
async def regions(req: RegionCaptionRequest):
    """Dense region caption using Florence-2 <DENSE_REGION_CAPTION> task"""
    if not _backend:
        raise HTTPException(503, "Backend not loaded")
    if not hasattr(_backend, "_run_inference"):
        raise HTTPException(400, "Region caption only supported with Florence backend")

    from PIL import Image as PILImage

    img_bytes = base64.b64decode(req.image)
    image = PILImage.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = image.size

    start = time.time()
    result = await _backend._run_inference(image, "<DENSE_REGION_CAPTION>")
    elapsed = (time.time() - start) * 1000

    parsed = result.get("<DENSE_REGION_CAPTION>", {})
    bboxes = parsed.get("bboxes", [])
    labels = parsed.get("labels", [])

    region_list = []
    for bbox, label in zip(bboxes, labels):
        if len(bbox) >= 4:
            x1, y1, x2, y2 = bbox[0] / w, bbox[1] / h, bbox[2] / w, bbox[3] / h
            region_list.append(
                {
                    "caption": label.strip(),
                    "bbox": [x1, y1, x2, y2],
                }
            )

    return RegionCaptionResponse(regions=region_list, inference_time_ms=elapsed)


@app.post("/phrase_grounding", response_model=PhraseGroundingResponse)
async def phrase_grounding(req: PhraseGroundingRequest):
    """Phrase grounding using Florence-2 <CAPTION_TO_PHRASE_GROUNDING> task.

    Grounds a natural-language phrase (e.g. the task instruction) to bbox(es) in
    the image. Unlike OCR/region-caption, this is text->region: it localizes the
    described target even for icon-only buttons with no readable text.
    """
    if not _backend:
        raise HTTPException(503, "Backend not loaded")
    if not hasattr(_backend, "_run_inference"):
        raise HTTPException(400, "Phrase grounding only supported with Florence backend")

    from PIL import Image as PILImage

    img_bytes = base64.b64decode(req.image)
    image = PILImage.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = image.size

    start = time.time()
    result = await _backend._run_inference(image, "<CAPTION_TO_PHRASE_GROUNDING>", text_input=req.phrase)
    elapsed = (time.time() - start) * 1000

    parsed = result.get("<CAPTION_TO_PHRASE_GROUNDING>", {})
    bboxes = parsed.get("bboxes", [])
    labels = parsed.get("labels", [])

    region_list = []
    for bbox, label in zip(bboxes, labels):
        if len(bbox) >= 4:
            x1, y1, x2, y2 = bbox[0] / w, bbox[1] / h, bbox[2] / w, bbox[3] / h
            region_list.append(
                {
                    "caption": (label or req.phrase).strip(),
                    "bbox": [x1, y1, x2, y2],
                }
            )

    return PhraseGroundingResponse(regions=region_list, inference_time_ms=elapsed)


async def startup(backend_type: str, model_name: str = None, model_dir: str = None):
    global _backend

    if backend_type == "florence":
        from browser_use_vision.grounding.florence import FlorenceBackend

        _backend = FlorenceBackend(model_name=model_name or "microsoft/Florence-2-large", device="cuda")
    elif backend_type == "omniparser":
        from browser_use_vision.grounding.omniparser import OmniParserBackend

        if not model_dir:
            raise ValueError("--model-dir required for omniparser backend")
        _backend = OmniParserBackend(model_dir=model_dir, device="cuda")
    else:
        raise ValueError(f"Unknown backend: {backend_type}")

    await _backend.load_model()
    logger.info(f"Vision API ready with {backend_type} backend")


def main():
    parser = argparse.ArgumentParser(description="Browser-Use Vision API Server")
    parser.add_argument("--backend", choices=["florence", "omniparser"], default="florence")
    parser.add_argument("--model-name", default="microsoft/Florence-2-large")
    parser.add_argument("--model-dir", default=None, help="OmniParser weights directory")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    @app.on_event("startup")
    async def on_startup():
        await startup(args.backend, args.model_name, args.model_dir)

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
