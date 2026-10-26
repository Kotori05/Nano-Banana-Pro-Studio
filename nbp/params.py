from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .config import ASPECT_RATIO_OPTIONS, DEFAULT_MODEL_OPTIONS, IMAGE_SIZE_OPTIONS, LAST_PARAMS_PATH, NANO_BANANA_2_LITE_MODEL


APP_JSON_PREFIX = "NanoBananaParams:"


@dataclass
class GenerationParams:
    prompt: str = ""
    model_name: str = DEFAULT_MODEL_OPTIONS[3]
    aspect_ratio: str = ASPECT_RATIO_OPTIONS[0]
    image_size: str = IMAGE_SIZE_OPTIONS[0]
    temperature: float = 0.9
    top_p: float = 0.95
    top_k: int = 40
    max_output_tokens: int = 8192
    system_instruction: str = ""
    enable_search: bool = False
    save_png_parameters: bool = True
    extra: dict[str, Any] = field(default_factory=dict)

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("extra", None)
        data["extra"] = dict(self.extra or {})
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "GenerationParams":
        data = dict(data or {})
        extra = data.pop("extra", {}) or {}
        allowed = cls.__dataclass_fields__.keys()
        clean = {k: v for k, v in data.items() if k in allowed}
        params = cls(**clean)
        params.extra = extra if isinstance(extra, dict) else {}
        params.normalize()
        return params

    def normalize(self) -> "GenerationParams":
        self.model_name = self.model_name or DEFAULT_MODEL_OPTIONS[3]
        self.aspect_ratio = normalize_aspect_ratio(self.aspect_ratio)
        self.image_size = self.image_size if self.image_size in IMAGE_SIZE_OPTIONS else IMAGE_SIZE_OPTIONS[0]
        self.temperature = float(self.temperature)
        self.top_p = float(self.top_p)
        self.top_k = int(self.top_k)
        self.max_output_tokens = int(self.max_output_tokens)
        self.enable_search = bool(self.enable_search)
        self.save_png_parameters = bool(self.save_png_parameters)
        if self.model_name == NANO_BANANA_2_LITE_MODEL:
            self.image_size = "1K"
            self.enable_search = False
            self.max_output_tokens = min(self.max_output_tokens, 4096)
        return self


def aspect_key(value: str | None) -> str:
    if not value:
        return "1:1"
    match = re.search(r"\d+\s*:\s*\d+", str(value))
    return match.group(0).replace(" ", "") if match else "1:1"


def normalize_aspect_ratio(value: str | None) -> str:
    key = aspect_key(value)
    for option in ASPECT_RATIO_OPTIONS:
        if option.startswith(key):
            return option
    return value or ASPECT_RATIO_OPTIONS[0]


def ui_aspect_to_vertex(value: str | None) -> str:
    return aspect_key(value)


def params_to_webui_text(params: GenerationParams) -> str:
    params = GenerationParams.from_dict(params.public_dict())
    lines = [params.prompt.strip()]
    if params.system_instruction.strip():
        lines.append(f"System instruction: {params.system_instruction.strip()}")
    app_json = json.dumps(params.public_dict(), ensure_ascii=False, separators=(",", ":"))
    lines.append(
        "Model: {model}, Size: {size}, Aspect ratio: {aspect}, Temperature: {temp}, "
        "Top P: {top_p}, Top K: {top_k}, Max output tokens: {tokens}, Search: {search}".format(
            model=params.model_name,
            size=params.image_size,
            aspect=ui_aspect_to_vertex(params.aspect_ratio),
            temp=params.temperature,
            top_p=params.top_p,
            top_k=params.top_k,
            tokens=params.max_output_tokens,
            search=params.enable_search,
        )
    )
    lines.append(f"{APP_JSON_PREFIX} {app_json}")
    return "\n".join(lines)


def parse_webui_text(text: str | None) -> GenerationParams:
    if not text:
        raise ValueError("PNG does not contain a parameters text block.")
    for line in text.splitlines():
        if line.startswith(APP_JSON_PREFIX):
            raw = line[len(APP_JSON_PREFIX):].strip()
            return GenerationParams.from_dict(json.loads(raw))

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    prompt_lines: list[str] = []
    param_line = ""
    system_instruction = ""
    for line in lines:
        if line.startswith("System instruction:"):
            system_instruction = line.split(":", 1)[1].strip()
            continue
        if "Model:" in line and ("Temperature:" in line or "Aspect ratio:" in line):
            param_line = line
            continue
        prompt_lines.append(line)

    data: dict[str, Any] = {"prompt": "\n".join(prompt_lines), "system_instruction": system_instruction}
    if param_line:
        mapping = {
            "Model": "model_name",
            "Size": "image_size",
            "Aspect ratio": "aspect_ratio",
            "Temperature": "temperature",
            "Top P": "top_p",
            "Top K": "top_k",
            "Max output tokens": "max_output_tokens",
            "Search": "enable_search",
        }
        for part in param_line.split(","):
            if ":" not in part:
                continue
            label, value = [x.strip() for x in part.split(":", 1)]
            key = mapping.get(label)
            if not key:
                continue
            if key in {"temperature", "top_p"}:
                data[key] = float(value)
            elif key in {"top_k", "max_output_tokens"}:
                data[key] = int(float(value))
            elif key == "enable_search":
                data[key] = value.lower() in {"true", "1", "yes", "on"}
            else:
                data[key] = value
    return GenerationParams.from_dict(data)


def save_last_params(params: GenerationParams) -> None:
    LAST_PARAMS_PATH.write_text(
        json.dumps(params.public_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_last_params() -> GenerationParams:
    if not LAST_PARAMS_PATH.exists():
        raise FileNotFoundError("还没有保存过上次生成参数。")
    return GenerationParams.from_dict(json.loads(LAST_PARAMS_PATH.read_text(encoding="utf-8")))


def format_params_preview(params: GenerationParams, raw_text: str | None = None) -> str:
    lines = [
        f"Prompt: {params.prompt}",
        f"Model: {params.model_name}",
        f"Aspect ratio: {params.aspect_ratio}",
        f"Image size: {params.image_size}",
        f"Temperature: {params.temperature}",
        f"Top P: {params.top_p}",
        f"Top K: {params.top_k}",
        f"Max output tokens: {params.max_output_tokens}",
        f"Search: {params.enable_search}",
    ]
    if params.system_instruction:
        lines.append(f"System instruction: {params.system_instruction}")
    if raw_text:
        lines.append("\n--- Raw PNG parameters ---\n" + raw_text)
    return "\n".join(lines)
