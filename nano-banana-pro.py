## Ethical Statement

# This project is released under the GNU AGPL v3 license.

# It is intended for:
# - Free personal use
# - Free research use
# - Free non-commercial sharing
# - Open collaborative improvement

# This project is **NOT intended to be used for**:
# - Knowledge-paywall products
# - Information arbitrage
# - Closed-source commercial GUI repackaging
# - Paid courses based primarily on this tool without original contribution

# If you use this project commercially, you must:
# - Open-source all your modifications under AGPL v3
# - Clearly credit the original project
# - Notify users that a free open-source version exists

# Respect creators. Respect users.


import os
import mimetypes
from typing import List, Dict, Any, Tuple

import gradio as gr
from google import genai
from google.genai import types

import os
from pathlib import Path
import json

import re
from datetime import datetime
from PIL import Image

import uuid
from datetime import datetime
import socket

from pprint import pprint
import importlib.util
import sys

# 预设配置文件路径
CONFIG_PATH = Path("config.json")

# 动态加载插件
def load_plugins_from_dir(plugin_dir: str = "plugins"):
    """
    动态扫描指定目录，加载包含 create_tab 函数的插件
    """
    if not os.path.exists(plugin_dir):
        print(f"[INFO] 插件目录 {plugin_dir} 不存在，已跳过。")
        return

    # 遍历目录下的 .py 文件
    for filename in os.listdir(plugin_dir):
        if filename.endswith(".py") and not filename.startswith("__"):
            file_path = os.path.join(plugin_dir, filename)
            module_name = filename[:-3] # 去掉 .py
            
            try:
                # 动态加载模块
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    
                    # 检查是否存在 create_tab 函数
                    if hasattr(module, "create_tab") and callable(module.create_tab):
                        print(f"[PLUGIN] 正在加载插件: {filename} ...")
                        # 执行插件构建逻辑
                        module.create_tab()
                    else:
                        print(f"[PLUGIN] 跳过 {filename}: 未找到 'create_tab' 函数")
            except Exception as e:
                print(f"[ERROR] 加载插件 {filename} 失败: {e}")

# 打印请求报文
def _debug_print_send(model_name, system_instruction, user_text, image_files, generate_config=None, contents=None):
    print("\n" + "=" * 80)
    print("[SEND] Gemini Request")
    print("Model:", model_name)

    if system_instruction:
        print("\n[System Instruction]\n", system_instruction)

    if user_text:
        print("\n[User Text]\n", user_text)

    if image_files:
        print("\n[User Images]")
        for i, img in enumerate(image_files):
            p = img.name if hasattr(img, "name") else img
            print(f"  [{i}] {p}")

    if contents is not None:
        print("\n[Contents]")
        pprint(contents)

    if generate_config is not None:
        print("\n[Generate Config]")
        # google-genai 的对象通常有 model_dump；没有就 pprint
        try:
            pprint(generate_config.model_dump())
        except Exception:
            pprint(generate_config)

    print("=" * 80 + "\n")

# 打印接受报文
def _debug_print_recv(response):
    import json
    print("\n" + "=" * 80)
    print("[RECV] Gemini Response")
    try:
        print(json.dumps(response.model_dump(), ensure_ascii=False, indent=2))
    except Exception:
        pprint(response)
    print("=" * 80 + "\n")

def find_free_port(start: int = 7860, end: int = 7880, host: str = "127.0.0.1") -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in range {start}-{end}")

def load_presets_from_config() -> Dict[str, Any]:
    """
    从 config.json 读取参数预设，格式：
    {
      "presets": {
        "名称": { ...参数... },
        ...
      }
    }
    """
    if not CONFIG_PATH.exists():
        return {}
    try:
        data = json.load(CONFIG_PATH.open("r", encoding="utf-8"))
        if isinstance(data, dict):
            if "presets" in data and isinstance(data["presets"], dict):
                return data["presets"]
            # 兼容旧格式：整个 json 就是 presets
            return data
    except Exception as e:
        print(f"[WARN] 读取 config.json 失败：{e}")
    return {}


def save_presets_to_config(presets: Dict[str, Any]) -> None:
    """
    将预设写回 config.json
    """
    data = {"presets": presets}
    try:
        CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[INFO] 已保存参数预设到 {CONFIG_PATH}")
    except Exception as e:
        print(f"[ERROR] 写入 config.json 失败：{e}")


def save_preset(
    preset_name: str,
    presets: Dict[str, Any],
    model_name: str,
    aspect_ratio: str,
    image_size: str,
    temperature: float,
    top_p: float,
    top_k: int,
    max_output_tokens: int,
    system_instruction: str,
):
    """
    Gradio 回调：保存当前参数为一个预设。
    返回更新后的 presets_state 和 preset_dropdown。
    """
    name = (preset_name or "").strip() or "default"
    presets = dict(presets or {})
    presets[name] = {
        "model_name": model_name,
        "aspect_ratio": aspect_ratio,
        "image_size": image_size,
        "temperature": float(temperature),
        "top_p": float(top_p),
        "top_k": int(top_k),
        "max_output_tokens": int(max_output_tokens),
        "system_instruction": system_instruction,
    }
    save_presets_to_config(presets)
    choices = list(presets.keys())
    return presets, gr.update(choices=choices, value=name)


