from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image
from google.genai import types

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

from nbp.config import DEFAULT_MODEL_OPTIONS, GEMINI_IMAGE_MODELS, MODEL_CHOICES, NANO_BANANA_2_LITE_MODEL
from nbp.generation import IMAGE_MODELS, GenerationService, build_generate_config, call_gemini_vertex
from nbp.params import GenerationParams
from nbp.png_metadata import read_png_parameters
from nbp.queue_service import QueueService
from nbp.ui import create_gradio_app, model_controls_for_ui, model_image_size_for_ui, queue_model_controls_for_ui


NANO_BANANA_2_MODELS = (
    "gemini-3.1-flash-image-preview",
    "gemini-3.1-flash-image",
    "gemini-nano-banana-2.1",
    NANO_BANANA_2_LITE_MODEL,
)


class GeminiImagesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        original_cwd = Path.cwd()
        os.chdir(temp.name)
        self.addCleanup(os.chdir, original_cwd)
        buffer = io.BytesIO()
        Image.new("RGB", (32, 32), "yellow").save(buffer, format="PNG")
        self.image_bytes = buffer.getvalue()
        self.client = Mock()
        self.client.models.generate_content.return_value = types.GenerateContentResponse(
            candidates=[types.Candidate(
                finish_reason="STOP",
                content=types.Content(role="model", parts=[types.Part.from_bytes(data=self.image_bytes, mime_type="image/png")]),
            )],
        )
        client_patch = patch("nbp.generation.create_client", return_value=self.client)
        client_patch.start()
        self.addCleanup(client_patch.stop)
        for name in ("_debug_print_send", "_debug_print_recv"):
            debug_patch = patch("nbp.generation." + name)
            debug_patch.start()
            self.addCleanup(debug_patch.stop)

    def test_menu_and_generation_share_all_image_models(self):
        self.assertEqual(set(GEMINI_IMAGE_MODELS), IMAGE_MODELS)
        self.assertTrue(IMAGE_MODELS.issubset(DEFAULT_MODEL_OPTIONS))
        self.assertEqual(DEFAULT_MODEL_OPTIONS[3], "gemini-3-pro-image-preview")
        labels = dict((value, label) for label, value in MODEL_CHOICES)
        for model in NANO_BANANA_2_MODELS:
            self.assertIn("Nano Banana 2", labels[model])
        self.assertIn("gemini-3-pro-image", IMAGE_MODELS)

    def test_every_nano_banana_2_model_generates_images_and_roundtrips_parameters(self):
        for model in NANO_BANANA_2_MODELS:
            with self.subTest(model=model):
                params = GenerationParams(prompt="A banana", model_name=model, image_size="4K")
                text, paths = GenerationService().generate("google-test-key", params)
                request = self.client.models.generate_content.call_args.kwargs
                self.assertEqual(request["model"], model)
                self.assertEqual(request["config"].response_modalities, ["TEXT", "IMAGE"])
                self.assertEqual(request["config"].image_config.aspect_ratio, "16:9")
                self.assertEqual(request["config"].image_config.image_size,
                                 "1024px" if model == NANO_BANANA_2_LITE_MODEL else "4K")
                self.assertIn("Image generated", text)
                self.assertEqual(len(paths), 1)
                saved, _ = read_png_parameters(paths[0])
                self.assertEqual(saved.model_name, model)
                self.assertEqual(saved.image_size, "1K" if model == NANO_BANANA_2_LITE_MODEL else "4K")

    def test_standard_models_keep_all_three_sizes_and_panorama_ratios(self):
        for model in NANO_BANANA_2_MODELS[:-1]:
            for size in ("1K", "2K", "4K"):
                for ratio in ("16:9", "1:4", "4:1", "1:8", "8:1"):
                    with self.subTest(model=model, size=size, ratio=ratio):
                        params = GenerationParams(model_name=model, image_size=size, aspect_ratio=ratio)
                        config = build_generate_config(params, want_image=True, want_thinking=False)
                        self.assertEqual(config.image_config.image_size, size)
                        self.assertEqual(config.image_config.aspect_ratio, ratio)

    def test_lite_normalizes_unsupported_defaults_for_direct_calls_and_queue_arrays(self):
        params = GenerationParams(model_name=NANO_BANANA_2_LITE_MODEL, enable_search=True, max_output_tokens=8192)
        normalized = GenerationParams.from_dict(params.public_dict())
        self.assertEqual(normalized.image_size, "1K")
        self.assertFalse(normalized.enable_search)
        self.assertEqual(normalized.max_output_tokens, 4096)
        queue = QueueService(GenerationService())
        queue.submit_group("banana", [], 2, "Parameters Only", params,
                           {"image_size": "4K,2K", "enable_search": "1", "max_output_tokens": "8192"}, "google-test-key")
        group = queue._groups[0]
        for item in group["items"]:
            queue._run_item(group, item)
            config = self.client.models.generate_content.call_args.kwargs["config"]
            self.assertEqual(config.image_config.image_size, "1024px")
            self.assertLessEqual(config.max_output_tokens, 4096)
            self.assertFalse(config.tools)
            self.assertEqual(item["status"], "completed")

    def test_image_system_instructions_are_user_content_and_references_are_sent(self):
        Path("reference.png").write_bytes(self.image_bytes)
        params = GenerationParams(model_name="gemini-nano-banana-2.1", prompt="Make it yellow", system_instruction="Keep the subject")
        call_gemini_vertex("google-test-key", params, [{"role": "user", "text": "Previous request"}], ["reference.png"])
        contents = self.client.models.generate_content.call_args.kwargs["contents"]
        self.assertTrue(all(content.role in {"user", "model"} for content in contents))
        current = contents[-1]
        self.assertEqual(current.parts[0].text, "Keep the subject")
        self.assertEqual(current.parts[1].text, "Make it yellow")
        self.assertEqual(current.parts[2].inline_data.data, self.image_bytes)

    def test_text_model_uses_system_instruction_config(self):
        config = build_generate_config(GenerationParams(model_name="gemini-2.5-flash", system_instruction="Be concise"),
                                       want_image=False, want_thinking=False)
        self.assertEqual(config.system_instruction, "Be concise")

    def test_lite_ui_constraints_and_both_model_menus(self):
        updates = model_controls_for_ui(NANO_BANANA_2_LITE_MODEL, "16:9", "4K")
        self.assertFalse(updates[1]["interactive"])
        self.assertFalse(updates[1]["value"])
        self.assertEqual(updates[-2]["maximum"], 4096)
        self.assertEqual(model_image_size_for_ui(NANO_BANANA_2_LITE_MODEL, "4K")["value"], "1K")
        self.assertEqual(model_image_size_for_ui("gemini-nano-banana-2.1", "1K")["choices"], ["4K", "2K", "1K"])
        self.assertEqual([update["value"] for update in queue_model_controls_for_ui(NANO_BANANA_2_LITE_MODEL)],
                         ["1K", "0", "4096"])
        demo = create_gradio_app()
        self.addCleanup(demo.close)
        dropdowns = [block for block in demo.blocks.values() if getattr(block, "label", "") == "模型"]
        self.assertEqual(len(dropdowns), 2)
        for dropdown in dropdowns:
            self.assertTrue(set(NANO_BANANA_2_MODELS).issubset(value for _, value in dropdown.choices))


if __name__ == "__main__":
    unittest.main()
