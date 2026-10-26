from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

import gradio as gr

from .config import (
    ASPECT_RATIO_OPTIONS,
    DEFAULT_ADVANCED_CONFIG,
    DEFAULT_MODEL_OPTIONS,
    IMAGE_SIZE_OPTIONS,
    MODEL_CHOICES,
    NANO_BANANA_2_LITE_MODEL,
    load_presets_from_config,
    save_presets_to_config,
)
from .export import log_turn_to_md
from .generation import GenerationService
from .openai_images import OPENAI_ASPECT_RATIOS, is_openai_image_model, openai_image_size
from .params import GenerationParams, aspect_key, format_params_preview, load_last_params
from .png_metadata import read_png_parameters
from .queue_service import QueueService


def save_preset(
    preset_name: str,
    presets: dict[str, Any],
    model_name: str,
    aspect_ratio: str,
    image_size: str,
    temperature: float,
    top_p: float,
    top_k: int,
    max_output_tokens: int,
    system_instruction: str,
    enable_search: bool,
    save_png_parameters: bool,
):
    name = (preset_name or "").strip() or "default"
    presets = dict(presets or {})
    presets[name] = GenerationParams(
        model_name=model_name,
        aspect_ratio=aspect_ratio,
        image_size=image_size,
        temperature=float(temperature),
        top_p=float(top_p),
        top_k=int(top_k),
        max_output_tokens=int(max_output_tokens),
        system_instruction=system_instruction,
        enable_search=enable_search,
        save_png_parameters=save_png_parameters,
    ).public_dict()
    save_presets_to_config(presets)
    return presets, gr.update(choices=list(presets.keys()), value=name)


def load_preset(selected_name: str, presets: dict[str, Any]):
    if not selected_name or selected_name not in (presets or {}):
        upd = gr.update()
        return upd, upd, upd, upd, upd, upd, upd, upd, upd, upd
    params = GenerationParams.from_dict(presets[selected_name])
    return (
        params.model_name,
        params.enable_search,
        params.aspect_ratio,
        params.image_size,
        params.temperature,
        params.top_p,
        params.top_k,
        params.max_output_tokens,
        params.system_instruction,
        params.save_png_parameters,
    )


def delete_preset(selected_name: str, presets: dict[str, Any]):
    presets = dict(presets or {})
    if selected_name in presets:
        del presets[selected_name]
        save_presets_to_config(presets)
    choices = list(presets.keys())
    return presets, gr.update(choices=choices, value=choices[0] if choices else None)


def make_params(
    prompt: str,
    model_name: str,
    aspect_ratio: str,
    image_size: str,
    temperature: float,
    top_p: float,
    top_k: int,
    max_output_tokens: int,
    system_instruction: str,
    enable_search: bool,
    save_png_parameters: bool,
) -> GenerationParams:
    return GenerationParams(
        prompt=prompt or "",
        model_name=model_name,
        aspect_ratio=aspect_ratio,
        image_size=image_size,
        temperature=float(temperature),
        top_p=float(top_p),
        top_k=int(top_k),
        max_output_tokens=int(max_output_tokens),
        system_instruction=system_instruction or "",
        enable_search=bool(enable_search),
        save_png_parameters=bool(save_png_parameters),
    ).normalize()


def params_to_outputs(params: GenerationParams):
    return (
        params.prompt,
        params.model_name,
        params.enable_search,
        params.aspect_ratio,
        params.image_size,
        params.temperature,
        params.top_p,
        params.top_k,
        params.max_output_tokens,
        params.system_instruction,
        params.save_png_parameters,
    )


def load_last_params_for_ui():
    try:
        params = load_last_params()
        images = [
            path
            for path in normalize_file_list((params.extra or {}).get("user_images", []))
            if os.path.exists(path)
        ]
        return (*params_to_outputs(params), gr.update(value=[]), images, format_selected_images(images))
    except Exception as exc:
        gr.Warning(f"读取上次参数失败: {exc}")
        upd = gr.update()
        return upd, upd, upd, upd, upd, upd, upd, upd, upd, upd, upd, upd, [], format_selected_images([])


def normalize_file_list(files: Any) -> list[str]:
    if not files:
        return []
    if not isinstance(files, list):
        files = [files]
    paths: list[str] = []
    for item in files:
        path = getattr(item, "name", item)
        if path:
            paths.append(str(path))
    return paths


