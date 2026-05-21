import gradio as gr
from PIL import Image
import tempfile
import os
import time

def process_sprite_sheet(image, rows, cols, duration, loop):
    """
    核心处理逻辑
    注意：Pillow 保存 GIF 时，duration 参数单位是毫秒(int)
    """
    if image is None:
        return None
    
    # 防止 duration 为空或 0 导致报错
    if not duration or duration <= 0:
        duration = 100
    
    img_width, img_height = image.size
    frame_width = img_width // int(cols)
    frame_height = img_height // int(rows)
    
    frames = []
    for r in range(int(rows)):
        for c in range(int(cols)):
            left = c * frame_width
            top = r * frame_height
            right = left + frame_width
            bottom = top + frame_height
            frame = image.crop((left, top, right, bottom))
            frames.append(frame)
    
    # 保存为 GIF
    # 1. 定义保存目录 (例如根目录下的 outputs/gif)
    output_dir = os.path.join("outputs", "gif")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    # 2. 生成带时间戳的文件名 (避免覆盖)
    timestamp = int(time.time())
    filename = f"sprite_{timestamp}.gif"
    out_path = os.path.join(output_dir, filename)
    
    # 3. 保存
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=int(duration),
        loop=0 if loop else 1
    )
    
    print(f"[SpriteTool] GIF 已保存: {out_path}")
    return out_path

# === 联动逻辑函数 ===

def sync_duration_from_fps(fps):
    """根据 FPS 计算 帧间隔(ms)"""
    if not fps or fps <= 0:
        return gr.update() # 不更新
    # 1秒 = 1000ms
    new_duration = int(1000 / fps)
    return new_duration

def sync_fps_from_duration(duration):
    """根据 帧间隔(ms) 计算 FPS"""
    if not duration or duration <= 0:
        return gr.update() # 不更新
    new_fps = round(1000 / duration, 2)
    return new_fps

# ====================

def create_tab():
    """
    插件入口函数
    """
    with gr.Tab("🎞️ 精灵图转 GIF"):
        gr.Markdown("### 👾 Sprite Sheet to GIF Converter")
        
        with gr.Row():
            # 左侧：设置区
            with gr.Column(scale=1):
                input_img = gr.Image(label="上传精灵图 (Sprite Sheet)", type="pil")
                
                with gr.Row():
                    rows = gr.Number(label="行数 (Rows)", value=1, precision=0, minimum=1)
                    cols = gr.Number(label="列数 (Cols)", value=4, precision=0, minimum=1)
                
                # --- 联动区域 ---
                with gr.Group():
                    gr.Markdown("⏱️ **时间设置 (自动联动)**")
                    with gr.Row():
                        # FPS 输入框
                        fps = gr.Number(
                            label="帧率 (FPS)", 
                            value=10, 
                            precision=1,
                            step=1,
                            minimum=0.1
                        )
                        # Duration 输入框
                        duration = gr.Number(
                            label="帧间隔 (ms)", 
                            value=100, 
                            precision=0,
                            step=10,
                            minimum=1
                        )
                # ----------------
                
                loop = gr.Checkbox(label="循环播放 (Loop)", value=True)
                btn_convert = gr.Button("开始转换", variant="primary")
            
            # 右侧：预览区
            with gr.Column(scale=1):
                output_gif = gr.Image(label="结果 GIF")

        # === 事件绑定 ===
        
        # 1. 当 FPS 改变时 -> 更新 Duration
        fps.change(
            fn=sync_duration_from_fps,
            inputs=fps,
            outputs=duration
        )
        
        # 2. 当 Duration 改变时 -> 更新 FPS
        duration.change(
            fn=sync_fps_from_duration,
            inputs=duration,
            outputs=fps
        )

        # 3. 点击转换按钮
        # 注意：inputs 里我们只需要 duration，因为 PIL 最终要的是毫秒数
        # FPS 只是为了方便用户计算，最终值已经同步到了 duration 框里
        btn_convert.click(
            fn=process_sprite_sheet,
            inputs=[input_img, rows, cols, duration, loop],
            outputs=output_gif
        )
