from __future__ import annotations

import os
import re
import uuid
from datetime import datetime
from pathlib import Path

from PIL import Image

from .params import GenerationParams, params_to_webui_text


def save_as_jpg_under_1mb(src_path: str, dst_path: str, max_bytes: int = 1024 * 1024) -> None:
    image = Image.open(src_path).convert("RGB")
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    quality = 92
    width, height = image.size
    while True:
        image.save(dst_path, format="JPEG", quality=quality, optimize=True)
        if os.path.getsize(dst_path) <= max_bytes:
            return
        quality -= 8
        if quality >= 40:
            continue
        new_w = max(256, int(width * 0.85))
        new_h = max(256, int(height * 0.85))
        if new_w == width and new_h == height:
            image.save(dst_path, format="JPEG", quality=40, optimize=True)
            return
        image = image.resize((new_w, new_h))
        width, height = image.size
        quality = 88


def ensure_export_session_dir(out_dir: str = "exports", base_name: str = "chat_session") -> str:
    Path(out_dir).mkdir(exist_ok=True)
    sid = f"{base_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    session_dir = Path(out_dir) / sid
    (session_dir / "images").mkdir(parents=True, exist_ok=True)
    md_path = session_dir / "chat.md"
    if not md_path.exists():
        md_path.write_text(
            f"# Chat Log\n\n- Session: {sid}\n- Created: {datetime.now().isoformat(timespec='seconds')}\n",
            encoding="utf-8",
        )
    return str(session_dir)


def append_md(md_path: str | Path, text: str) -> None:
    with open(md_path, "a", encoding="utf-8") as handle:
        handle.write(text if text.endswith("\n") else text + "\n")


def log_turn_to_md(
    session_dir: str,
    user_text: str,
    user_image_paths: list[str],
    assistant_text: str,
    assistant_image_paths: list[str],
    params: GenerationParams | None = None,
) -> str:
    if not session_dir:
        session_dir = ensure_export_session_dir()
    images_dir = Path(session_dir) / "images"
    md_path = Path(session_dir) / "chat.md"

    def convert_many(paths: list[str], prefix: str) -> list[str]:
        rels = []
        for src in paths or []:
            if not src or not os.path.exists(src):
                continue
            name = f"{datetime.now().strftime('%H%M%S')}_{uuid.uuid4().hex[:6]}_{prefix}.jpg"
            dst = images_dir / name
            save_as_jpg_under_1mb(src, str(dst))
            rels.append(f"images/{name}")
        return rels

    block = ["\n---\n", f"## Turn @ {datetime.now().isoformat(timespec='seconds')}\n", "### User\n"]
    if user_text:
        block.append(user_text.strip() + "\n")
    for rel in convert_many(user_image_paths, "u"):
        block.append(f"\n![]({rel})\n")
    block.append("\n### Assistant\n")
    if assistant_text:
        block.append(assistant_text.strip() + "\n")
    if params:
        block.append("\n```text\n" + params_to_webui_text(params) + "\n```\n")
    for rel in convert_many(assistant_image_paths, "a"):
        block.append(f"\n![]({rel})\n")
    append_md(md_path, "\n".join(block))
    return session_dir


def export_chat_to_md(history: list[dict], out_base_name: str = "chat_export", out_dir: str = "exports") -> str:
    safe_name = re.sub(r"[^a-zA-Z0-9_\-]+", "_", (out_base_name or "chat_export").strip() or "chat_export")
    export_root = Path(out_dir) / safe_name
    images_dir = export_root / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    img_pat = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
    used_map: dict[str, str] = {}
    img_counter = 0

    def convert_one(src: str) -> str:
        nonlocal img_counter
        src_norm = src.strip().strip('"').strip("'").replace("\\", "/")
        if src_norm in used_map:
            return used_map[src_norm]
        if not os.path.exists(src_norm):
            return src
        img_counter += 1
        rel = f"images/{img_counter}.jpg"
        save_as_jpg_under_1mb(src_norm, str(export_root / rel))
        used_map[src_norm] = rel
        return rel

    lines = [f"# Chat Export\n\n- Exported: {datetime.now().isoformat(timespec='seconds')}\n"]
    for msg in history or []:
        role = msg.get("role", "unknown")
        content = img_pat.sub(lambda m: m.group(0).replace(m.group(1), convert_one(m.group(1))), msg.get("content", ""))
        lines.append(f"\n## {role.capitalize()}\n")
        lines.append(content.strip() + "\n")
    md_path = export_root / f"{safe_name}.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return str(md_path)


def log_queue_group_to_md(group: dict, out_dir: str = "exports") -> str:
    session_dir = ensure_export_session_dir(out_dir, "queue_session")
    md_path = Path(session_dir) / "chat.md"
    params = group.get("base_params")
    block = [
        "\n---\n",
        f"## Queue Group @ {datetime.now().isoformat(timespec='seconds')}\n",
        f"- ID: {group.get('id')}\n",
        f"- Status: {group.get('status')}\n",
        f"- Progress: {group.get('done_count')}/{group.get('total_count')}\n",
        "\n### Prompt\n",
        str(group.get("prompt", "")).strip() + "\n",
    ]
    if isinstance(params, GenerationParams):
        block.append("\n### Base Parameters\n```text\n" + params_to_webui_text(params) + "\n```\n")
    block.append("\n### Items\n")
    for item in group.get("items", []):
        block.append(f"\n#### Item {item.get('index', 0) + 1}: {item.get('status')}\n")
        if item.get("error"):
            block.append(f"Error: {item.get('error')}\n")
        item_params = item.get("params")
        if isinstance(item_params, GenerationParams):
            block.append("```text\n" + params_to_webui_text(item_params) + "\n```\n")
        for image in item.get("images", []):
            block.append(f"![]({str(image).replace(os.sep, '/')})\n")
    append_md(md_path, "\n".join(block))
    return session_dir

