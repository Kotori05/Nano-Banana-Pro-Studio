from __future__ import annotations

import base64
import io
import math
import os
import uuid
from pathlib import Path
from typing import Any

import requests
from PIL import Image

from .config import OPENAI_IMAGE_MODELS
from .params import GenerationParams, aspect_key, save_last_params
from .png_metadata import save_png_with_parameters


OPENAI_API_URL = "https://api.openai.com/v1"
OPENAI_ASPECT_RATIOS = ("16:9", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "21:9")


def is_openai_image_model(model_name: str) -> bool:
    # Dated snapshots use the same API and capabilities as their model family.
    return any(model_name == name or model_name.startswith(name + "-") for name in OPENAI_IMAGE_MODELS)


def openai_image_size(aspect_ratio: str, image_size: str) -> str:
    """Map the existing K controls to OpenAI's edge, pixel and alignment limits."""
    width_ratio, height_ratio = map(int, aspect_key(aspect_ratio).split(":"))
    if min(width_ratio, height_ratio) <= 0 or not 1 / 3 <= width_ratio / height_ratio <= 3:
        raise ValueError("GPT Image 的宽高比必须在 1:3 到 3:1 之间；请选择 16:9、1:1、2:3 等比例。")
    long_edge = {"1K": 1024, "2K": 2048, "4K": 3840}.get(image_size)
    if long_edge is None:
        raise ValueError("GPT Image 图片尺寸请选择 1K、2K 或 4K。")
    ratio = width_ratio / height_ratio
    width = long_edge if ratio >= 1 else long_edge * ratio
    height = long_edge / ratio if ratio >= 1 else long_edge
    # A 4K square exceeds the pixel budget; narrow 1K images need more pixels.
    scale = min(1.0, math.sqrt(8_294_400 / (width * height)))
    scale = max(scale, math.sqrt(655_360 / (width * height)))
    width = max(16, int(width * scale) // 16 * 16)
    height = max(16, int(height * scale) // 16 * 16)
    # Rounding the short edge down can push a boundary ratio above 3:1.
    width = min(width, height * 3)
    height = min(height, width * 3)
    while width * height < 655_360:
        width += 16
        height += 16
    return f"{width}x{height}"


def _request_prompt(params: GenerationParams, history_messages: list[dict[str, Any]]) -> str:
    parts = []
    if params.system_instruction.strip():
        parts.append("Instructions:\n" + params.system_instruction.strip())
    for message in history_messages:
        if message.get("text"):
            role = "User" if message.get("role") == "user" else "Assistant"
            parts.append(f"{role}: {message['text']}")
    parts.append("Current request:\n" + (params.prompt.strip() or "Create an image using the supplied references."))
    prompt = "\n\n".join(parts)
    if len(prompt) > 32000:
        raise ValueError("GPT Image 请求文本超过 32000 字符，请缩短提示词或清空历史对话。")
    return prompt


def _reference_files(history_messages: list[dict[str, Any]], user_images: list[str]) -> list[str]:
    paths = []
    for message in history_messages:
        paths.extend(message.get("images", []) or [])
    paths.extend(user_images)
    paths = list(dict.fromkeys(str(path) for path in paths))
    if len(paths) > 16:
        raise ValueError("GPT Image 单次最多支持 16 张参考图（含历史对话图片），请减少图片或清空对话。")
    return paths


def call_openai_images(
    api_key: str,
    params: GenerationParams,
    history_messages: list[dict[str, Any]],
    user_images: list[str],
) -> tuple[str, list[str]]:
    key = (api_key or "").strip() or os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("请填写 OpenAI API Key，或设置 OPENAI_API_KEY 环境变量 / OPENAI_API_KEY.txt。")
    params = GenerationParams.from_dict(params.public_dict())
    size = openai_image_size(params.aspect_ratio, params.image_size)
    payload = {
        "model": params.model_name,
        "prompt": _request_prompt(params, history_messages),
        "size": size,
        "n": 1,
        "output_format": "png",
    }
    references = _reference_files(history_messages, user_images)
    # Converting references to PNG supports every image type accepted by the UI.
    files = []
    for index, path in enumerate(references):
        try:
            with Image.open(path) as source:
                buffer = io.BytesIO()
                source.convert("RGBA" if "A" in source.getbands() else "RGB").save(buffer, format="PNG")
                data = buffer.getvalue()
        except (OSError, ValueError) as exc:
            raise ValueError(f"无法读取 GPT Image 参考图: {path}") from exc
        if len(data) >= 50 * 1024 * 1024:
            raise ValueError(f"GPT Image 每张参考图必须小于 50 MB: {path}")
        files.append(("image[]", (f"reference_{index + 1}.png", data, "image/png")))

    endpoint = "edits" if files else "generations"
    kwargs: dict[str, Any] = {"data": payload, "files": files} if files else {"json": payload}
    try:
        response = requests.post(
            f"{OPENAI_API_URL}/images/{endpoint}",
            headers={"Authorization": f"Bearer {key}"},
            timeout=(15, 600),
            **kwargs,
        )
    except requests.Timeout:
        raise RuntimeError("OpenAI request timed out，请稍后重试。") from None
    except requests.RequestException:
        raise RuntimeError("OpenAI connection failed，请检查网络连接后重试。") from None

    try:
        body = response.json()
    except ValueError:
        raise RuntimeError(f"OpenAI 返回了非 JSON 响应 (HTTP {response.status_code})。") from None
    finally:
        response.close()
    if not isinstance(body, dict):
        raise RuntimeError("OpenAI 返回了无效的图像响应。")
    if not response.ok or body.get("error"):
        error = body.get("error") or {}
        message = error.get("message", "请求失败") if isinstance(error, dict) else str(error)
        message = str(message).replace(key, "[REDACTED]")
        raise RuntimeError(f"OpenAI request failed (HTTP {response.status_code}): {message}")
    results = body.get("data")
    if not isinstance(results, list) or not results:
        raise RuntimeError("OpenAI 未返回图像，请检查提示词或模型访问权限。")

    params.extra["openai_size"] = size
    generated_images = []
    for result in results:
        encoded = result.get("b64_json") if isinstance(result, dict) else None
        if not encoded:
            raise RuntimeError("OpenAI 图像响应缺少 b64_json 数据。")
        try:
            data = base64.b64decode(encoded, validate=True)
            with Image.open(io.BytesIO(data)) as image:
                out_path = Path("outputs") / f"{params.model_name}_{uuid.uuid4().hex}.png"
                save_png_with_parameters(image, out_path, params, params.save_png_parameters)
        except (OSError, ValueError, TypeError):
            raise RuntimeError("OpenAI 返回的图像数据无效。") from None
        generated_images.append(str(out_path))
    save_last_params(params)
    return f"Image generated. ({params.model_name}, {size})", generated_images
