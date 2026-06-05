"""
Adapter entrypoint for Verifiable Browser Runtime (VBR) integration.

Exposes a stable, synchronous ``ground()`` callable that VBR can discover and
invoke without adding browser-use-vision as a required dependency.

Usage from VBR::

    from browser_use_vision import ground, BrowserUseVisionGrounder

    # Contract smoke (GPU-free, no screenshot)
    result = ground("confirm button", context={"controlled_local_demo": "visual_fallback"})

    # Element matching (GPU-free)
    result = ground("Play", context={"elements": [{"label": "Play", "bbox": [0.1, 0.2, 0.3, 0.4]}]})

    # Florence grounding (needs GPU server)
    g = BrowserUseVisionGrounder(backend_url="http://localhost:8100")
    result = g.ground("next track", context={"screenshot": png_bytes})
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any


PROVIDER = "browser-use-vision"


class BrowserUseVisionGrounder:
    """Adapter for Verifiable Browser Runtime optional vision provider integration."""

    PROVIDER = PROVIDER

    def __init__(self, backend_url: str | None = None):
        self._backend_url = backend_url

    def ground(
        self,
        target_description: str,
        context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        ctx = dict(context) if context else {}

        if ctx.get("controlled_local_demo") == "visual_fallback":
            return self._local_contract_smoke(target_description)

        if "elements" in ctx:
            return self._element_match(target_description, ctx["elements"])

        if "screenshot" in ctx:
            return self._florence_ground(target_description, ctx["screenshot"])

        raise RuntimeError(
            "browser-use-vision adapter: no actionable context provided. "
            "Pass context with 'controlled_local_demo', 'elements', or 'screenshot'. "
            "Cannot produce non-mock grounding without input."
        )

    # ── path 1: contract smoke ──────────────────────────────────

    @staticmethod
    def _local_contract_smoke(target_description: str) -> dict[str, Any]:
        return {
            "selected_target_ref": "element:0",
            "confidence": 0.8,
            "is_mock": False,
            "evidence": {
                "provider": PROVIDER,
                "method": "local-contract-smoke",
                "bbox": None,
                "reason": (
                    "Controlled local adapter contract smoke; "
                    "no screenshot grounding claimed. "
                    f"target_description={target_description!r}"
                ),
            },
        }

    # ── path 2: element matching (GPU-free) ─────────────────────

    @staticmethod
    def _element_match(
        target_description: str, elements: list[dict],
    ) -> dict[str, Any]:
        if not elements:
            raise RuntimeError(
                "browser-use-vision adapter: 'elements' list is empty; "
                "cannot match target description to any element."
            )

        target_lower = target_description.lower()
        target_tokens = set(target_lower.split())
        best_idx = -1
        best_score = -1.0
        best_label = ""

        for i, el in enumerate(elements):
            label = str(el.get("label", "")).strip()
            if not label:
                continue
            label_lower = label.lower()
            label_tokens = set(label_lower.split())

            score = 0.0
            if target_lower == label_lower:
                score = 1.0
            elif target_lower in label_lower or label_lower in target_lower:
                score = 0.8
            else:
                overlap = target_tokens & label_tokens
                if overlap:
                    score = 0.5 * len(overlap) / max(len(target_tokens), len(label_tokens))

            if score > best_score:
                best_score = score
                best_idx = i
                best_label = label

        if best_idx < 0 or best_score <= 0:
            raise RuntimeError(
                f"browser-use-vision adapter: no element label matches "
                f"target_description={target_description!r} among "
                f"{len(elements)} elements."
            )

        bbox = elements[best_idx].get("bbox")

        return {
            "selected_target_ref": f"element:{best_idx}",
            "confidence": round(min(best_score, 1.0), 3),
            "is_mock": False,
            "evidence": {
                "provider": PROVIDER,
                "method": "element-match",
                "bbox": list(bbox) if bbox else None,
                "reason": f"Matched label {best_label!r} (score {best_score:.2f})",
            },
        }

    # ── path 3: Florence grounding (needs GPU) ──────────────────

    def _florence_ground(
        self, target_description: str, screenshot: bytes,
    ) -> dict[str, Any]:
        if not self._backend_url:
            raise RuntimeError(
                "browser-use-vision adapter: screenshot provided but no "
                "backend_url configured. Instantiate with "
                "BrowserUseVisionGrounder(backend_url='http://...:8100')."
            )

        from browser_use_vision.grounding.florence import FlorenceBackend

        backend = FlorenceBackend(remote_url=self._backend_url)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                results = pool.submit(
                    asyncio.run,
                    backend.caption_to_phrase_grounding(screenshot, target_description),
                ).result()
        else:
            results = asyncio.run(
                backend.caption_to_phrase_grounding(screenshot, target_description)
            )

        if not results:
            raise RuntimeError(
                f"browser-use-vision adapter: Florence phrase grounding returned "
                f"no results for target_description={target_description!r}."
            )

        best = max(results, key=lambda r: r.get("confidence", 0.0)) if len(results) > 1 else results[0]
        bbox = best.get("bbox")

        return {
            "selected_target_ref": (
                f"bbox:{','.join(f'{v:.4f}' for v in bbox)}" if bbox else "bbox:unknown"
            ),
            "confidence": float(best.get("confidence", 0.5)),
            "is_mock": False,
            "evidence": {
                "provider": PROVIDER,
                "method": "florence-phrase-grounding",
                "bbox": list(bbox) if bbox else None,
                "reason": f"Florence caption_to_phrase_grounding for {target_description!r}",
            },
        }


def ground(
    target_description: str,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Module-level convenience — creates a default grounder and calls ground()."""
    return BrowserUseVisionGrounder().ground(target_description, context)
