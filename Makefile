.PHONY: test lint typecheck format clean serve-vision serve-llm

# Run unit tests (CPU only, no browser-use dependency needed)
test:
	python -m pytest tests/ -v --tb=short

# Run full integration tests (requires GPU server with vision+llm services)
test-integration:
	PYTHONPATH=. python scripts/test_agent_integration.py

# Type checking with pyright
typecheck:
	pyright browser_use_vision/

# Lint with ruff
lint:
	ruff check browser_use_vision/ tests/ scripts/

# Format with ruff
format:
	ruff format browser_use_vision/ tests/ scripts/

# Start Florence-2 vision server (GPU required)
serve-vision:
	python browser_use_vision/server.py --port 8100

# Start Qwen LLM server (GPU required)
serve-llm:
	python scripts/llm_server.py --port 8200

# Clean build artifacts
clean:
	rm -rf __pycache__ */__pycache__ */*/__pycache__
	rm -rf .pytest_cache .ruff_cache
	rm -rf dist/ build/ *.egg-info
	rm -rf benchmarks/results/*.json
