from __future__ import annotations

import mimetypes
import os
import threading
import time
from pathlib import Path
from pprint import pprint
from typing import Any

from google import genai
from google.genai import types

from .params import GenerationParams, save_last_params, ui_aspect_to_vertex
from .png_metadata import save_png_with_parameters


IMAGE_MODELS = {"gemini-2.5-flash-image", "gemini-3-pro-image-preview", "gemini-3.1-flash-image-preview"}


class GenerationService:
    def __init__(self, max_concurrency: int = 1) -> None:
        self._limit = max(1, int(max_concurrency))
        self._desired_limit = self._limit
        self._semaphore = threading.BoundedSemaphore(self._limit)
        self._lock = threading.Lock()
        self._active = 0
        self._waiting = 0

    @property
    def max_concurrency(self) -> int:
        return self._desired_limit

    def set_max_concurrency(self, value: int) -> None:
        value = max(1, int(value or 1))
        with self._lock:
            self._desired_limit = value
            if value == self._limit:
                return
            if self._active or self._waiting:
                return
            self._apply_limit_locked(value)

    def _apply_limit_locked(self, value: int) -> None:
        self._limit = value
        self._semaphore = threading.BoundedSemaphore(value)

    def generate(
        self,
        api_key: str,
        params: GenerationParams,
        history_messages: list[dict[str, Any]] | None = None,
        user_images: list[str] | None = None,
    ) -> tuple[str, list[str]]:
        semaphore = self._semaphore
        with self._lock:
            self._waiting += 1
        semaphore.acquire()
        with self._lock:
            self._waiting -= 1
            self._active += 1
        try:
            return call_gemini_vertex(api_key, params, history_messages or [], user_images or [])
        finally:
            semaphore.release()
            with self._lock:
                self._active -= 1
                if not self._active and not self._waiting and self._desired_limit != self._limit:
                    self._apply_limit_locked(self._desired_limit)


def create_client(explicit_key: str | None = None, project: str | None = None, location: str = "global") -> genai.Client:
    project_id = project or os.environ.get("GOOGLE_CLOUD_PROJECT")
    api_key = explicit_key or os.environ.get("GOOGLE_CLOUD_API_KEY")
    if project_id:
        try:
            return genai.Client(vertexai=True, project=project_id, location=location)
        except Exception as exc:
            print(f"[WARN] Vertex client failed, falling back to API key mode: {exc}")
    if api_key:
        return genai.Client(vertexai=False, api_key=api_key)
    raise RuntimeError("Cannot create Google GenAI client: no Vertex project or API key is configured.")


def build_generate_config(params: GenerationParams, want_image: bool, want_thinking: bool) -> types.GenerateContentConfig:
    safety_settings = [
        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
    ]
    cfg_kwargs: dict[str, Any] = {
        "temperature": params.temperature,
        "top_p": params.top_p,
        "top_k": params.top_k,
        "max_output_tokens": params.max_output_tokens,
        "safety_settings": safety_settings,
    }
    if params.enable_search:
        cfg_kwargs["tools"] = [{"google_search": {}}]
    if want_image:
        try:
            image_config = types.ImageConfig(
                aspect_ratio=ui_aspect_to_vertex(params.aspect_ratio),
                image_size=params.image_size,
            )
        except Exception as exc:
            print(f"[WARN] ImageConfig rejected image_size; using aspect ratio only: {exc}")
            image_config = types.ImageConfig(aspect_ratio=ui_aspect_to_vertex(params.aspect_ratio))
        cfg_kwargs["response_modalities"] = ["TEXT", "IMAGE"]
        cfg_kwargs["image_config"] = image_config
    if want_thinking:
        try:
            cfg_kwargs["thinking_config"] = types.ThinkingConfig(include_thoughts=True)
        except Exception as exc:
            print(f"[WARN] ThinkingConfig ignored: {exc}")
    return types.GenerateContentConfig(**cfg_kwargs)


def file_to_image_part(path: str) -> types.Part:
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        mime = "image/png"
    with open(path, "rb") as handle:
        return types.Part.from_bytes(data=handle.read(), mime_type=mime)