def load_preset(
    selected_name: str,
    presets: Dict[str, Any],
):
    """
    Gradio 回调：根据选择的预设，加载参数到 UI。
    返回顺序：model_name, aspect_ratio, image_size,
             temperature, top_p, top_k, max_output_tokens, system_instruction
    """
    if not selected_name or selected_name not in (presets or {}):
        # 不改动当前值
        upd = gr.update()
        return upd, upd, upd, upd, upd, upd, upd, upd

    p = presets[selected_name]
    def get_or_update(key, default=None):
        return p.get(key, default if default is not None else gr.update())

    return (
        get_or_update("model_name"),
        get_or_update("aspect_ratio"),
        get_or_update("image_size"),
        get_or_update("temperature"),
        get_or_update("top_p"),
        get_or_update("top_k"),
        get_or_update("max_output_tokens"),
        get_or_update("system_instruction", ""),
    )


def delete_preset(
    selected_name: str,
    presets: Dict[str, Any],
):
    """
    Gradio 回调：删除当前选中的预设。
    返回更新后的 presets_state 和 preset_dropdown。
    """
    presets = dict(presets or {})
    if selected_name in presets:
        del presets[selected_name]
        save_presets_to_config(presets)
    choices = list(presets.keys())
    new_value = choices[0] if choices else None
    return presets, gr.update(choices=choices, value=new_value)

