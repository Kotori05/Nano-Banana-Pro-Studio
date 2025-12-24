# 🍌 Nano Banana Pro Studio
A local Gradio application with full support for all available parameters of `gemini-3-pro-image-preview`

## Gemini 3 Pro Image Generator

A lightweight graphical interface built with **Gradio** and the **Google GenAI SDK**, designed specifically for testing and using Google Vertex AI’s latest **Gemini 3 Pro Image** (Nano Banana) model.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Gradio](https://img.shields.io/badge/Gradio-5.23.2-orange)
![Vertex AI](https://img.shields.io/badge/Google-Vertex%20AI-4285F4)

---

## ✨ Key Features

- **⚡ Latest model support**  
  Full support for all currently available parameters of `gemini-3-pro-image-preview`, including safety-related parameters  
  (although in practice, they don’t seem to be very effective).

- **🎨 Rich parameter controls**  
  Supports multiple aspect ratios such as **1:1**, **16:9**, and **21:9**, as well as **2K / 4K** resolution options.

- **🔐 Dual authentication modes**
  - **Enterprise-grade**: Google Cloud **Service Account JSON** (standard Vertex AI mode)
  - **Personal use**: **API Key** (AI Studio / Vertex Express mode)

- **📝 Configuration presets**  
  Built-in preset templates with support for saving and reusing your own commonly used parameter sets.

- **🖼️ Multimodal interaction**  
  Supports **image-to-image** generation and **multi-image fusion prompts**.

<img width="2271" height="1996" alt="UI Screenshot" src="https://github.com/user-attachments/assets/de815daf-3536-44f7-aca5-defd8c2db626" />

---

## 📦 Installation Guide

### 1. Clone the repository

    git clone https://github.com/Kotori05/Nano-Banana-Pro-Studio.git
    cd Nano-Banana-Pro-Studio

### 2. Create a Python environment (recommended)

    conda create -n banana python=3.10
    conda activate banana

### 3. Install dependencies

Option A (recommended, pinned versions):

    pip install -r requirements.txt

Option B (manual install):

    pip install gradio==5.23.2 google-genai==1.53 gradio-client protobuf \
    google-api-core google-auth google-cloud-core \
    googleapis-common-protos websockets Pillow requests numpy aiohttp

---

## 🔑 Authentication Setup

This project supports **two authentication methods**. Choose the one that fits your account type.

### Method A: Google Cloud Service Account (Recommended, stable)

- Create a **Service Account** in Google Cloud Console
- Enable the **Vertex AI API** for the project
- Download the Service Account JSON key
- Rename it to:

    GOOGLE_CLOUD_API_KEY.json

- Place it in the project root directory

---

### Method B: API Key (AI Studio / Vertex Express)

- Obtain an API Key from **Google AI Studio** or **Vertex AI**
- Create a file named:

    GOOGLE_CLOUD_API_KEY.txt

- Paste your API Key into the file (plain text, **no quotes**)
- Place the file in the project root directory

---

## 🚀 Run the Application

    cd /your/project/location
    python ./nano-banana-pro.py

On first run:
- The `outputs/` folder will be created automatically
- A configuration preset file `config.json` will also be generated

---

## 💡 Tips

- `gemini-3-pro-image-preview` **does not currently support system prompts**
  - Put system-level instructions directly into the **user prompt**
- Other Gemini models **do** support system prompts via the UI field

---

## 🧩 Plugin Tab System

- Includes a simple **plugin loader**
- Automatically scans all `.py` files under the `plugins/` directory
- Each plugin must expose a `create_tab()` function
- You can use this system to develop your own extensions

### Included plugins

#### Matrix-to-GIF conversion tool
<img width="1062" height="219" alt="Matrix to GIF Plugin" src="https://github.com/user-attachments/assets/e8998b7a-91e2-4a65-b9c1-6a70b7e2f22f" />

#### Request queue management tool
<img width="1650" height="2005" alt="Request Queue Plugin" src="https://github.com/user-attachments/assets/a07398fb-4fc5-464e-a43e-8722c720ed05" />

---

## 🤝 Contributing

- Feature contributions and improvements are welcome
- ⚠️ **NEVER upload API keys or credential files to the repository**
