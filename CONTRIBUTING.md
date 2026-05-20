# Contributing to browser-use-vision

## Development Setup

```bash
# Clone and install
git clone https://github.com/Raidriar7170/browser-use-vision.git
cd browser-use-vision
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
make test

# Lint & format
make lint
make format
```

## Project Structure

- `browser_use_vision/` — Core package (adaptive strategy, grounding backends, enhanced agent)
- `tests/` — Unit tests (run without GPU/browser-use)
- `scripts/` — Server scripts and integration tests
- `benchmarks/` — Evaluation framework
- `demo/` — Gradio demo app

## Running Integration Tests

Requires a GPU server with Florence-2 and an LLM service:

```bash
# Start vision server (GPU)
make serve-vision

# Start LLM server (GPU)
make serve-llm

# Run integration tests
make test-integration
```

## Code Style

- Python 3.11+, type hints everywhere
- Ruff for linting/formatting (line-length=120)
- Async-first design (all agent/backend methods are async)
- Bilingual docstrings (English + Chinese)
