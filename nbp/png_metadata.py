from __future__ import annotations

import io
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from .params import GenerationParams, params_to_webui_text, parse_webui_text


PNG_PARAMETERS_KEY = "parameters"


def _bytes_from_unknown_image(image: Any) -> bytes | None:
    for attr in ("data", "image_bytes", "bytes"):
        value = getattr(image, attr, None)
        if isinstance(value, bytes):
            return value
    inline_data = getattr(image, "inline_data", None)
    if inline_data is not None:
        value = getattr(inline_data, "data", None)
        if isinstance(value, bytes):
            return value
    return None


def _to_pil_image(image: Any) -> Image.Image:
    if isinstance(image, Image.Image):
        return image

    data = _bytes_from_unknown_image(image)
    if data:
        with Image.open(io.BytesIO(data)) as opened:
            return opened.copy()

    save = getattr(image, "save", None)
    if callable(save):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        try:
            save(str(temp_path))
            with Image.open(temp_path) as opened:
                return opened.copy()
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass

    raise TypeError(f"Unsupported image object for PNG saving: {type(image)!r}")


def save_png_with_parameters(image: Any, path: str | Path, params: GenerationParams, enabled: bool = True) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pil_image = _to_pil_image(image)
    if enabled:
        info = PngInfo()
        info.add_text(PNG_PARAMETERS_KEY, params_to_webui_text(params))
        pil_image.save(path, pnginfo=info)
    else:
        pil_image.save(path)


def read_png_parameters(path: str | Path) -> tuple[GenerationParams, str]:
    with Image.open(path) as image:
        raw = image.info.get(PNG_PARAMETERS_KEY)
    if not raw:
        raise ValueError("此 PNG 不包含生成参数。")
    return parse_webui_text(raw), raw