def load_google_api_key_from_file() -> None:
    """
    尝试同时加载 'GOOGLE_CLOUD_API_KEY.json' (Vertex) 和 'GOOGLE_CLOUD_API_KEY.txt' (AI Studio)。
    将所有找到的凭证都写入环境变量，供后续逻辑选用。
    """
    # === 1. 读取 Vertex JSON (Service Account) ===
    vertex_json_path = Path("GOOGLE_CLOUD_API_KEY.json")
    if vertex_json_path.exists() and vertex_json_path.is_file():
        try:
            abs_path = str(vertex_json_path.resolve())
            with open(vertex_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                project_id = data.get("project_id")
            
            if project_id:
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = abs_path
                os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
                print(f"[INFO] 已加载 Vertex 凭证: {vertex_json_path.name} (Project: {project_id})")
            else:
                print(f"[WARN] {vertex_json_path} 缺少 'project_id' 字段，跳过 Vertex 加载。")
        except Exception as e:
            print(f"[ERROR] 读取 Vertex JSON 失败: {e}")
    
    # === 2. 读取 AI Studio API Key ===
    # (不管上面是否成功，这里都继续读，作为备用)
    api_key_txt_path = Path("GOOGLE_CLOUD_API_KEY.txt")
    if api_key_txt_path.exists() and api_key_txt_path.is_file():
        try:
            key = api_key_txt_path.read_text(encoding="utf-8").strip()
            if key:
                os.environ["GOOGLE_CLOUD_API_KEY"] = key
                print(f"[INFO] 已加载 API Key: {api_key_txt_path.name}")
            else:
                print(f"[WARN] {api_key_txt_path} 内容为空。")
        except Exception as e:
            print(f"[ERROR] 读取 API Key TXT 失败: {e}")

# ========== 基本配置 ==========

DEFAULT_MODEL_OPTIONS = [
    "gemini-2.5-flash",          # 文本/多模态输入，文本输出（官方 quickstart 推荐）
    "gemini-3-pro-preview",      # 3 Pro 语言模型（多模态输入，文本输出）
    "gemini-3-pro-image-preview",# 3 Pro 图像生成
    "gemini-2.5-flash-image",    # 2.5 图像生成
]


# 与 Vertex 示例类似的宽高比 & 尺寸
ASPECT_RATIO_OPTIONS = [
    "1:1 正方形4096x4096",
    "2:3 照片3392x5056",
    "3:2 横版照片5056x3392",    
    "3:4 竖版海报3584x4800",
    "4:3 传统横版4800x3584",
    "4:5 证件照3712x4608",
    "5:4 老屏幕4608x3712",
    "9:16 人像3072x5504",
    "16:9 风景5504x3072",
    "21:9 超宽屏6336x2688"
    ]
# 电影级宽屏 
# """
# 1:1       1024x1024	1210	2048x2048	1210	4096x4096	2000
# 2:3	    848x1264	1210	1696x2528	1210	3392x5056	2000
# 3:2	    1264x848	1210	2528x1696	1210	5056x3392	2000
# 3:4	    896x1200	1210	1792x2400	1210	3584x4800	2000
# 4:3	    1200x896	1210	2400x1792	1210	4800x3584	2000
# 4:5	    928x1152	1210	1856x2304	1210	3712x4608	2000
# 5:4	    1152x928	1210	2304x1856	1210	4608x3712	2000
# 9:16      768x1376	1210	1536x2752	1210	3072x5504	2000
# 16:9	    1376x768	1210	2752x1536	1210	5504x3072	2000
# 21:9	    1584x672	1210	3168x1344	1210	6336x2688	2000
# """


IMAGE_SIZE_OPTIONS = [
    "1K",
    "2K",
    "4K",
]

DEFAULT_ADVANCED_CONFIG: Dict[str, Any] = {
    "temperature": 0.9,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 8192,
    "system_instruction": "",
}


# ========== 工具函数：client & 参数构造 ==========
def create_client(explicit_key: str | None = None, project: str | None = None, location: str = "global") -> genai.Client:
    """
    创建 Client。
    策略：优先尝试 Vertex AI (Project ID) -> 失败则降级到 AI Studio (API Key)。
    """
    # 获取环境中的配置
    project_id = project or os.environ.get("GOOGLE_CLOUD_PROJECT")
    api_key = explicit_key or os.environ.get("GOOGLE_CLOUD_API_KEY")

    # === 尝试 1: Vertex AI ===
    if project_id:
        try:
            # print(f"[DEBUG] 尝试连接 Vertex AI (Project: {project_id})...")
            return genai.Client(
                vertexai=True,
                project=project_id,
                location=location
            )
        except Exception as e:
            print(f"[WARN] Vertex AI Client 初始化失败 ({e})，尝试降级到 API Key 模式...")
    
    # === 尝试 2: API Key (AI Studio) ===
    # 跑到这里说明：要么没 Project ID，要么 Vertex 初始化挂了 
    if api_key:
        print("[INFO] 使用 API Key 模式 (AI Studio)")
        return genai.Client(
            vertexai=False,
            api_key=api_key
        )
    
    # === 彻底失败 ===
    raise RuntimeError(
        "❌ 无法创建 Client：既没有有效的 Vertex Project ID，也没有可用的 API Key。\n"
        "请检查根目录下是否存在 'GOOGLE_CLOUD_API_KEY.json' 或 'GOOGLE_CLOUD_API_KEY.txt'。"
    )
    
def ui_aspect_to_vertex(value: str) -> str:
    """
    将 UI 显示的 '1:1 (Square)' 转成 Vertex 接受的 '1:1'
    """
    if not value:
        return "1:1"
    if value.startswith("1:1"):
        return "1:1"
    if value.startswith("3:2"):
        return "3:2"
    if value.startswith("2:3"):
        return "2:3"
    if value.startswith("3:4"):
        return "3:4"
    if value.startswith("4:3"):
        return "4:3"
    if value.startswith("4:5"):
        return "4:5"
    if value.startswith("5:4"):
        return "5:4"
    if value.startswith("16:9"):
        return "16:9"
    if value.startswith("9:16"):
        return "9:16"
    if value.startswith("21:9"):
        return "21:9"
    return "1:1"


def build_generate_config(
    temperature: float,
    top_p: float,
    top_k: int,
    max_output_tokens: int,
    aspect_ratio_ui: str,
    image_size_ui: str,
    want_image: bool,
    want_thinking: bool,
    want_search: bool,
) -> types.GenerateContentConfig:
    """
    构造 GenerateContentConfig。

    - 文本模型：只设置采样参数 + 关掉安全过滤
    - 图像模型：加上 response_modalities + ImageConfig(aspect_ratio, image_size)
    - 思考模型：尝试加上 ThinkingConfig(thinking_level="HIGH")，如果 SDK 不支持会自动忽略
    """
    safety_settings = [
        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
    ]

    cfg_kwargs: Dict[str, Any] = dict(
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        max_output_tokens=max_output_tokens,
        safety_settings=safety_settings,
    )
    # === Google Search / Grounding ===
    if want_search:
        cfg_kwargs["tools"] = [{"google_search": {}}]

    # === 图像模型：参考 Nano-Banana Pro 示例，带上 aspect_ratio + image_size ===
    if want_image:
        aspect_ratio = ui_aspect_to_vertex(aspect_ratio_ui)
        image_size = image_size_ui or "1K"
        
        # --- 新增：人物生成参数 ---
        # "allow_all" = Allow (All ages)
        # "allow_adult" = Allow (Adults only)
        # "dont_allow" = Don't allow
        person_generation = "allow_all" 

        try:
            img_cfg = types.ImageConfig(
                aspect_ratio=aspect_ratio,
                image_size=image_size,
                # person_generation=person_generation, # <--- 加上这一行！
            )
        except Exception as e:
            print(f"[WARN] 当前 ImageConfig 不支持高级参数，退回基础配置：{e}")
            img_cfg = types.ImageConfig(aspect_ratio=aspect_ratio)

        cfg_kwargs["response_modalities"] = ["TEXT", "IMAGE"]
        cfg_kwargs["image_config"] = img_cfg

    # === 思考模型：尝试加上 thinking_config ===
    if want_thinking:
        try:
            # 修改：去掉不支持的 thinking_level 参数，只实例化对象
            # 如果新版 SDK 需要 include_thoughts=True，通常是在 generate_content 的调用里，而不是 Config 里
            # 这里先设为空配置，或者根据你的 SDK 版本查阅文档。
            # 为了防止报错，我们先传入一个空字典或最基础的配置
            thinking_cfg = types.ThinkingConfig(include_thoughts=True) 
            cfg_kwargs["thinking_config"] = thinking_cfg
        except Exception as e:
            print(f"[WARN] ThinkingConfig 配置出错，已忽略：{e}")

    return types.GenerateContentConfig(**cfg_kwargs)


def file_to_image_part(path: str) -> types.Part:
    """
    将本地文件路径转换为 Part，用于图片输入。
    类似 Vertex 示例里的 Part.from_uri，只是我们这里是本地文件。
    """
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        # 默认 png
        mime = "image/png"
    with open(path, "rb") as f:
        data = f.read()
    return types.Part.from_bytes(data=data, mime_type=mime)

def _save_as_jpg_under_1mb(src_path: str, dst_path: str, max_bytes: int = 1024 * 1024) -> None:
    """
    把 src_path 转成 JPG 保存到 dst_path，并尽量保证文件 <= max_bytes（默认 1MB）。
    """
    img = Image.open(src_path)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    else:
        img = img.convert("RGB")

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)

    # 先调质量；不行再缩放
    quality = 92
    width, height = img.size

    while True:
        img.save(dst_path, format="JPEG", quality=quality, optimize=True)
        if os.path.getsize(dst_path) <= max_bytes:
            return

        quality -= 8
        if quality >= 40:
            continue

        # quality 已经很低了，开始缩放
        scale = 0.85
        new_w = max(256, int(width * scale))
        new_h = max(256, int(height * scale))
        if new_w == width and new_h == height:
            # 已经缩不动了，直接保存（可能略超 1MB）
            img.save(dst_path, format="JPEG", quality=40, optimize=True)
            return

        img = img.resize((new_w, new_h))
        width, height = img.size
        quality = 88

