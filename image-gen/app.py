"""
Lightweight proxy: HuggingFace Inference API → OpenAI-compatible /v1/images/generations.

OpenWebUI sends requests in OpenAI format. This service translates them
to HuggingFace's text-to-image API and returns base64-encoded images.

Supported HF models (text-to-image):
  - stabilityai/stable-diffusion-xl-base-1.0
  - black-forest-labs/FLUX.1-schnell
  - black-forest-labs/FLUX.1-dev
  - stabilityai/stable-diffusion-3.5-large
  - any model on HF Hub with text-to-image pipeline

Usage:
  HF_TOKEN=hf_xxx python app.py
  HF_TOKEN=hf_xxx HF_IMAGE_MODEL=black-forest-labs/FLUX.1-schnell python app.py
"""

from __future__ import annotations

import base64
import io
import json
import os
import time
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

app = FastAPI(title="HF Image Gen Proxy")

HF_TOKEN = os.environ.get("HF_TOKEN", "")
HF_API_URL = os.environ.get("HF_API_URL", "https://router.huggingface.co/hf-inference/models")
HF_DEFAULT_MODEL = os.environ.get("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell")
TIMEOUT = int(os.environ.get("HF_TIMEOUT", "120"))

# Model aliases for convenience
MODEL_ALIASES = {
    "flux-schnell": "black-forest-labs/FLUX.1-schnell",
    "flux-dev": "black-forest-labs/FLUX.1-dev",
    "sdxl": "stabilityai/stable-diffusion-xl-base-1.0",
    "sd3.5": "stabilityai/stable-diffusion-3.5-large",
    "sd3.5-turbo": "stabilityai/stable-diffusion-3.5-large-turbo",
}


class ImageRequest(BaseModel):
    prompt: str
    model: Optional[str] = None
    n: int = Field(default=1, ge=1, le=4)
    size: Optional[str] = "1024x1024"
    response_format: Optional[str] = "b64_json"


@app.get("/healthz")
def health():
    return {"status": "ok", "default_model": HF_DEFAULT_MODEL}


@app.get("/v1/models")
def list_models():
    """List available image generation models."""
    models = []
    for alias, model_id in MODEL_ALIASES.items():
        models.append({
            "id": alias,
            "object": "model",
            "owned_by": model_id.split("/")[0],
        })
    # Also include the default model
    models.append({
        "id": HF_DEFAULT_MODEL,
        "object": "model",
        "owned_by": HF_DEFAULT_MODEL.split("/")[0],
    })
    return {"object": "list", "data": models}


@app.post("/v1/images/generations")
async def generate_image(req: ImageRequest, authorization: Optional[str] = Header(None)):
    """Generate images via HuggingFace Inference API."""
    token = HF_TOKEN
    if authorization and authorization.startswith("Bearer "):
        # Allow overriding the token via Authorization header
        auth_token = authorization.removeprefix("Bearer ").strip()
        if auth_token and auth_token != "not-used":
            token = auth_token

    if not token:
        raise HTTPException(status_code=401, detail="HF_TOKEN not configured")

    # Resolve model
    model = req.model or HF_DEFAULT_MODEL
    model = MODEL_ALIASES.get(model, model)

    # Parse size
    width, height = 1024, 1024
    if req.size:
        try:
            w, h = req.size.lower().split("x")
            width, height = int(w), int(h)
        except ValueError:
            pass

    url = f"{HF_API_URL}/{model}"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "inputs": req.prompt,
        "parameters": {
            "width": width,
            "height": height,
        },
    }

    images = []
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for _ in range(req.n):
            resp = await client.post(url, headers=headers, json=payload)

            if resp.status_code == 503:
                # Model loading — wait and retry once
                wait_time = 30
                try:
                    body = resp.json()
                    wait_time = min(body.get("estimated_time", 30), 120)
                except Exception:
                    pass
                await _wait(wait_time)
                resp = await client.post(url, headers=headers, json=payload)

            if resp.status_code != 200:
                detail = resp.text[:500]
                raise HTTPException(status_code=resp.status_code, detail=f"HF API error: {detail}")

            # HF returns raw image bytes
            img_b64 = base64.b64encode(resp.content).decode()
            images.append({"b64_json": img_b64})

    return JSONResponse({
        "created": int(time.time()),
        "data": images,
    })


async def _wait(seconds: float):
    import asyncio
    print(f"[image-gen] Model loading, waiting {seconds:.0f}s...")
    await asyncio.sleep(seconds)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "9100"))
    uvicorn.run(app, host="0.0.0.0", port=port)
