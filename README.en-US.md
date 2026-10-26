# Nano Banana Pro Studio

A local Gemini image-generation workspace built with **Gradio** and the **Google GenAI SDK**. It focuses on `gemini-3-pro-image-preview`, multi-image references, PNG parameter metadata, Markdown generation logs, and a built-in smart queue.

OpenAI GPT Image generation and reference-image editing are also available on the main page and in the smart queue.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Gradio](https://img.shields.io/badge/Gradio-5.23.2-orange)
![Vertex AI](https://img.shields.io/badge/Google-Vertex%20AI-4285F4)

## Key Features

- **Gemini image model support**: Supports `gemini-3-pro-image-preview`, `gemini-2.5-flash-image`, and related image models.
- **Nano Banana 2 family**: Supports `gemini-3.1-flash-image` (2 stable), `gemini-nano-banana-2.1` (2.1), and `gemini-3.1-flash-lite-image` (2 Lite), alongside the existing 2 preview and `gemini-3-pro-image` (Pro stable). The main page and queue share the model catalogue and image routing.
- **OpenAI image models**: Supports `gpt-image-2`, `gpt-image-2.5-flare`, and `gpt-image-2.5-sunburst`. Flare targets fast everyday generation; Sunburst emphasizes editing precision.
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

### OpenAI API Key

Enter your key in the **OpenAI API Key** field above the tabs, then select a GPT Image model on the main page or in the queue. Alternatively, set `OPENAI_API_KEY` or place a plain-text key in `OPENAI_API_KEY.txt` in the project root. Precedence is UI > environment > file. Google credentials and an additional OpenAI SDK are not required.

- Text-only requests use `/v1/images/generations`; reference images and images from conversation history use `/v1/images/edits`. Up to 16 reference images are supported, including previous generated images for successive edits.
- `1K / 2K / 4K` target maximum edges of `1024 / 2048 / 3840`, adjusted to the supported pixel budget. The UI displays the actual requested resolution: `16:9 + 4K` is `3840x2160`, while `1:1 + 4K` is `2880x2880`. Aspect ratios must be between `1:3` and `3:1`. Resolutions above `2560x1440` are experimental.
- Quality uses the API default, `auto`. System Instruction is included in the prompt. Google Search, temperature, top_p, top_k, and max_output_tokens apply only to Gemini.
- Keys are excluded from presets, PNG metadata, last parameters, and Markdown logs. Each queue group retains its submitted key in memory; a blank key uses the environment / local key file.

See the [official OpenAI image documentation](https://developers.openai.com/api/docs/guides/image-generation). As of October 27, 2026, the newest image models listed are GPT Image 2.5 Flare / Sunburst. The deprecated `chatgpt-image-latest` alias is excluded from the default choices.

## Run

The only recommended launch command is:

```bash
python launch.py
```

The app automatically changes the working directory to the folder containing `launch.py` and creates `outputs/`, `exports/`, and `plugins/` when needed. The old `nano_banana_pro.py` file is no longer maintained as a compatibility launcher.

## Usage Notes

- Main-page defaults are `16:9`, `4K`, and temperature `0.9`.
- Gemini image models include System Instruction in the user prompt instead of sending an unsupported `system` content role. Text models use the native `system_instruction` configuration.
- Nano Banana 2 / 2.1 support 1K, 2K, 4K, and panoramic aspect ratios. 2 Lite supports only 1K, up to 4096 output tokens, and no search grounding; the main page and queue apply these limits automatically. See the [official Google image documentation](https://ai.google.dev/gemini-api/docs/image-generation).
- PNG parameter saving is enabled by default. If “save generation parameters to PNG” is disabled, images are still saved, but the PNG parameter page will report no embedded parameters.
- PNG metadata, last parameters, and Markdown logs do not intentionally store API keys or credential paths.
- Do not commit `OPENAI_API_KEY.txt`; it is included in `.gitignore`.
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