def _ensure_export_session_dir(out_dir: str = "exports", base_name: str = "chat_session") -> str:
    os.makedirs(out_dir, exist_ok=True)
    sid = f"{base_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    session_dir = os.path.join(out_dir, sid)
    os.makedirs(os.path.join(session_dir, "images"), exist_ok=True)
    md_path = os.path.join(session_dir, "chat.md")
    if not os.path.exists(md_path):
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# Chat Log\n\n- Session: {sid}\n- Created: {datetime.now().isoformat(timespec='seconds')}\n")
    return session_dir

def _append_md(md_path: str, text: str) -> None:
    with open(md_path, "a", encoding="utf-8") as f:
        f.write(text if text.endswith("\n") else text + "\n")

def log_turn_to_md(
    session_dir: str,
    user_text: str,
    user_image_paths: list[str],
    assistant_text: str,
    assistant_image_paths: list[str],
) -> str:
    """
    追加记录一轮对话到 exports/<session>/chat.md
    图片会被转换成 <=1MB jpg，保存到 images/ 下。
    返回 session_dir（用于 state 保持）。
    """
    if not session_dir:
        session_dir = _ensure_export_session_dir()

    images_dir = os.path.join(session_dir, "images")
    md_path = os.path.join(session_dir, "chat.md")

    def _conv_many(paths: list[str], prefix: str) -> list[str]:
        rels = []
        for p in (paths or []):
            if not p or not os.path.exists(p):
                continue
            # 生成唯一文件名
            name = f"{datetime.now().strftime('%H%M%S')}_{uuid.uuid4().hex[:6]}_{prefix}.jpg"
            dst_abs = os.path.join(images_dir, name)
            _save_as_jpg_under_1mb(p, dst_abs, max_bytes=1024 * 1024)
            rels.append(f"images/{name}")
        return rels

    user_imgs_rel = _conv_many(user_image_paths, "u")
    asst_imgs_rel = _conv_many(assistant_image_paths, "a")

    ts = datetime.now().isoformat(timespec="seconds")
    block = []
    block.append("\n---\n")
    block.append(f"## Turn @ {ts}\n")

    block.append("### User\n")
    if user_text:
        block.append(user_text.strip() + "\n")
    for rel in user_imgs_rel:
        block.append(f"\n![]({rel})\n")

    block.append("\n### Assistant\n")
    if assistant_text:
        block.append(assistant_text.strip() + "\n")
    for rel in asst_imgs_rel:
        block.append(f"\n![]({rel})\n")

    _append_md(md_path, "\n".join(block))
    return session_dir