def format_selected_images(paths: list[str]) -> str:
    if not paths:
        return "尚未选择图片。"
    return "\n".join(f"{idx + 1}. {path}" for idx, path in enumerate(paths))


def merge_uploaded_files(current_files, existing_files):
    existing = normalize_file_list(existing_files)
    current = normalize_file_list(current_files)
    if not current:
        return gr.update(value=[]), existing, format_selected_images(existing)
    merged: list[str] = []
    for path in existing + current:
        if path not in merged:
            merged.append(path)
    return gr.update(value=[]), merged, format_selected_images(merged)


def clear_uploaded_files():
    return gr.update(value=[]), [], format_selected_images([])


def gr_chat_send(
    user_input: str,
    image_files: list[str],
    history: list[dict],
    raw_messages: list[dict[str, Any]],
    api_key: str,
    model_name: str,
    aspect_ratio: str,
    image_size: str,
    temperature: float,
    top_p: float,
    top_k: int,
    max_output_tokens: int,
    system_instruction: str,
    enable_search: bool,
    save_png_parameters: bool,
    session_dir: str,
    generation_service: GenerationService,
    openai_api_key: str = "",
):
    image_files = normalize_file_list(image_files)
    params = make_params(
        user_input,
        model_name,
        aspect_ratio,
        image_size,
        temperature,
        top_p,
        top_k,
        max_output_tokens,
        system_instruction,
        enable_search,
        save_png_parameters,
    )
    if not params.prompt and not image_files:
        return history, raw_messages, "", gr.update(value=[]), [], format_selected_images([]), session_dir
    params.extra["user_images"] = image_files.copy()

    history = history or []
    raw_messages = raw_messages or []
    user_display = params.prompt
    if image_files:
        user_display += "\n" + "\n".join(f"\n![image]({path.replace(os.sep, '/')})" for path in image_files)
    history.append({"role": "user", "content": user_display})
    raw_messages.append({"role": "user", "text": params.prompt, "images": image_files.copy()})
    try:
        reply_text, generated_images = generation_service.generate(
            api_key=api_key,
            params=params,
            history_messages=raw_messages[:-1],
            user_images=image_files,
            openai_api_key=openai_api_key,
        )
    except Exception as exc:
        import traceback

        traceback.print_exc()
        reply_text = f"错误: {exc}"
        generated_images = []

    display_text = f"**[{params.model_name}]**\n{reply_text}" if reply_text else f"**[{params.model_name}]**"
    if generated_images:
        display_text += "\n" + "\n".join(f"\n![generated]({path.replace(os.sep, '/')})" for path in generated_images)
    history.append({"role": "assistant", "content": display_text})
    session_dir = log_turn_to_md(
        session_dir,
        user_text=params.prompt,
        user_image_paths=image_files,
        assistant_text=reply_text,
        assistant_image_paths=generated_images,
        params=params,
    )
    raw_messages.append({"role": "model", "text": reply_text, "images": generated_images.copy() if is_openai_image_model(params.model_name) else []})
    return history, raw_messages, "", gr.update(value=[]), [], format_selected_images([]), session_dir


def gr_clear():
    return [], []


def read_png_for_ui(png_file):
    paths = normalize_file_list(png_file)
    if not paths:
        return "请先上传 PNG 文件。", "", None
    try:
        params, raw = read_png_parameters(paths[0])
        return format_params_preview(params, raw), raw, params.public_dict()
    except Exception as exc:
        return f"读取 PNG 参数失败: {exc}", "", None


def send_png_params_to_main(parsed):
    if not parsed:
        gr.Warning("没有可发送的 PNG 参数。")
        upd = gr.update()
        return upd, upd, upd, upd, upd, upd, upd, upd, upd, upd, upd
    return params_to_outputs(GenerationParams.from_dict(parsed))


def send_png_params_to_queue(parsed):
    if not parsed:
        gr.Warning("没有可发送到智能队列的 PNG 参数。")
        upd = gr.update()
        return upd, upd, upd, upd, upd, upd, upd, upd, upd, upd, upd
    params = GenerationParams.from_dict(parsed)
    return (
        params.prompt,
        params.model_name,
        params.aspect_ratio,
        params.image_size,
        "1" if params.enable_search else "0",
        str(params.temperature),
        str(params.top_p),
        str(params.top_k),
        str(params.max_output_tokens),
        params.system_instruction,
        params.save_png_parameters,
    )


