import gradio as gr
import time
import random
import json
import traceback
from datetime import datetime

# 尝试从主程序导入核心调用函数和配置
# 注意：为了避免循环导入，建议在函数内部导入，或者确保 nano-banana--pro.py 结构允许
try:
    from nano-banana-pro import call_gemini_vertex, DEFAULT_MODEL_OPTIONS
except ImportError:
    # 如果独立运行或导入失败的 fallback
    DEFAULT_MODEL_OPTIONS = ["gemini-3-pro-image-preview"]
    print("[QueueManager] ⚠️ 无法导入 nano-banana-pro.py，请确保文件在同一目录下")

# ================= 工具函数：参数解析 =================

def parse_param_array(input_str: str, target_length: int, default_val, converter=str):
    """
    解析参数字符串为列表，并自动填充/截断
    输入: "0, 1", target=4, default="0"
    输出: [0, 1, 1, 1] (类型由 converter 决定)
    """
    if not input_str or not str(input_str).strip():
        return [default_val] * target_length
    
    # 1. 分割并去空
    raw_list = [x.strip() for x in str(input_str).split(',')]
    
    # 2. 转换类型
    processed_list = []
    for x in raw_list:
        try:
            processed_list.append(converter(x))
        except:
            processed_list.append(default_val)
            
    if not processed_list:
        return [default_val] * target_length

    # 3. 填充或截断
    current_len = len(processed_list)
    if current_len >= target_length:
        return processed_list[:target_length]
    else:
        # 复制最后一个元素来填充
        last_val = processed_list[-1]
        return processed_list + [last_val] * (target_length - current_len)

def format_queue_log(queue_data, current_status=""):
    """格式化队列状态日志"""
    log = f"=== 📟 队列监控面板 ({datetime.now().strftime('%H:%M:%S')}) ===\n"
    if current_status:
        log += f"▶️ 当前状态: {current_status}\n"
    
    log += "\n" + "-"*30 + "\n"
    
    # 倒序显示，新的在上面
    for idx, item in enumerate(reversed(queue_data)):
        real_idx = len(queue_data) - 1 - idx
        status_icon = {
            "pending": "⏳ 等待中",
            "running": "🔄 执行中",
            "completed": "✅ 已完成",
            "failed": "❌ 已失败",
            "partial": "⚠️ 部分完成"
        }.get(item['status'], item['status'])
        
        log += f"[{real_idx+1}] {status_icon} | 批次: {item['done_count']}/{item['total_count']}\n"
        log += f"   📝 提示词: {item['prompt'][:30]}...\n"
        if item.get('error_msg'):
            log += f"   ❗ 错误: {item['error_msg']}\n"
        log += "-"*30 + "\n"
            
    return log

# ================= 核心逻辑：带重试的执行器 =================

