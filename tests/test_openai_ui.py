from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

from nbp.config import ASPECT_RATIO_OPTIONS, OPENAI_IMAGE_MODELS
from nbp.queue_service import QueueService
from nbp.ui import create_gradio_app, model_controls_for_ui


class OpenAIUITests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        original_cwd = Path.cwd()
        os.chdir(temp.name)
        self.addCleanup(os.chdir, original_cwd)
        self.demo = create_gradio_app()
        self.addCleanup(self.demo.close)

    def key_callbacks(self):
        key = next(block for block in self.demo.blocks.values()
                   if getattr(block, "label", "") == "OpenAI API Key（主页面 / 智能队列共用）")
        self.assertEqual(key.type, "password")
        self.assertFalse(key.value)
        callbacks = [fn for fn in self.demo.fns.values() if key in fn.inputs]
        self.assertEqual(len(callbacks), 2)
        return callbacks

    @staticmethod
    def arguments(fn):
        values = []
        for component in fn.inputs:
            value = component.value
            if getattr(component, "label", "") == "OpenAI API Key（主页面 / 智能队列共用）":
                value = "ui-openai-key"
            elif getattr(component, "label", "") == "模型":
                value = "gpt-image-2.5-flare"
            elif getattr(component, "label", "") in {"Prompt", "Prompt / 消息"}:
                value = "A blue bird"
            values.append(value)
        return values

    def test_models_and_key_are_bound_to_main_and_queue(self):
        models = [block for block in self.demo.blocks.values() if getattr(block, "label", "") == "模型"]
        self.assertEqual(len(models), 2)
        for dropdown in models:
            values = [choice[1] for choice in dropdown.choices]
            self.assertTrue(all(model in values for model in OPENAI_IMAGE_MODELS))
        self.key_callbacks()

    def test_actual_main_callback_passes_openai_key_and_keeps_edit_history(self):
        callback = next(fn for fn in self.key_callbacks() if len(fn.outputs) == 7)
        with patch("nbp.generation.call_openai_images", return_value=("done", ["previous.png"])) as call:
            result = callback.fn(*self.arguments(callback))
        self.assertEqual(call.call_args.args[0], "ui-openai-key")
        self.assertEqual(call.call_args.args[1].model_name, "gpt-image-2.5-flare")
        self.assertEqual(result[1][-1]["images"], ["previous.png"])
        for export in Path("exports").rglob("*.md"):
            self.assertNotIn("ui-openai-key", export.read_text())

    def test_actual_queue_callback_snapshots_key_without_persisting_it(self):
        callback = next(fn for fn in self.key_callbacks() if len(fn.outputs) == 4)
        callback.fn(*self.arguments(callback))
        queue = next(cell.cell_contents for cell in callback.fn.__closure__
                     if isinstance(cell.cell_contents, QueueService))
        group = queue._groups[-1]
        self.assertEqual(group["openai_api_key"], "ui-openai-key")
        self.assertEqual(group["base_params"].model_name, "gpt-image-2.5-flare")
        self.assertNotIn("openai_api_key", group["base_params"].public_dict())

    def test_switching_models_filters_ratios_and_disables_gemini_controls(self):
        updates = model_controls_for_ui("gpt-image-2.5-sunburst", ASPECT_RATIO_OPTIONS[-1], "4K")
        self.assertEqual(updates[0]["value"], ASPECT_RATIO_OPTIONS[0])
        self.assertEqual(len(updates[0]["choices"]), 10)
        self.assertTrue(all(not update["interactive"] for update in updates[1:-1]))
        self.assertIn("3840x2160", updates[-1])
        updates = model_controls_for_ui("gemini-3-pro-image-preview", ASPECT_RATIO_OPTIONS[0], "4K")
        self.assertEqual(updates[0]["choices"], ASPECT_RATIO_OPTIONS)
        self.assertTrue(all(update["interactive"] for update in updates[1:-1]))


if __name__ == "__main__":
    unittest.main()