def queue_refresh(queue_service: QueueService, selected_id: str | None = None):
    choices = queue_service.group_choices()
    if selected_id is None:
        return (
            queue_service.rows(),
            gr.update(choices=choices),
            queue_service.log_text(),
            queue_service.gallery_paths(),
        )
    selected_id = (selected_id or "").strip()
    value = selected_id if selected_id in choices else (choices[0] if choices else None)
    return (
        queue_service.rows(),
        gr.update(choices=choices, value=value),
        queue_service.log_text(),
        queue_service.gallery_paths(),
    )


def queue_submit(
    prompt,
    ref_images,
    batch_count,
    strategy,
    model_name,
    ar_arr,
    size_arr,
    search_arr,
    temp_arr,
    top_p_arr,
    top_k_arr,
    token_arr,
    api_key,
    sys_inst,
    save_png_parameters,
    queue_service: QueueService,
    openai_api_key: str = "",
):
    def first_text(value, default):
        if value is None or str(value).strip() == "":
            return default
        return str(value).split(",")[0].strip()

    def first_float(value, default):
        try:
            return float(first_text(value, default))
        except Exception:
            return float(default)

    def first_int(value, default):
        try:
            return int(float(first_text(value, default)))
        except Exception:
            return int(default)

    base_params = GenerationParams(
        prompt=prompt or "",
        model_name=model_name,
        aspect_ratio=first_text(ar_arr, ASPECT_RATIO_OPTIONS[0]),
        image_size=first_text(size_arr, IMAGE_SIZE_OPTIONS[0]),
        temperature=first_float(temp_arr, DEFAULT_ADVANCED_CONFIG["temperature"]),
        top_p=first_float(top_p_arr, DEFAULT_ADVANCED_CONFIG["top_p"]),
        top_k=first_int(top_k_arr, DEFAULT_ADVANCED_CONFIG["top_k"]),
        max_output_tokens=first_int(token_arr, DEFAULT_ADVANCED_CONFIG["max_output_tokens"]),
        system_instruction=sys_inst or "",
        enable_search=first_text(search_arr, "0").lower() in {"1", "true", "yes", "on"},
        save_png_parameters=bool(save_png_parameters),
    ).normalize()
    queue_service.submit_group(
        prompt=prompt or "",
        ref_images=normalize_file_list(ref_images),
        batch_count=int(batch_count or 1),
        strategy=strategy,
        base_params=base_params,
        param_arrays={
            "aspect_ratio": ar_arr,
            "image_size": size_arr,
            "enable_search": search_arr,
            "temperature": temp_arr,
            "top_p": top_p_arr,
            "top_k": top_k_arr,
            "max_output_tokens": token_arr,
        },
        api_key=api_key or "",
        openai_api_key=openai_api_key,
    )
    choices = queue_service.group_choices()
    return queue_refresh(queue_service, choices[-1] if choices else None)


def queue_move(selected_id: str, direction: int, queue_service: QueueService):
    if selected_id:
        queue_service.move_group(selected_id.strip(), direction)
    return queue_refresh(queue_service, selected_id)


def queue_delete(selected_id: str, queue_service: QueueService):
    if selected_id:
        queue_service.delete_group(selected_id.strip())
    return queue_refresh(queue_service)


def queue_action(action: str, selected_id: str, queue_service: QueueService):
    selected_id = (selected_id or "").strip() or None
    if action == "skip_item":
        queue_service.skip_item(selected_id)
    elif action == "skip_group":
        queue_service.skip_group(selected_id)
    elif action == "abort":
        queue_service.abort()
    elif action == "resume":
        queue_service.resume()
    return queue_refresh(queue_service, selected_id)


def queue_resume(selected_id: str, concurrency: int, queue_service: QueueService):
    queue_service.set_concurrency(int(concurrency or 1))
    return queue_action("resume", selected_id, queue_service)


def select_queue_row(table, evt: gr.SelectData):
    try:
        row_index = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
        row = table.iloc[row_index].tolist() if hasattr(table, "iloc") else table[row_index]
        return str(row[0])
    except Exception:
        pass
    if isinstance(evt.value, list) and evt.value:
        return str(evt.value[0])
    return gr.update()