def _debug_print_send(model_name: str, params: GenerationParams, image_files: list[str], generate_config: Any) -> None:
    print("\n" + "=" * 80)
    print("[SEND] Gemini Request")
    print("Model:", model_name)
    if params.system_instruction:
        print("\n[System Instruction]\n", params.system_instruction)
    if params.prompt:
        print("\n[User Text]\n", params.prompt)
    if image_files:
        print("\n[User Images]")
        for idx, image in enumerate(image_files):
            print(f"  [{idx}] {image}")
    print("\n[Generate Config]")
    try:
        pprint(generate_config.model_dump())
    except Exception:
        pprint(generate_config)
    print("=" * 80 + "\n")


def _debug_print_recv(response: Any) -> None:
    print("\n" + "=" * 80)
    print("[RECV] Gemini Response")
    try:
        import json

        print(json.dumps(response.model_dump(), ensure_ascii=False, indent=2))
    except Exception:
        pprint(response)
    print("=" * 80 + "\n")


def _content_from_message(message: dict[str, Any]) -> types.Content | None:
    parts = []
    if message.get("text"):
        parts.append(types.Part.from_text(text=message["text"]))
    for image in message.get("images", []) or []:
        try:
            parts.append(file_to_image_part(image))
        except Exception as exc:
            print(f"[WARN] Skipped history image {image}: {exc}")
    if not parts:
        return None
    role = "user" if message.get("role") == "user" else "model"
    return types.Content(role=role, parts=parts)


def call_gemini_vertex(
    api_key: str,
    params: GenerationParams,
    history_messages: list[dict[str, Any]],
    user_images: list[str],
) -> tuple[str, list[str]]:
    params = GenerationParams.from_dict(params.public_dict())
    client = create_client(api_key, location="global")
    contents: list[types.Content] = []
    if params.system_instruction.strip():
        contents.append(types.Content(role="system", parts=[types.Part.from_text(text=params.system_instruction.strip())]))
    for message in history_messages or []:
        content = _content_from_message(message)
        if content:
            contents.append(content)

    current_parts = []
    if params.prompt:
        current_parts.append(types.Part.from_text(text=params.prompt))
    for image in user_images or []:
        try:
            current_parts.append(file_to_image_part(image))
        except Exception as exc:
            print(f"[WARN] Skipped input image {image}: {exc}")
    if current_parts:
        contents.append(types.Content(role="user", parts=current_parts))

    want_image = params.model_name in IMAGE_MODELS
    want_thinking = "thinking" in params.model_name.lower() or "3.1-pro" in params.model_name or "3-flash" in params.model_name
    generate_config = build_generate_config(params, want_image=want_image, want_thinking=want_thinking)
    _debug_print_send(params.model_name, params, user_images, generate_config)

    try:
        response = client.models.generate_content(
            model=params.model_name,
            contents=contents if len(contents) > 1 else (contents[0] if contents else params.prompt),
            config=generate_config,
        )
    except Exception as exc:
        raise RuntimeError(f"Gemini request failed: {exc}") from exc

    _debug_print_recv(response)
    text_chunks: list[str] = []
    generated_images: list[str] = []

    if not getattr(response, "candidates", None):
        feedback = getattr(response, "prompt_feedback", "No feedback")
        return f"Model returned no candidates. Feedback: {feedback}", []

    first_candidate = response.candidates[0]
    finish_reason = getattr(first_candidate, "finish_reason", "UNKNOWN")

    response_parts = getattr(response, "parts", None)
    if not response_parts:
        content = getattr(first_candidate, "content", None)
        response_parts = getattr(content, "parts", []) if content is not None else []

    for part in response_parts or []:
        if getattr(part, "thought", None):
            continue
        if getattr(part, "text", None):
            text_chunks.append(part.text)
            continue
        as_image = getattr(part, "as_image", None)
        if callable(as_image):
            image = as_image()
            if image is None:
                continue
            out_dir = Path("outputs")
            out_dir.mkdir(exist_ok=True)
            out_path = out_dir / f"{params.model_name}_{int(time.time() * 1000)}.png"
            save_png_with_parameters(image, out_path, params, params.save_png_parameters)
            generated_images.append(str(out_path))

    final_text = "\n".join(chunk.strip() for chunk in text_chunks if chunk.strip())
    if not final_text and not generated_images:
        if "SAFETY" in str(finish_reason):
            return f"Content was blocked by safety policy. Finish reason: {finish_reason}", []
        if finish_reason != "STOP":
            return f"Generation stopped without content. Finish reason: {finish_reason}", []
        return "API returned STOP with empty content.", []
    if not final_text and generated_images:
        final_text = "Image generated."
    save_last_params(params)
    return final_text, generated_images