def export_chat_to_md(
    history: List[dict],
    out_base_name: str = "chat_export",
    out_dir: str = "exports",
) -> str:
    """
    导出当前 Chatbot(history type="messages") 为 Markdown。
    如果内容里引用了图片路径：把它们转为 <=1MB 的 jpg，放到 exports/<name>/images/ 下，并替换 md 引用。
    返回导出的 md 文件路径。
    """
    safe_name = (out_base_name or "chat_export").strip() or "chat_export"
    safe_name = re.sub(r"[^a-zA-Z0-9_\-]+", "_", safe_name)

    export_root = os.path.join(out_dir, safe_name)
    images_dir = os.path.join(export_root, "images")
    os.makedirs(images_dir, exist_ok=True)

    # 匹配 markdown 图片：![alt](path)
    img_pat = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")

    used_map = {}  # src_path -> new_rel_path
    img_counter = 0

    def _convert_one(src: str) -> str:
        nonlocal img_counter
        src_norm = src.strip().strip('"').strip("'")
        src_norm = src_norm.replace("\\", "/")
        if src_norm in used_map:
            return used_map[src_norm]

        if not os.path.exists(src_norm):
            # 找不到就原样返回
            return src

        img_counter += 1
        dst_name = f"{img_counter}.jpg"
        dst_abs = os.path.join(images_dir, dst_name)
        _save_as_jpg_under_1mb(src_norm, dst_abs, max_bytes=1024 * 1024)

        rel = f"images/{dst_name}"
        used_map[src_norm] = rel
        return rel

    lines = []
    lines.append(f"# Chat Export\n\n- Exported: {datetime.now().isoformat(timespec='seconds')}\n")

    for msg in (history or []):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")

        # 替换图片引用为导出目录下的 images/xxx.jpg
        def _repl(m):
            path = m.group(1)
            new_rel = _convert_one(path)
            return m.group(0).replace(path, new_rel)

        content2 = img_pat.sub(_repl, content)

        if role == "user":
            lines.append("\n## User\n")
        elif role == "assistant":
            lines.append("\n## Assistant\n")
        else:
            lines.append(f"\n## {role}\n")

        lines.append(content2.strip() + "\n")

    md_path = os.path.join(export_root, f"{safe_name}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return md_path


# ========== 主业务逻辑：调用 Gemini（Vertex AI） ==========
def call_gemini_vertex(
    api_key: str,
    model_name: str,
    history_messages: List[Dict[str, Any]],
    user_text: str,
    user_images: List[str],
    aspect_ratio: str,
    image_size: str,
    system_instruction: str,
    temperature: float,
    top_p: float,
    top_k: int,
    max_output_tokens: int,
    enable_search: bool,
) -> Tuple[str, List[str]]:  # <--- 修改返回值类型提示
    """
    修改后：返回 (文本内容, 生成的图片路径列表)
    """
    # 1) 创建 client (确保 location="global")
    # 如果你的 create_client 还没改默认值，建议这里强行传 global
    client = create_client(api_key, location="global") 

    # 2) 组装 contents (保持不变)
    contents: List[types.Content] = []
    
    # ... (中间组装 contents 的代码完全保持不变，省略以节省篇幅) ...
    if system_instruction.strip():
        contents.append(types.Content(role="system", parts=[types.Part.from_text(text=system_instruction.strip())]))
    for msg in history_messages:
        # ... (保持原样) ...
        parts = []
        if msg.get("text"): parts.append(types.Part.from_text(text=msg.get("text")))
        for img in msg.get("images", []):
            try: parts.append(file_to_image_part(img))
            except: continue
        if parts: contents.append(types.Content(role="user" if msg.get("role")=="user" else "model", parts=parts))
    
    current_parts = []
    if user_text: current_parts.append(types.Part.from_text(text=user_text))
    for img in user_images:
        try: current_parts.append(file_to_image_part(img))
        except: continue
    if current_parts: contents.append(types.Content(role="user", parts=current_parts))

    # 3) 构造 Config (保持不变)
    # 记得你之前用的字典绕过校验的方法，或者确保 build_generate_config 是最新的
    image_models = {"gemini-2.5-flash-image", "gemini-3-pro-image-preview"}
    want_image = model_name in image_models
    want_thinking = model_name == "gemini-3-pro-preview"

    generate_config = build_generate_config(
        temperature=temperature, top_p=top_p, top_k=top_k, max_output_tokens=max_output_tokens,
        aspect_ratio_ui=aspect_ratio, image_size_ui=image_size,
        want_image=want_image, want_thinking=want_thinking,
        want_search=bool(enable_search),
    )
    
    _debug_print_send(
        model_name=model_name,
        system_instruction=system_instruction,
        user_text=user_text,
        image_files=user_images,
        generate_config=generate_config,
    )

# 4) 调用
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=contents if len(contents) > 1 else (contents[0] if contents else user_text),
            config=generate_config,
        )
    except Exception as e:
        raise RuntimeError(f"调用 Vertex Gemini 失败：{e}")

    # 5) 解析结果 (🛠️ 增强调试版)
    _debug_print_recv(response) # 打印响应

    text_chunks = []
    generated_images = []

    # 先检查有没有 candidates
    if not hasattr(response, "candidates") or not response.candidates:
        # 这种情况通常是 prompt_feedback 直接拦截了
        feedback = getattr(response, "prompt_feedback", "无反馈信息")
        return f"⚠️ 模型未返回任何候选结果 (Blocked)。\n反馈信息: {feedback}", []

    first_candidate = response.candidates[0]
    finish_reason = getattr(first_candidate, "finish_reason", "UNKNOWN")

    # 提取文本
    if getattr(response, "text", None):
        text_chunks.append(response.text)

    # 提取 Parts (文本和图片)
    from pathlib import Path
    import time

    for part in getattr(response, "parts", []) or []:
        if getattr(part, "thought", None): continue
        if getattr(part, "text", None):
            text_chunks.append(part.text)
            continue
        
        # 处理图片
        as_image = getattr(part, "as_image", None)
        if callable(as_image):
            img = as_image()
            if img is not None:
                out_dir = Path("outputs")
                out_dir.mkdir(exist_ok=True)
                filename = f"{model_name}_{int(time.time()*1000)}.png"
                out_path = out_dir / filename
                try:
                    img.save(out_path)
                    generated_images.append(str(out_path))
                except Exception:
                    pass

    final_text = "\n".join(t.strip() for t in text_chunks if t.strip())
    
    # 🛠️ 关键修改：如果什么都没拿到，检查 Finish Reason
    if not final_text and not generated_images:
        # 如果是因为安全原因被拦截
        if "SAFETY" in str(finish_reason):
            return f"🛡️ 内容被安全策略拦截 (Finish Reason: {finish_reason})。\n请尝试修改提示词或图片。", []
        # 如果是其他原因
        elif finish_reason != "STOP":
             return f"⚠️ 模型停止生成，但未返回内容 (Finish Reason: {finish_reason})。\n这通常是因为输入了两张图但没有提供足够的文字指令，或者模型对多图输入感到困惑。", []
        else:
             return "⚠️ API 返回成功 (STOP)，但内容为空。这可能是 Vertex AI 的临时故障或模型输出了空字符串。", []

    # 如果只有图没有字，给个提示
    if not final_text and generated_images:
        final_text = "✅ 图像已生成（见下方）"
    
    return final_text, generated_images