def load_optional_plugins(plugin_dir: str = "plugins") -> None:
    path = Path(plugin_dir).resolve()
    if not path.exists():
        return
    for file_path in path.glob("*.py"):
        if file_path.name.startswith("__") or file_path.name == "queue_manager.py":
            continue
        try:
            spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
            if not spec or not spec.loader:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[file_path.stem] = module
            spec.loader.exec_module(module)
            if hasattr(module, "create_tab") and callable(module.create_tab):
                module.create_tab()
        except Exception as exc:
            print(f"[WARN] Failed to load optional plugin {file_path.name}: {exc}")


def model_controls_for_ui(model_name: str, aspect_ratio: str, image_size: str):
    openai = is_openai_image_model(model_name)
    choices = ASPECT_RATIO_OPTIONS
    if openai:
        supported = [option for option in choices if aspect_key(option) in OPENAI_ASPECT_RATIOS]
        if aspect_key(aspect_ratio) not in OPENAI_ASPECT_RATIOS:
            aspect_ratio = supported[0]
        # Existing Gemini pixel labels do not describe the OpenAI output sizes.
        choices = [(" ".join(option.split()[:-1]), option) for option in supported]
        size = openai_image_size(aspect_ratio, image_size)
        note = f"GPT Image：请求尺寸 **{size}**，质量由模型自动选择。System Instruction 合并到提示词；采样参数和 Google Search 不适用。"
        if image_size == "4K":
            note += " 4K 按最大边 3840 和总像素上限换算，超出 2560×1440 的尺寸为实验支持。"
    elif model_name == NANO_BANANA_2_LITE_MODEL:
        note = "Nano Banana 2 Lite：仅支持 1K，最多 4096 输出 tokens，不支持 Google Search；主页面和队列会自动使用这些限制。"
    else:
        note = "Gemini 使用 Google 认证及下方的生成参数。"
    search_update = gr.update(interactive=not openai and model_name != NANO_BANANA_2_LITE_MODEL)
    token_update = gr.update(interactive=not openai, maximum=32768)
    if model_name == NANO_BANANA_2_LITE_MODEL:
        search_update.update(value=False)
        token_update.update(value=4096, maximum=4096)
    return (
        gr.update(choices=choices, value=aspect_ratio), search_update,
        *(gr.update(interactive=not openai) for _ in range(3)), token_update, note,
    )


def model_image_size_for_ui(model_name: str, image_size: str):
    if model_name == NANO_BANANA_2_LITE_MODEL:
        return gr.update(choices=["1K"], value="1K")
    return gr.update(choices=IMAGE_SIZE_OPTIONS, value=image_size)


def queue_model_controls_for_ui(model_name: str):
    if model_name == NANO_BANANA_2_LITE_MODEL:
        return (
            gr.update(value="1K", interactive=False),
            gr.update(value="0", interactive=False),
            gr.update(value="4096", interactive=False),
        )
    openai = is_openai_image_model(model_name)
    return gr.update(interactive=True), gr.update(interactive=not openai), gr.update(interactive=not openai)