def execute_queue_task(
    prompt, ref_images, batch_count,
    param_arrays, # 字典：包含所有参数的原始字符串
    api_key, system_instruction,
    strategy_mode
):
    """
    生成器函数：逐步执行队列任务并 yield 状态
    """
    from nano-banana--pro import call_gemini_vertex # 延迟导入
    
    results = []
    logs = []
    
    # 1. 解析所有参数数组
    # 将 "1:1, 16:9" 这种字符串解析为对应每次循环的 list
    parsed_params = {
        "aspect_ratio": parse_param_array(param_arrays['aspect_ratio'], batch_count, "1:1"),
        "image_size": parse_param_array(param_arrays['image_size'], batch_count, "1K"),
        "enable_search": parse_param_array(param_arrays['enable_search'], batch_count, 0, int), # 0/1
        "temperature": parse_param_array(param_arrays['temperature'], batch_count, 0.9, float),
        "top_p": parse_param_array(param_arrays['top_p'], batch_count, 0.95, float),
        "top_k": parse_param_array(param_arrays['top_k'], batch_count, 40, int),
        "max_output_tokens": parse_param_array(param_arrays['max_output_tokens'], batch_count, 8192, int),
    }

    # 2. 循环执行
    for i in range(batch_count):
        current_prompt = prompt
        
        # --- 策略应用 ---
        if strategy_mode == "随机噪声 (Seed Salting)":
            seed = random.randint(10000, 99999)
            current_prompt = f"{prompt} \n(Random Seed: {seed}, Batch: {i+1})"
        elif strategy_mode == "语义重写 (Flash Rewrite)":
            # 这里简化处理，实际应该调用 flash 模型重写
            # 暂时用简单的后缀模拟
            modifiers = ["Cinematic Lighting", "Wide Angle", "Close-up", "Cyberpunk Style", "Watercolor"]
            mod = modifiers[i % len(modifiers)]
            current_prompt = f"{prompt}, {mod}"
        
        # --- 获取当前轮次的参数 ---
        cur_aspect = parsed_params["aspect_ratio"][i]
        cur_size = parsed_params["image_size"][i]
        cur_search = bool(parsed_params["enable_search"][i])
        cur_temp = parsed_params["temperature"][i]
        cur_top_p = parsed_params["top_p"][i]
        cur_top_k = parsed_params["top_k"][i]
        cur_tokens = parsed_params["max_output_tokens"][i]
        
        status_msg = f"正在执行第 {i+1}/{batch_count} 张... \n尺寸: {cur_aspect} | 搜索: {cur_search} | Temp: {cur_temp}"
        yield results, i, status_msg, None # 更新状态

        # --- 带有错误退让的 API 调用 ---
        max_retries = 3
        retry_delay = 5 # 初始等待秒数
        success = False
        
        for attempt in range(max_retries):
            try:
                # 调用主程序的函数
                # 注意：history_messages 传空，确保单次独立生成
                text_out, img_paths = call_gemini_vertex(
                    api_key=api_key,
                    model_name="gemini-3-pro-image-preview", # 强制使用画图模型，或者做成参数
                    history_messages=[], 
                    user_text=current_prompt,
                    user_images=ref_images,
                    aspect_ratio=cur_aspect,
                    image_size=cur_size,
                    system_instruction=system_instruction,
                    temperature=cur_temp,
                    top_p=cur_top_p,
                    top_k=cur_top_k,
                    max_output_tokens=cur_tokens,
                    enable_search=cur_search
                )
                
                if img_paths:
                    results.extend(img_paths)
                    success = True
                    break # 成功，跳出重试循环
                else:
                    # 如果返回空（可能是被拦截），视为非致命错误，不重试，直接下一张
                    print(f"[Queue] 第 {i+1} 张未生成图片: {text_out}")
                    break 

            except Exception as e:
                err_str = str(e)
                print(f"[Queue Error] Attempt {attempt+1}: {err_str}")
                
                # === 错误分类处理 ===
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    wait_time = retry_delay * (2 ** attempt) # 指数退避: 5s, 10s, 20s
                    yield results, i, f"⚠️ 触发限流 (429)，冷却 {wait_time} 秒...", None
                    time.sleep(wait_time)
                    continue # 重试
                
                elif "400" in err_str or "INVALID_ARGUMENT" in err_str:
                    yield results, i, f"❌ 参数错误 (400)，跳过本任务...", f"400 Error: {err_str}"
                    # 400 错误通常无法通过重试解决（如参数不对），直接跳出重试，甚至可以 return 终止整个 batch
                    # 这里选择跳过当前这张，继续下一张
                    success = False
                    break 
                
                else:
                    # 其他未知错误，尝试重试
                    wait_time = 5
                    time.sleep(wait_time)
        
        if not success:
            # 如果重试多次依然失败
            pass
            
        # 强制冷却一小会儿，避免连续请求过于密集
        time.sleep(2)

    yield results, batch_count, "任务完成", None


# ================= Gradio 界面构建 =================

def process_queue_click(
    prompt, ref_images, batch_count, strategy,
    ar_arr, size_arr, search_arr, temp_arr, top_p_arr, top_k_arr, token_arr,
    api_key, sys_inst,
    queue_data
):
    """
    响应“加入队列并执行”按钮
    """
    # 1. 新建任务对象
    new_task = {
        "id": int(time.time()),
        "prompt": prompt,
        "total_count": int(batch_count),
        "done_count": 0,
        "status": "pending", # pending -> running -> completed/failed
        "error_msg": ""
    }
    
    queue_data = queue_data or []
    queue_data.append(new_task)
    
    # 2. 更新日志显示 (Pending)
    yield queue_data, format_queue_log(queue_data, "准备开始..."), []
    
    # 3. 开始执行
    # 更新当前任务状态为 running
    queue_data[-1]['status'] = "running"
    
    param_arrays = {
        "aspect_ratio": ar_arr, "image_size": size_arr, "enable_search": search_arr,
        "temperature": temp_arr, "top_p": top_p_arr, "top_k": top_k_arr, "max_output_tokens": token_arr
    }
    
    try:
        # 调用生成器
        iterator = execute_queue_task(
            prompt, ref_images, int(batch_count), param_arrays,
            api_key, sys_inst, strategy
        )
        
        for img_results, done_idx, status_text, err in iterator:
            # 实时更新状态
            queue_data[-1]['done_count'] = done_idx
            
            if err:
                queue_data[-1]['error_msg'] = err
            
            # 刷新界面
            log_str = format_queue_log(queue_data, status_text)
            yield queue_data, log_str, img_results
            
        # 完成
        queue_data[-1]['status'] = "completed" if not queue_data[-1].get('error_msg') else "partial"
        yield queue_data, format_queue_log(queue_data, "✅ 所有任务执行完毕"), img_results
        
    except Exception as e:
        traceback.print_exc()
        queue_data[-1]['status'] = "failed"
        queue_data[-1]['error_msg'] = str(e)
        yield queue_data, format_queue_log(queue_data, "❌ 执行过程中发生致命错误"), []


