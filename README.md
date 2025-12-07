# 🍌-Nano-Banana-Pro-Studio
支持 `gemini-3-pro-image-preview`全部可用参数的本地gradio应用
# Gemini 3 Pro Image Generator

一个基于 **Gradio** 和 **Google GenAI SDK** 构建的轻量级图形界面，专为测试和使用 Google Vertex AI 最新的 **Gemini 3 Pro Image** (Nano Banana) 模型而设计。

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Gradio](https://img.shields.io/badge/Gradio-5.9.1-orange)
![Vertex AI](https://img.shields.io/badge/Google-Vertex%20AI-4285F4)

## ✨ 主要特性

* **⚡️ 最新模型支持**：完美支持 `gemini-3-pro-image-preview` 和 `gemini-2.5-flash-image`。
* **🛠️ SDK 补丁**：内置了绕过 SDK 强类型校验的逻辑，解决了 `image_size` 和 `person_generation` 参数报错的问题。
* **🎨 丰富的参数控制**：支持 1:1, 16:9, 21:9 等多种宽高比，以及 4K/2K 分辨率选择。
* **🔐 双重认证模式**：
    * **企业级**：支持 Service Account JSON (Vertex AI 标准模式)。
    * **个人级**：支持 API Key (AI Studio / Vertex Express 模式)。
* **📝 配置模板**：内置快捷模板，支持自定义保存常用参数预设。
* **🖼️ 多模态交互**：支持“图生图”和多图融合指令。

## 📦 安装指南
1. 克隆仓库
2. 创建环境 (推荐)
conda create -n banana python=3.10
conda activate banana
3. 安装依赖
pip install -r requirements.txt
pip install gradio==5.9.1 google-genai==1.53 gradio-client protobuf google-api-core google-auth google-cloud-core googleapis-common-protos websockets Pillow requests numpy aiohttp


🔑 配置认证
本项目支持两种认证方式，请根据你的账号类型选择一种：

方式 A：使用 Google Cloud Service Account (推荐，稳定)
在 Google Cloud Console 中创建一个 Service Account 并下载 JSON 密钥。

确保该项目已启用 Vertex AI API。

将 JSON 文件重命名为 GOOGLE_CLOUD_API_KEY.json 并放入项目根目录。

方式 B：使用 API Key
在 Google AI Studio 或 Vertex AI 获取 API Key。

创建一个名为 GOOGLE_CLOUD_API_KEY.txt 的文件放入项目根目录。

将 API Key 粘贴到文件中（纯文本，不要包含引号）。

🚀 运行
python banana.py

🤝 贡献
欢迎提交功能更新
⚠️ 绝对不要上传密钥文件！！！
