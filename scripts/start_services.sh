#!/bin/bash
# 启动 Vision API + LLM API 服务（用绝对路径）
VENV=/mnt/data/minghongsun/browser-use-vision/.venv
PYTHON=$VENV/bin/python3
PROJECT=/mnt/data/minghongsun/browser-use-vision
export PYTHONPATH=$PROJECT

cd $PROJECT

# Vision API on GPU 0
nohup $PYTHON -m browser_use_vision.server \
  --backend florence \
  --model-name /mnt/data/minghongsun/models/florence-2-large \
  --port 8100 \
  > $PROJECT/server.log 2>&1 &
echo "VisionAPI PID: $!"

# LLM API on GPU 1
nohup $PYTHON scripts/llm_server.py \
  --model-dir /mnt/data/minghongsun/models/qwen2.5-7b-instruct \
  --port 8200 --gpu 1 \
  > $PROJECT/llm_server.log 2>&1 &
echo "LLM_API PID: $!"