def create_gradio_app() -> gr.Blocks:
    presets = load_presets_from_config()
    first_key = next(iter(presets.keys()), None)
    initial = GenerationParams.from_dict(presets.get(first_key, {})) if first_key else GenerationParams()
    generation_service = GenerationService(max_concurrency=1)
    queue_service = QueueService(generation_service)

    with gr.Blocks(title="Banana Studio") as demo:
        gr.Markdown("# Banana Studio")
        openai_api_key = gr.Textbox(
            label="OpenAI API Key（主页面 / 智能队列共用）",
            type="password",
            placeholder="sk-...；留空使用 OPENAI_API_KEY 环境变量或 OPENAI_API_KEY.txt",
            info="仅用于 GPT Image 模型；页面填写的密钥不保存到预设、PNG 或生成记录。",
        )
        with gr.Tabs():
            with gr.Tab("主页面"):
                raw_messages_state = gr.State([])
                export_session_dir = gr.State("")
                image_files_state = gr.State([])
                with gr.Row():
                    with gr.Column(scale=1, min_width=320):
                        gr.Markdown("### 设置")
                        api_key = gr.Textbox(
                            label="GOOGLE_CLOUD_API_KEY（留空则使用环境变量）",
                            value=os.environ.get("GOOGLE_CLOUD_API_KEY", ""),
                            type="password",
                        )
                        model_name = gr.Dropdown(label="模型", choices=MODEL_CHOICES, value=initial.model_name)
                        enable_search = gr.Checkbox(label="启用 Google Search", value=initial.enable_search)
                        save_png_parameters = gr.Checkbox(label="保存生成参数到 PNG", value=True)
                        aspect_ratio = gr.Dropdown(label="图片宽高比", choices=ASPECT_RATIO_OPTIONS, value=initial.aspect_ratio)
                        image_size = gr.Dropdown(label="图片尺寸", choices=IMAGE_SIZE_OPTIONS, value=initial.image_size)
                        model_info = gr.Markdown()
                        temperature = gr.Slider(label="temperature", minimum=0.0, maximum=2.0, value=initial.temperature, step=0.05)
                        top_p = gr.Slider(label="top_p", minimum=0.0, maximum=1.0, value=initial.top_p, step=0.01)
                        top_k = gr.Slider(label="top_k", minimum=1, maximum=100, value=initial.top_k, step=1)
                        max_output_tokens = gr.Slider(
                            label="max_output_tokens",
                            minimum=256,
                            maximum=32768,
                            value=initial.max_output_tokens,
                            step=256,
                        )
                        system_instruction = gr.Textbox(label="System Instruction（系统指令）", lines=4, value=initial.system_instruction)
                        btn_load_last = gr.Button("读取上次参数")

                        gr.Markdown("### 参数预设")
                        presets_state = gr.State(presets)
                        preset_name_input = gr.Textbox(label="预设名称", value=first_key or "")
                        preset_dropdown = gr.Dropdown(label="已保存预设", choices=list(presets.keys()), value=first_key)
                        with gr.Row():
                            btn_save_preset = gr.Button("保存")
                            btn_load_preset = gr.Button("加载")
                            btn_delete_preset = gr.Button("删除")

                    with gr.Column(scale=2):
                        gr.Markdown("### 对话")
                        chatbot = gr.Chatbot(label="对话记录", height=520, type="messages")
                        user_input = gr.Textbox(label="Prompt / 消息", lines=4)
                        image_upload = gr.Files(label="拖拽图片到这里（可多次追加）", file_types=["image"], file_count="multiple", type="filepath")
                        selected_images = gr.Textbox(label="已选择图片", value=format_selected_images([]), lines=5, interactive=False)
                        with gr.Row():
                            send_btn = gr.Button("发送", variant="primary")
                            clear_images_btn = gr.Button("清空图片")
                            clear_btn = gr.Button("清空对话")

                main_param_outputs = [
                    user_input,
                    model_name,
                    enable_search,
                    aspect_ratio,
                    image_size,
                    temperature,
                    top_p,
                    top_k,
                    max_output_tokens,
                    system_instruction,
                    save_png_parameters,
                ]

                btn_load_last.click(
                    fn=load_last_params_for_ui,
                    outputs=[*main_param_outputs, image_upload, image_files_state, selected_images],
                )
                image_upload.change(fn=merge_uploaded_files, inputs=[image_upload, image_files_state], outputs=[image_upload, image_files_state, selected_images])
                clear_images_btn.click(fn=clear_uploaded_files, outputs=[image_upload, image_files_state, selected_images])
                send_btn.click(
                    fn=lambda key, *args: gr_chat_send(*args, generation_service=generation_service, openai_api_key=key),
                    inputs=[
                        openai_api_key,
                        user_input,
                        image_files_state,
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
                        save_png_parameters,
                        export_session_dir,
                    ],
                    outputs=[chatbot, raw_messages_state, user_input, image_upload, image_files_state, selected_images, export_session_dir],
                )
                clear_btn.click(fn=gr_clear, outputs=[chatbot, raw_messages_state])

                model_controls = [aspect_ratio, enable_search, temperature, top_p, top_k, max_output_tokens, model_info]
                model_name.change(fn=model_controls_for_ui, inputs=[model_name, aspect_ratio, image_size], outputs=model_controls)
                model_name.change(fn=model_image_size_for_ui, inputs=[model_name, image_size], outputs=image_size)
                image_size.change(fn=model_controls_for_ui, inputs=[model_name, aspect_ratio, image_size], outputs=model_controls)
                aspect_ratio.change(
                    fn=lambda *args: model_controls_for_ui(*args)[-1],
                    inputs=[model_name, aspect_ratio, image_size], outputs=model_info,
                )
                demo.load(fn=model_controls_for_ui, inputs=[model_name, aspect_ratio, image_size], outputs=model_controls)
                demo.load(fn=model_image_size_for_ui, inputs=[model_name, image_size], outputs=image_size)

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
                        enable_search,
                        save_png_parameters,
                    ],
                    outputs=[presets_state, preset_dropdown],
                )
                btn_load_preset.click(
                    fn=load_preset,
                    inputs=[preset_dropdown, presets_state],
                    outputs=[
                        model_name,
                        enable_search,
                        aspect_ratio,
                        image_size,
                        temperature,
                        top_p,
                        top_k,
                        max_output_tokens,
                        system_instruction,
                        save_png_parameters,
                    ],
                )
                btn_delete_preset.click(fn=delete_preset, inputs=[preset_dropdown, presets_state], outputs=[presets_state, preset_dropdown])

            with gr.Tab("PNG 参数读取"):
                parsed_png_state = gr.State(None)
                png_file = gr.File(label="PNG 文件", file_types=[".png"], type="filepath")
                png_preview = gr.Textbox(label="解析后的参数", lines=14)
                png_raw = gr.Textbox(label="原始参数文本", lines=10)
                with gr.Row():
                    read_png_btn = gr.Button("读取 PNG")
                    send_png_btn = gr.Button("发送到主页面", variant="primary")
                    send_png_queue_btn = gr.Button("发送到智能队列")
                read_png_btn.click(fn=read_png_for_ui, inputs=png_file, outputs=[png_preview, png_raw, parsed_png_state])
                png_file.change(fn=read_png_for_ui, inputs=png_file, outputs=[png_preview, png_raw, parsed_png_state])
                send_png_btn.click(fn=send_png_params_to_main, inputs=parsed_png_state, outputs=main_param_outputs)

            with gr.Tab("智能队列"):
                gr.Markdown("### 队列")
                queue_image_files_state = gr.State([])
                with gr.Row():
                    with gr.Column(scale=4):
                        queue_prompt = gr.Textbox(label="Prompt", lines=4)
                        queue_images = gr.File(label="拖拽参考图片到这里（可多次追加）", file_count="multiple", type="filepath", file_types=["image"])
                        queue_selected_images = gr.Textbox(label="已选择参考图片", value=format_selected_images([]), lines=5, interactive=False)
                        queue_clear_images_btn = gr.Button("清空参考图")
                        with gr.Row():
                            queue_batch = gr.Slider(label="执行次数", minimum=1, maximum=32, value=4, step=1)
                            queue_strategy = gr.Radio(
                                label="差异化策略",
                                choices=["随机种子扰动", "风格轮换", "仅参数变化"],
                                value="随机种子扰动",
                            )
                            queue_concurrency = gr.Slider(label="并发数", minimum=1, maximum=8, value=1, step=1)
                        with gr.Accordion("参数数组", open=True):
                            queue_model = gr.Dropdown(label="模型", choices=MODEL_CHOICES, value=DEFAULT_MODEL_OPTIONS[3])
                            queue_ar = gr.Textbox(label="宽高比", value="16:9")
                            queue_size = gr.Textbox(label="图片尺寸", value="4K")
                            queue_search = gr.Textbox(label="搜索 (0/1)", value="0")
                            queue_temp = gr.Textbox(label="Temperature", value="0.9")
                            queue_top_p = gr.Textbox(label="Top P", value="0.95")
                            queue_top_k = gr.Textbox(label="Top K", value="40")
                            queue_tokens = gr.Textbox(label="Max output tokens", value="8192")
                            queue_sys = gr.Textbox(label="System Instruction（系统指令）", lines=2)
                            queue_save_png = gr.Checkbox(label="保存生成参数到 PNG", value=True)
                        queue_api_key = gr.Textbox(label="Google API Key（可选）", type="password")
                        gr.Markdown("GPT Image 使用页面顶部的 **OpenAI API Key**。宽高比支持 1:3 至 3:1；尺寸为 1K / 2K / 4K。Google Search 和采样参数仅用于 Gemini。")
                        gr.Markdown("Nano Banana 2 / 2.1 支持 1K、2K、4K；2 Lite 仅支持 1K，最多 4096 输出 tokens，不支持搜索。")
                        queue_submit_btn = gr.Button("加入任务组")
                    with gr.Column(scale=5):
                        selected_group_id = gr.Dropdown(label="选择任务组", choices=[], value=None)
                        queue_table = gr.Dataframe(
                            label="队列列表",
                            headers=["ID", "状态", "进度", "结果数", "Prompt", "错误"],
                            datatype=["str", "str", "str", "number", "str", "str"],
                            interactive=False,
                        )
                        with gr.Row():
                            move_up_btn = gr.Button("↑ 上移")
                            move_down_btn = gr.Button("↓ 下移")
                            delete_btn = gr.Button("X 取消/删除", variant="stop")
                        with gr.Row():
                            skip_item_btn = gr.Button("跳过单项")
                            skip_group_btn = gr.Button("跳过组")
                            abort_btn = gr.Button("中止", variant="stop")
                            resume_btn = gr.Button("继续 / 启动队列", variant="primary")
                        queue_log = gr.Textbox(label="队列日志", lines=10)
                        queue_gallery = gr.Gallery(label="队列结果", columns=3, height=520, object_fit="contain")

                queue_outputs = [queue_table, selected_group_id, queue_log, queue_gallery]
                queue_model.change(fn=queue_model_controls_for_ui, inputs=queue_model, outputs=[queue_size, queue_search, queue_tokens])
                queue_images.change(
                    fn=merge_uploaded_files,
                    inputs=[queue_images, queue_image_files_state],
                    outputs=[queue_images, queue_image_files_state, queue_selected_images],
                )
                queue_clear_images_btn.click(
                    fn=clear_uploaded_files,
                    outputs=[queue_images, queue_image_files_state, queue_selected_images],
                )
                queue_submit_btn.click(
                    fn=lambda key, *args: queue_submit(*args, queue_service=queue_service, openai_api_key=key),
                    inputs=[
                        openai_api_key,
                        queue_prompt,
                        queue_image_files_state,
                        queue_batch,
                        queue_strategy,
                        queue_model,
                        queue_ar,
                        queue_size,
                        queue_search,
                        queue_temp,
                        queue_top_p,
                        queue_top_k,
                        queue_tokens,
                        queue_api_key,
                        queue_sys,
                        queue_save_png,
                    ],
                    outputs=queue_outputs,
                )
                send_png_queue_btn.click(
                    fn=send_png_params_to_queue,
                    inputs=parsed_png_state,
                    outputs=[
                        queue_prompt,
                        queue_model,
                        queue_ar,
                        queue_size,
                        queue_search,
                        queue_temp,
                        queue_top_p,
                        queue_top_k,
                        queue_tokens,
                        queue_sys,
                        queue_save_png,
                    ],
                )
                move_up_btn.click(fn=lambda group_id: queue_move(group_id, -1, queue_service), inputs=selected_group_id, outputs=queue_outputs)
                move_down_btn.click(fn=lambda group_id: queue_move(group_id, 1, queue_service), inputs=selected_group_id, outputs=queue_outputs)
                delete_btn.click(fn=lambda group_id: queue_delete(group_id, queue_service), inputs=selected_group_id, outputs=queue_outputs)
                skip_item_btn.click(fn=lambda group_id: queue_action("skip_item", group_id, queue_service), inputs=selected_group_id, outputs=queue_outputs)
                skip_group_btn.click(fn=lambda group_id: queue_action("skip_group", group_id, queue_service), inputs=selected_group_id, outputs=queue_outputs)
                abort_btn.click(fn=lambda group_id: queue_action("abort", group_id, queue_service), inputs=selected_group_id, outputs=queue_outputs)
                resume_btn.click(
                    fn=lambda group_id, concurrency: queue_resume(group_id, concurrency, queue_service),
                    inputs=[selected_group_id, queue_concurrency],
                    outputs=queue_outputs,
                )
                queue_table.select(fn=select_queue_row, inputs=queue_table, outputs=selected_group_id)
                refresh_timer = gr.Timer(2)
                refresh_timer.tick(fn=lambda: queue_refresh(queue_service), outputs=queue_outputs)

            load_optional_plugins("plugins")

        return demo