# ========== Gradio 交互逻辑 ==========
def gr_chat_send(
    user_input: str,
    image_files: List[str],
    history: List[dict],
    raw_messages: List[Dict[str, Any]],
    api_key: str, 
    model_name: str,
    aspect_ratio: str, image_size: str, temperature: float, top_p: float, top_k: int, max_output_tokens: int, system_instruction: str,
    enable_search: bool,
    session_dir,
):
    user_input = (user_input or "").strip()
    image_files = image_files or []

    if not user_input and not image_files:
        return history, raw_messages, "", None, session_dir

    # ===== 1. 用户消息上屏 (核心修改) =====
    # 策略：不再构建 {"type": "image"} 字典，而是把图片转为 Markdown 文本
    # 这样完全避开了 Gradio 5.9.1 的 Pydantic 校验 Bug
    
    user_display_content = user_input
    if image_files:
        # 🛠️ 修复点 1：把路径中的反斜杠 \ 替换为 /
        img_markdowns = [f"\n![image]({str(path).replace(os.sep, '/')})" for path in image_files]
        user_display_content += "\n" + "\n".join(img_markdowns)    
    
    # 构建为纯文本消息 (Gradio 会自动渲染 Markdown 中的图片)
    history = history or []
    history.append({
        "role": "user",
        "content": user_display_content 
    })

    # ===== 2. 记录原始消息 (传给 API 用，保持原样) =====
    # 这里依然保留 structured 格式，因为 Gemini API 需要区分 text 和 image
    raw_messages.append({"role": "user", "text": user_input, "images": image_files.copy()})
    
    # ===== 3. 调用 API =====
    try:
        reply_text, generated_images = call_gemini_vertex(
            api_key=api_key, model_name=model_name,
            history_messages=raw_messages[:-1],
            user_text=user_input, user_images=image_files,
            aspect_ratio=aspect_ratio, image_size=image_size,
            system_instruction=system_instruction,
            temperature=float(temperature), top_p=float(top_p), top_k=int(top_k), max_output_tokens=int(max_output_tokens),
            enable_search=bool(enable_search),
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        reply_text = f"❌ 出错：{e}"
        generated_images = []

    # ===== 4. 构建助手消息 (同样使用 Markdown 修复) =====
    
    display_text = f"**[{model_name}]**\n{reply_text}" if reply_text else f"**[{model_name}]**"
    
    if generated_images:
        # 🛠️ 修复点 2：同样替换反斜杠
        gen_img_markdowns = [f"\n![generated]({str(path).replace(os.sep, '/')})" for path in generated_images]
        display_text += "\n" + "\n".join(gen_img_markdowns)
    
    # 助手消息也作为纯文本推入历史
    history.append({
        "role": "assistant",
        "content": display_text,
    })
    
    session_dir_new = log_turn_to_md(
        session_dir,                 # 来自 gr.State
        user_text=user_input,
        user_image_paths=image_files,
        assistant_text=reply_text,
        assistant_image_paths=generated_images or [],
    )
    
    # ===== 5. 记录原始助手消息 =====
    # 原始记录 (无图，因为我们不把生成图作为下一轮输入)
    raw_messages.append({
        "role": "model",
        "text": reply_text,
        "images": [], 
    })

    return history, raw_messages, "", None, session_dir_new

def gr_clear(history, raw_messages):
    return [], []

# ========== 搭建 Gradio UI ==========

def create_gradio_app() -> gr.Blocks:
    # 先从 config.json 读取预设
    presets = load_presets_from_config()
    if presets:
        first_key = next(iter(presets.keys()))
        p0 = presets[first_key]
        default_model = p0.get("model_name", DEFAULT_MODEL_OPTIONS[0])
        default_aspect = p0.get("aspect_ratio", ASPECT_RATIO_OPTIONS[0])
        default_image_size = p0.get("image_size", IMAGE_SIZE_OPTIONS[0])
        default_temp = p0.get("temperature", DEFAULT_ADVANCED_CONFIG["temperature"])
        default_top_p = p0.get("top_p", DEFAULT_ADVANCED_CONFIG["top_p"])
        default_top_k = p0.get("top_k", DEFAULT_ADVANCED_CONFIG["top_k"])
        default_max_tokens = p0.get("max_output_tokens", DEFAULT_ADVANCED_CONFIG["max_output_tokens"])
        default_sys_inst = p0.get("system_instruction", DEFAULT_ADVANCED_CONFIG["system_instruction"])
    else:
        first_key = None
        default_model = DEFAULT_MODEL_OPTIONS[0]
        default_aspect = ASPECT_RATIO_OPTIONS[0]
        default_image_size = IMAGE_SIZE_OPTIONS[0]
        default_temp = DEFAULT_ADVANCED_CONFIG["temperature"]
        default_top_p = DEFAULT_ADVANCED_CONFIG["top_p"]
        default_top_k = DEFAULT_ADVANCED_CONFIG["top_k"]
        default_max_tokens = DEFAULT_ADVANCED_CONFIG["max_output_tokens"]
        default_sys_inst = DEFAULT_ADVANCED_CONFIG["system_instruction"]

    with gr.Blocks(title="Banana Studio (Vertex AI / google.genai)") as demo:
        gr.Markdown(
            "# 🍌 Banana Studio - Vertex AI 版\n"
            "使用 `google.genai` 调用 Gemini（Vertex AI 端点），安全过滤全部关闭（OFF，仅用于测试）。"
        )
        # 1. 创建顶级 Tabs 容器
        with gr.Tabs():
            
            # === Tab 1: 主对话界面 (原来的界面) ===
            with gr.Tab("🍌 Banana Studio"):
                raw_messages_state = gr.State([])  # 保存原始结构 [{'role', 'text', 'images'}, ...]
                export_session_dir = gr.State(value="")

                with gr.Row():
                    # ===== 左侧：参数区 =====
                    with gr.Column(scale=1, min_width=320):
                        gr.Markdown("### ⚙️ 设置面板")

                        api_key = gr.Textbox(
                            label="GOOGLE_CLOUD_API_KEY（留空则使用环境变量）",
                            value=os.environ.get("GOOGLE_CLOUD_API_KEY", ""),
                            type="password",
                        )

                        model_name = gr.Dropdown(
                            label="模型",
                            choices=DEFAULT_MODEL_OPTIONS,
                            value=default_model,
                        )
                        
                        enable_search = gr.Checkbox(
                            label="启用 Google Search（Grounding / 联网检索）",
                            value=False,
                        )

                        aspect_ratio = gr.Dropdown(
                            label="图像宽高比（用于 image_config，仅当前示例中传给配置）",
                            choices=ASPECT_RATIO_OPTIONS,
                            value=default_aspect,
                        )

                        image_size = gr.Dropdown(
                            label="图像尺寸（image_size，例如 1K / 512 / 2K）",
                            choices=IMAGE_SIZE_OPTIONS,
                            value=default_image_size,
                        )

                        gr.Markdown("#### 高级参数")

                        temperature = gr.Slider(
                            label="temperature",
                            minimum=0.0,
                            maximum=2.0,
                            value=default_temp,
                            step=0.05,
                        )
                        top_p = gr.Slider(
                            label="top_p",
                            minimum=0.0,
                            maximum=1.0,
                            value=default_top_p,
                            step=0.01,
                        )
                        top_k = gr.Slider(
                            label="top_k",
                            minimum=1,
                            maximum=100,
                            value=default_top_k,
                            step=1,
                        )
                        max_output_tokens = gr.Slider(
                            label="max_output_tokens",
                            minimum=256,
                            maximum=32768,
                            value=default_max_tokens,
                            step=256,
                        )

                        system_instruction = gr.Textbox(
                            label="System Instruction（系统提示词）",
                            lines=4,
                            value=default_sys_inst,
                            placeholder="在这里写对模型的总指导，比如：你是一个善于写代码和查 bug 的助手……",
                        )

                        gr.Markdown("#### 参数预设配置")

                        # 状态：所有预设
                        presets_state = gr.State(presets)

                        preset_name_input = gr.Textbox(
                            label="预设名称",
                            placeholder="例如：默认 / 翻译-保守 / 创作-大胆",
                            value=first_key or "",
                        )

                        preset_dropdown = gr.Dropdown(
                            label="已保存预设",
                            choices=list(presets.keys()),
                            value=first_key,
                        )

                        with gr.Row():
                            btn_save_preset = gr.Button("💾 保存当前为预设")
                            btn_load_preset = gr.Button("📥 加载预设")
                            btn_delete_preset = gr.Button("🗑 删除预设")

                        # --- 预设按钮绑定 ---
                        btn_save_preset.click(
                            fn=save_preset,
                            inputs=[
                                preset_name_input,
                                presets_state,
                                model_name,
                                aspect_ratio,
                                image_size,
                                temperature,
                                top_p,
                                top_k,
                                max_output_tokens,
                                system_instruction,
                            ],
                            outputs=[
                                presets_state,
                                preset_dropdown,
                            ],
                        )

                        btn_load_preset.click(
                            fn=load_preset,
                            inputs=[
                                preset_dropdown,
                                presets_state,
                            ],
                            outputs=[
                                model_name,
                                aspect_ratio,
                                image_size,
                                temperature,
                                top_p,
                                top_k,
                                max_output_tokens,
                                system_instruction,
                            ],
                        )

                        btn_delete_preset.click(
                            fn=delete_preset,
                            inputs=[
                                preset_dropdown,
                                presets_state,
                            ],
                            outputs=[
                                presets_state,
                                preset_dropdown,
                            ],
                        )

                        gr.Markdown(
                            "> 🔐 当前示例中，所有 SafetySetting 的 threshold 均为 `OFF`，"
                            "仅建议在本地/开发环境中使用。"
                        )

                    # ===== 右侧：对话区 =====
                    with gr.Column(scale=2):
                        gr.Markdown("### 💬 对话区")

                        chatbot = gr.Chatbot(
                            label="Chat",
                            height=520,
                            type="messages",  
                        )

                        with gr.Row():
                            user_input = gr.Textbox(
                                label="输入消息",
                                placeholder="在这里输入问题或描述…",
                                scale=4,
                            )
                        image_upload = gr.Files(
                            label="上传图片（多张图将作为当前轮多模态输入）",
                            file_types=["image"],
                            file_count="multiple",
                        )

                        with gr.Row():
                            send_btn = gr.Button("发送", variant="primary")
                            clear_btn = gr.Button("清空对话")

                        # 绑定发送事件
                        send_btn.click(
                            fn=gr_chat_send,
                            inputs=[
                                user_input,
                                image_upload,
                                chatbot,
                                raw_messages_state,
                                api_key,
                                model_name,
                                aspect_ratio,
                                image_size,
                                temperature,
                                top_p,
                                top_k,
                                max_output_tokens,
                                system_instruction,
                                enable_search,
                                export_session_dir,
                            ],
                            outputs=[
                                chatbot,
                                raw_messages_state,
                                user_input,
                                image_upload,
                                export_session_dir,
                            ],
                        )

                        clear_btn.click(
                            fn=gr_clear,
                            inputs=[chatbot, raw_messages_state],
                            outputs=[chatbot, raw_messages_state],
                        )
            
            # === Tab 2+: 动态加载插件 ===
            # 直接在这里调用加载函数，它会在当前的 gr.Tabs() 上下文中自动渲染 Tab
            load_plugins_from_dir("plugins")

        return demo


if __name__ == "__main__":
    # ① 加载 Key
    load_google_api_key_from_file()

    # ② 创建 UI
    demo = create_gradio_app()
    
    # 查找端口
    port = find_free_port(7860, 7880, host="127.0.0.1")

    # ③ 启动 (🛠️ 修复点：添加 allowed_paths)
    # 允许 Gradio 读取当前目录下的 outputs 文件夹和根目录文件
    demo.launch(
        server_name="127.0.0.1", 
        server_port=port,
        allowed_paths=[".", "outputs"] 
    )
    print(f"[banana] Gradio running on http://127.0.0.1:{port}")

