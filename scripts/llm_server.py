"""
轻量 LLM API 服务

用 transformers 加载 Qwen-2.5-7B-Instruct，提供 OpenAI 兼容的 /v1/chat/completions API。
浏览器 Agent 通过 LangChain ChatOpenAI 连接此服务。

启动:
    cd /mnt/data/minghongsun/browser-use-vision
    PYTHONPATH=. python3 scripts/llm_server.py --model Qwen/Qwen2.5-7B-Instruct --port 8200

使用:
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(base_url="http://localhost:8200/v1", api_key="none", model="qwen")
"""

import argparse
import asyncio
import json
import logging
import time
import uuid
from typing import Optional

import torch
import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, AutoTokenizer

logger = logging.getLogger(__name__)
app = FastAPI(title="LLM API Server")

_model = None
_tokenizer = None
_model_name = ""


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "qwen"
    messages: list[ChatMessage]
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 0.95
    stream: bool = False


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: Usage


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [{"id": _model_name, "object": "model", "owned_by": "local"}],
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    if _model is None or _tokenizer is None:
        return {"error": "Model not loaded"}

    # 构建 prompt
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    text = _tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

    inputs = _tokenizer(text, return_tensors="pt").to(_model.device)
    prompt_len = inputs["input_ids"].shape[1]

    t0 = time.time()
    with torch.no_grad():
        outputs = _model.generate(
            **inputs,
            max_new_tokens=request.max_tokens,
            temperature=max(request.temperature, 0.01),
            top_p=request.top_p,
            do_sample=request.temperature > 0.01,
            pad_token_id=_tokenizer.eos_token_id,
        )
    gen_time = time.time() - t0

    new_tokens = outputs[0][prompt_len:]
    response_text = _tokenizer.decode(new_tokens, skip_special_tokens=True)
    comp_tokens = len(new_tokens)

    logger.info(f"Generated {comp_tokens} tokens in {gen_time:.1f}s ({comp_tokens/gen_time:.1f} tok/s)")

    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
        created=int(time.time()),
        model=request.model,
        choices=[
            ChatCompletionChoice(
                message=ChatMessage(role="assistant", content=response_text),
            )
        ],
        usage=Usage(
            prompt_tokens=prompt_len,
            completion_tokens=comp_tokens,
            total_tokens=prompt_len + comp_tokens,
        ),
    )


@app.get("/health")
async def health():
    return {"status": "ok" if _model is not None else "loading", "model": _model_name}


def load_model(model_name: str, device: str = "auto", gpu_id: int = 1):
    global _model, _tokenizer, _model_name
    _model_name = model_name

    logger.info(f"Loading model: {model_name}")
    t0 = time.time()

    if device == "auto":
        device = f"cuda:{gpu_id}" if torch.cuda.is_available() else "cpu"

    _tokenizer = AutoTokenizer.from_pretrained(
        model_name,
        trust_remote_code=True,
    )

    _model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.float16,
        device_map=device,
        trust_remote_code=True,
    )
    _model.eval()

    logger.info(f"Model loaded in {time.time()-t0:.1f}s on {device}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--model-dir", default=None, help="Local model directory")
    parser.add_argument("--port", type=int, default=8200)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--gpu", type=int, default=1, help="GPU ID to use")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    model_path = args.model_dir or args.model
    load_model(model_path, gpu_id=args.gpu)

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