def create_tab():
    with gr.Tab("📚 智能队列 (Smart Queue)"):
        gr.Markdown("### 🛠️ 批量生成与参数矩阵")
        
        # 状态存储
        queue_state = gr.State([]) 
        
        with gr.Row():
            # --- 左侧：控制面板 ---
            with gr.Column(scale=4):
                
                # 1. 状态监控
                log_box = gr.TextArea(
                    label="队列状态监控", 
                    value="等待任务...", 
                    lines=8, 
                    max_lines=10,
                    interactive=False,
                    elem_id="queue-log"
                )
                
                # 2. 基础输入 (与主界面一致)
                prompt_input = gr.Textbox(label="提示词 (Prompt)", lines=3, placeholder="输入画面描述...")
                ref_image_input = gr.File(label="参考图片 (可选)", file_count="multiple", type="filepath")
                
                with gr.Row():
                    batch_slider = gr.Slider(label="执行次数 (Batch Size)", minimum=1, maximum=9, value=4, step=1)
                    strategy_radio = gr.Radio(
                        label="差异化策略", 
                        choices=["随机噪声 (Seed Salting)", "语义重写 (Flash Rewrite)", "仅参数变化"], 
                        value="随机噪声 (Seed Salting)"
                    )
                
                # 3. 高级参数矩阵 (Accordion 折叠)
                with gr.Accordion("📐 参数矩阵 (数组模式)", open=False):
                    gr.Markdown(
                        "输入以逗号分隔的值 (例如 `0, 1, 1`)。系统会自动对应到每一次循环。\n"
                        "如果值的数量少于执行次数，会自动复制最后一个值补全。"
                    )
                    with gr.Row():
                        ar_input = gr.Textbox(label="宽高比 (Aspect Ratio)", value="1:1, 16:9", placeholder="1:1, 16:9...")
                        size_input = gr.Textbox(label="尺寸 (Size)", value="1K", placeholder="1K, 2K...")
                    
                    with gr.Row():
                        search_input = gr.Textbox(label="是否搜索 (0=否, 1=是)", value="0", placeholder="0, 1, 0...")
                        temp_input = gr.Textbox(label="Temperature", value="0.9, 1.2", placeholder="0.9, 1.2...")
                    
                    with gr.Row():
                        topp_input = gr.Textbox(label="Top P", value="0.95")
                        topk_input = gr.Textbox(label="Top K", value="40")
                        token_input = gr.Textbox(label="Max Tokens", value="8192")

                # 4. 隐藏的 API Key 输入 (从主 Tab 传递过来比较麻烦，这里简单再放一个或默认读取环境变量)
                # 为了简便，建议用户在主 Tab 填好 Key，这里直接用环境变量，或者再放一个 Textbox
                api_key_input = gr.Textbox(label="API Key (如未设置环境变量请在此输入)", type="password")
                sys_inst_input = gr.Textbox(label="系统指令", value="", lines=1)

                btn_run = gr.Button("🚀 加入队列并启动", variant="primary")

            # --- 右侧：结果画廊 ---
            with gr.Column(scale=5):
                gallery = gr.Gallery(label="生成结果", columns=3, height=800, object_fit="contain")

        # 事件绑定
        btn_run.click(
            fn=process_queue_click,
            inputs=[
                prompt_input, ref_image_input, batch_slider, strategy_radio,
                ar_input, size_input, search_input, temp_input, topp_input, topk_input, token_input,
                api_key_input, sys_inst_input,
                queue_state
            ],
            outputs=[queue_state, log_box, gallery]
        )
