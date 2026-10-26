# Nano Banana Pro Studio

一个基于 **Gradio** 和 **Google GenAI SDK** 的本地 Gemini 图像生成工作台，重点支持 `gemini-3-pro-image-preview`、多图参考、PNG 参数读写、Markdown 记录导出和内置智能队列。

现已支持 OpenAI GPT Image 文生图与参考图编辑，主页面和智能队列均可使用。

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Gradio](https://img.shields.io/badge/Gradio-5.23.2-orange)
![Vertex AI](https://img.shields.io/badge/Google-Vertex%20AI-4285F4)

## 主要功能

- **Gemini 图像模型支持**：支持 `gemini-3-pro-image-preview`、`gemini-2.5-flash-image` 等图像模型。
- **Nano Banana 2 系列**：支持 `gemini-3.1-flash-image`（2 正式版）、`gemini-nano-banana-2.1`（2.1）、`gemini-3.1-flash-lite-image`（2 Lite），并保留 2 的预览版；也支持 `gemini-3-pro-image`（Pro 正式版）。主页面和队列共用模型列表与图像调用配置。
- **OpenAI 图像模型支持**：支持 `gpt-image-2`、`gpt-image-2.5-flare` 和 `gpt-image-2.5-sunburst`；Flare 侧重日常生成速度，Sunburst 侧重编辑精度。
- **完整参数控制**：支持模型、宽高比、图片尺寸、Google Search、temperature、top_p、top_k、max_output_tokens、System Instruction 等参数。
- **多图参考输入**：主页面和智能队列均支持多次拖拽追加参考图，并可单独清空待发送图片。
- **参数预设与上次参数回读**：可保存常用参数预设，也可读取最近一次成功生成使用的参数和可读取到的参考图路径。
- **PNG 参数写入与读取**：保存 PNG 时可写入 Stable Diffusion WebUI 风格的 `parameters` 文本块；PNG 参数读取页可解析参数并发送到主页面或智能队列。
- **内置智能队列**：支持连续加入多个任务组、查看队列、上移/下移、删除/取消、跳过单项、跳过组、中止和继续执行。
- **Markdown 记录导出**：对话和队列生成记录会导出到 `exports/`，队列任务按组记录提示词和每张结果的差异参数。
- **双认证模式**：支持 Google Cloud Service Account JSON，也支持 API Key。

<img width="2271" height="1996" alt="UI Screenshot" src="https://github.com/user-attachments/assets/de815daf-3536-44f7-aca5-defd8c2db626" />

## 安装

### 1. 克隆仓库

```bash
git clone https://github.com/Kotori05/Nano-Banana-Pro-Studio.git
cd Nano-Banana-Pro-Studio
```

### 2. 创建 Python 环境

```bash
conda create -n banana python=3.10
conda activate banana
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

如需手动安装：

```bash
pip install gradio==5.23.2 google-genai==1.53.0 gradio-client protobuf google-api-core google-auth google-cloud-core googleapis-common-protos websockets Pillow requests numpy aiohttp
```

## 配置认证

任选一种方式。

### 方式 A：Google Cloud Service Account

1. 在 Google Cloud Console 创建 Service Account，并下载 JSON 密钥。
2. 确认项目已启用 Vertex AI API。
3. 将 JSON 文件重命名为 `GOOGLE_CLOUD_API_KEY.json`，放到项目根目录。

### 方式 B：API Key

1. 在 Google AI Studio 或 Vertex AI 获取 API Key。
2. 在项目根目录创建 `GOOGLE_CLOUD_API_KEY.txt`。
3. 将 API Key 以纯文本写入文件，不要包含引号。

也可以在页面中的 API Key 输入框临时填写，或通过环境变量 `GOOGLE_CLOUD_API_KEY` 提供。

### OpenAI API Key

在页面顶部的 **OpenAI API Key（主页面 / 智能队列共用）** 输入框填写密钥，然后选择 GPT Image 模型。也可通过环境变量 `OPENAI_API_KEY` 或根目录的 `OPENAI_API_KEY.txt` 提供纯文本密钥。优先级为页面填写 > 环境变量 > 文件；无需 Google 认证，也无需安装额外 SDK。

- 无参考图时调用 `/v1/images/generations`，有参考图或对话历史图片时调用 `/v1/images/edits`。最多 16 张参考图，连续修改会携带此前生成的图片。
- `1K / 2K / 4K` 分别按目标最大边 `1024 / 2048 / 3840` 换算，必要时调整以满足总像素范围；实际请求尺寸显示在界面中。例如 `16:9 + 4K` 为 `3840x2160`，`1:1 + 4K` 为 `2880x2880`。宽高比限 `1:3` 至 `3:1`，不支持长条图选项。超过 `2560x1440` 的尺寸为实验支持。
- 质量使用 API 默认的 `auto`。System Instruction 会合并到提示词；Google Search、temperature、top_p、top_k、max_output_tokens 仅对 Gemini 生效。
- 密钥不写入预设、PNG、上次参数或 Markdown 记录。队列任务使用提交时填写的 OpenAI Key；留空时使用环境变量 / 本地密钥文件。

模型与接口依据 [OpenAI 官方图像文档](https://developers.openai.com/api/docs/guides/image-generation)。截至 2026-10-27，官方模型目录中较新图像模型为 GPT Image 2.5 Flare / Sunburst；`chatgpt-image-latest` 已标记弃用，未加入默认列表。

## 启动

当前唯一推荐启动入口是：

```bash
python launch.py
```

程序会自动切换到 `launch.py` 所在目录，并创建 `outputs/`、`exports/`、`plugins/` 等目录。旧的 `nano_banana_pro.py` 不再作为兼容启动入口维护。

## 使用说明

- 主页面默认参数为 `16:9`、`4K`、temperature `0.9`。
- Gemini 图像模型的 System Instruction 自动合并到 Prompt，避免不受支持的 `system` 消息角色；文本模型使用原生 `system_instruction` 配置。
- Nano Banana 2 / 2.1 支持 1K、2K、4K 以及长条图比例。2 Lite 仅支持 1K、最多 4096 输出 tokens 且不支持搜索；主页面和队列会自动应用这些限制。模型能力以 [Google 官方文档](https://ai.google.dev/gemini-api/docs/image-generation) 为准。
- PNG 参数默认开启保存；关闭“保存生成参数到 PNG”后仍会保存图片，但 PNG 参数读取页会提示无参数。
- PNG 参数读取页不会写入或展示 API key、凭证路径等敏感信息。
- 智能队列中，“加入任务组”只负责入队；“继续 / 启动队列”负责开始或恢复执行。
- 智能队列默认串行执行，并发数可在启动队列前设置。

## 智能队列

智能队列已经内置，不再作为松散插件依赖主文件导入。

- 支持连续提交多个任务组。
- 队列列表以 `1、2、3...` 显示任务组，内部使用时间戳 ID。
- pending 任务组可上移、下移、删除。
- running 任务组可跳过单项、跳过组、中止。
- 网络异常、超时、429、SSL 临时错误会进入重试或明确失败状态，不会长期停留在 running。
- 队列生成图片同样支持 PNG 参数写入，也可被 PNG 参数读取页回填。

## 可选插件

`plugins/` 目录仍可用于加载额外插件。插件文件需要提供 `create_tab()` 函数。内置智能队列不再依赖该机制。

示例插件：矩阵图转 GIF。

<img width="1062" height="219" alt="Matrix to GIF Plugin" src="https://github.com/user-attachments/assets/e8998b7a-91e2-4a65-b9c1-6a70b7e2f22f" />

## 安全提醒

- 不要提交 `GOOGLE_CLOUD_API_KEY.json`、`GOOGLE_CLOUD_API_KEY.txt`、API key 或其他凭证文件。
- 不要提交 `OPENAI_API_KEY.txt`；该文件已加入 `.gitignore`。
- PNG 参数、上次参数和 Markdown 记录不会主动写入 API key。

## 贡献

欢迎提交功能改进、Bug 修复和文档更新。
