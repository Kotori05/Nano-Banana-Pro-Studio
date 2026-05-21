# Nano Banana Pro Studio

A local Gemini image-generation workspace built with **Gradio** and the **Google GenAI SDK**. It focuses on `gemini-3-pro-image-preview`, multi-image references, PNG parameter metadata, Markdown generation logs, and a built-in smart queue.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Gradio](https://img.shields.io/badge/Gradio-5.23.2-orange)
![Vertex AI](https://img.shields.io/badge/Google-Vertex%20AI-4285F4)

## Key Features

- **Gemini image model support**: Supports `gemini-3-pro-image-preview`, `gemini-2.5-flash-image`, and related image models.
- **Full parameter controls**: Model, aspect ratio, image size, Google Search, temperature, top_p, top_k, max_output_tokens, System Instruction, and more.
- **Multi-image reference input**: The main page and smart queue both support repeated drag-and-drop image appending, plus a dedicated clear-images button.
- **Presets and last-parameter recall**: Save reusable presets and reload the latest successful generation parameters, including readable reference image paths when available.
- **PNG parameter write/read**: Generated PNG files can include a Stable Diffusion WebUI-style `parameters` text chunk. The PNG parameter page can parse it and send the values to either the main page or the smart queue.
- **Built-in smart queue**: Add multiple task groups, view the queue, move pending groups up/down, delete/cancel groups, skip one item, skip a whole group, abort, and resume.
- **Markdown export**: Chat and queue generation logs are exported to `exports/`. Queue logs record one prompt per group and per-result parameter differences.
- **Dual authentication modes**: Supports Google Cloud Service Account JSON and API Key authentication.

<img width="2271" height="1996" alt="UI Screenshot" src="https://github.com/user-attachments/assets/de815daf-3536-44f7-aca5-defd8c2db626" />

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/Kotori05/Nano-Banana-Pro-Studio.git
cd Nano-Banana-Pro-Studio
```

### 2. Create a Python environment

```bash
conda create -n banana python=3.10
conda activate banana
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

Manual install:

```bash
pip install gradio==5.23.2 google-genai==1.53.0 gradio-client protobuf google-api-core google-auth google-cloud-core googleapis-common-protos websockets Pillow requests numpy aiohttp
```

## Authentication

Choose one method.

### Method A: Google Cloud Service Account

1. Create a Service Account in Google Cloud Console and download the JSON key.
2. Make sure the Vertex AI API is enabled for the project.
3. Rename the JSON file to `GOOGLE_CLOUD_API_KEY.json` and place it in the project root.

### Method B: API Key

1. Get an API Key from Google AI Studio or Vertex AI.
2. Create `GOOGLE_CLOUD_API_KEY.txt` in the project root.
3. Paste the API Key as plain text, without quotes.

You can also paste an API Key into the UI field temporarily or provide it through the `GOOGLE_CLOUD_API_KEY` environment variable.

## Run

The only recommended launch command is:

```bash
python launch.py
```

The app automatically changes the working directory to the folder containing `launch.py` and creates `outputs/`, `exports/`, and `plugins/` when needed. The old `nano_banana_pro.py` file is no longer maintained as a compatibility launcher.

## Usage Notes

- Main-page defaults are `16:9`, `4K`, and temperature `0.9`.
- `gemini-3-pro-image-preview` may not support System Instruction. Put those instructions directly in the Prompt when using that model. Other models can still use the System Instruction field.
- PNG parameter saving is enabled by default. If “save generation parameters to PNG” is disabled, images are still saved, but the PNG parameter page will report no embedded parameters.
- PNG metadata, last parameters, and Markdown logs do not intentionally store API keys or credential paths.
- In the smart queue, “Add task group” only adds work to the queue. “Continue / start queue” starts or resumes execution.
- The smart queue is serial by default. Set concurrency before starting the queue if you want parallel execution.

## Smart Queue

The smart queue is now built in. It no longer depends on the optional plugin loader.

- Add multiple task groups continuously.
- The UI displays task groups as `1, 2, 3...`; internal IDs use timestamps.
- Pending task groups can be moved up, moved down, or deleted.
- Running groups can skip one item, skip the rest of the group, or abort.
- Network errors, timeouts, 429 errors, and temporary SSL errors retry or end in a clear terminal state instead of staying permanently running.
- Queue-generated PNG files use the same parameter metadata format and can be read back by the PNG parameter page.

## Optional Plugins

The `plugins/` folder can still load extra plugins. A plugin file should expose a `create_tab()` function. The built-in smart queue does not depend on this mechanism.

Example plugin: matrix image to GIF.

<img width="1062" height="219" alt="Matrix to GIF Plugin" src="https://github.com/user-attachments/assets/e8998b7a-91e2-4a65-b9c1-6a70b7e2f22f" />

## Security

- Never commit `GOOGLE_CLOUD_API_KEY.json`, `GOOGLE_CLOUD_API_KEY.txt`, API keys, or other credential files.
- PNG parameters, last parameters, and Markdown logs do not intentionally write API keys.

## Contributing

Feature improvements, bug fixes, and documentation updates are welcome.
