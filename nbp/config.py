from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Any


CONFIG_PATH = Path("config.json")
LAST_PARAMS_PATH = Path("last_params.json")

DEFAULT_MODEL_OPTIONS = [
    "gemini-2.5-flash",
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-3-pro-image-preview",
    "gemini-3.1-flash-image-preview",
    "gemini-2.5-flash-image",
]

ASPECT_RATIO_OPTIONS = [
    "16:9 横版风景 5504x3072",
    "1:1 正方形 4096x4096",
    "2:3 竖版照片 3392x5056",
    "3:2 横版照片 5056x3392",
    "3:4 竖版海报 3584x4800",
    "4:3 传统横版 4800x3584",
    "4:5 竖版构图 3712x4608",
    "5:4 经典横版 4608x3712",
    "9:16 竖屏人像 3072x5504",
    "21:9 超宽银幕 6336x2688",
]

IMAGE_SIZE_OPTIONS = ["4K", "2K", "1K"]

DEFAULT_ADVANCED_CONFIG: dict[str, Any] = {
    "temperature": 0.9,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 8192,
    "system_instruction": "",
}


def find_free_port(start: int = 7860, end: int = 7880, host: str = "127.0.0.1") -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in range {start}-{end}")


def load_google_api_key_from_file() -> None:
    vertex_json_path = Path("GOOGLE_CLOUD_API_KEY.json")
    if vertex_json_path.exists() and vertex_json_path.is_file():
        try:
            data = json.loads(vertex_json_path.read_text(encoding="utf-8"))
            project_id = data.get("project_id")
            if project_id:
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(vertex_json_path.resolve())
                os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
                print(f"[INFO] Loaded Vertex credentials: {vertex_json_path.name} ({project_id})")
            else:
                print(f"[WARN] {vertex_json_path} has no project_id; Vertex credentials skipped.")
        except Exception as exc:
            print(f"[ERROR] Failed to read Vertex credentials: {exc}")

    api_key_txt_path = Path("GOOGLE_CLOUD_API_KEY.txt")
    if api_key_txt_path.exists() and api_key_txt_path.is_file():
        try:
            key = api_key_txt_path.read_text(encoding="utf-8").strip()
            if key:
                os.environ["GOOGLE_CLOUD_API_KEY"] = key
                print(f"[INFO] Loaded API key from {api_key_txt_path.name}")
        except Exception as exc:
            print(f"[ERROR] Failed to read API key: {exc}")


def load_presets_from_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            presets = data.get("presets")
            return presets if isinstance(presets, dict) else data
    except Exception as exc:
        print(f"[WARN] Failed to read config.json: {exc}")
    return {}


def save_presets_to_config(presets: dict[str, Any]) -> None:
    data = {"presets": presets}
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
