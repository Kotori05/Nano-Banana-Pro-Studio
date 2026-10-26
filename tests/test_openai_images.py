from __future__ import annotations

import base64
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from PIL import Image

from nbp.config import ASPECT_RATIO_OPTIONS, OPENAI_IMAGE_MODELS, load_openai_api_key_from_file
from nbp.generation import GenerationService
from nbp.openai_images import call_openai_images, is_openai_image_model, openai_image_size
from nbp.params import GenerationParams, load_last_params
from nbp.png_metadata import read_png_parameters
from nbp.queue_service import QueueService


class OpenAIImagesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        original_cwd = Path.cwd()
        os.chdir(self.temp.name)
        self.addCleanup(os.chdir, original_cwd)
        self.env = patch.dict(os.environ, {"OPENAI_API_KEY": "", "GOOGLE_CLOUD_API_KEY": "google-key"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.params = GenerationParams(prompt="A blue bird", model_name="gpt-image-2", image_size="2K")
        buffer = io.BytesIO()
        Image.new("RGB", (32, 32), "blue").save(buffer, format="PNG")
        self.encoded_image = base64.b64encode(buffer.getvalue()).decode("ascii")
        self.post = patch("nbp.openai_images.requests.post")
        self.mock_post = self.post.start()
        self.addCleanup(self.post.stop)
        self.mock_post.return_value = self.response({"data": [{"b64_json": self.encoded_image}]})

    @staticmethod
    def response(body, status=200):
        return Mock(status_code=status, ok=status < 400, json=Mock(return_value=body))

    def test_generation_for_each_official_model_and_metadata(self):
        for model in OPENAI_IMAGE_MODELS:
            with self.subTest(model=model):
                self.params.model_name = model
                text, paths = call_openai_images("  openai-key  ", self.params, [], [])
                args, kwargs = self.mock_post.call_args
                self.assertEqual(args[0], "https://api.openai.com/v1/images/generations")
                self.assertEqual(kwargs["headers"]["Authorization"], "Bearer openai-key")
                self.assertEqual(kwargs["json"]["model"], model)
                self.assertEqual(kwargs["json"]["size"], "2048x1152")
                self.assertEqual(set(kwargs["json"]), {"model", "prompt", "size", "n", "output_format"})
                saved, raw = read_png_parameters(paths[0])
                self.assertEqual(saved.model_name, model)
                self.assertEqual(saved.extra["openai_size"], "2048x1152")
                self.assertIn(model, text)
                self.assertNotIn("openai-key", raw)
                self.assertNotIn("openai-key", Path("last_params.json").read_text())
                self.assertEqual(load_last_params().model_name, model)

    def test_references_use_multipart_edits_and_include_history(self):
        Image.new("RGB", (24, 24), "red").save("input.bmp")
        Image.new("RGB", (24, 24), "blue").save("previous.png")
        history = [{"role": "user", "text": "Draw a bird", "images": ["input.bmp"]},
                   {"role": "model", "text": "Done", "images": ["previous.png"]}]
        self.params.system_instruction = "Keep the style"
        call_openai_images("key", self.params, history, ["input.bmp"])
        args, kwargs = self.mock_post.call_args
        self.assertTrue(args[0].endswith("/images/edits"))
        self.assertNotIn("json", kwargs)
        self.assertEqual(len(kwargs["files"]), 2)
        for name, (filename, data, mime) in kwargs["files"]:
            self.assertEqual(name, "image[]")
            self.assertEqual(mime, "image/png")
            self.assertEqual(Image.open(io.BytesIO(data)).format, "PNG")
        for text in ("Keep the style", "User: Draw a bird", "Assistant: Done", "A blue bird"):
            self.assertIn(text, kwargs["data"]["prompt"])

    def test_environment_key_and_explicit_override(self):
        os.environ["OPENAI_API_KEY"] = "env-key"
        call_openai_images("", self.params, [], [])
        self.assertEqual(self.mock_post.call_args.kwargs["headers"]["Authorization"], "Bearer env-key")
        call_openai_images("override-key", self.params, [], [])
        self.assertEqual(self.mock_post.call_args.kwargs["headers"]["Authorization"], "Bearer override-key")

    def test_missing_key_never_uses_google_credentials(self):
        with self.assertRaisesRegex(RuntimeError, "OpenAI API Key"):
            call_openai_images(" ", self.params, [], [])
        self.mock_post.assert_not_called()

    def test_all_ui_sizes_satisfy_api_limits(self):
        for aspect in ASPECT_RATIO_OPTIONS + ["1:3", "3:1"]:
            for size in ("1K", "2K", "4K"):
                ratio = aspect.split()[0]
                a, b = map(int, ratio.split(":"))
                if max(a, b) / min(a, b) > 3:
                    with self.assertRaises(ValueError):
                        openai_image_size(aspect, size)
                    continue
                with self.subTest(aspect=aspect, size=size):
                    width, height = map(int, openai_image_size(aspect, size).split("x"))
                    self.assertEqual(width % 16, 0)
                    self.assertEqual(height % 16, 0)
                    self.assertLessEqual(max(width, height), 3840)
                    self.assertLessEqual(max(width, height) / min(width, height), 3)
                    self.assertTrue(655360 <= width * height <= 8294400)
                    self.assertAlmostEqual(width / height, a / b, delta=0.12)
        self.assertEqual(openai_image_size("16:9", "4K"), "3840x2160")
        self.assertEqual(openai_image_size("1:1", "4K"), "2880x2880")
        self.assertEqual(openai_image_size("9:16", "4K"), "2160x3840")

    def test_bad_inputs_fail_before_network_request(self):
        for refs, prompt, aspect in [(["missing.png"], "bird", "16:9"),
                                     ([str(i) for i in range(17)], "bird", "16:9"),
                                     ([], "x" * 32001, "16:9"), ([], "bird", "8:1")]:
            with self.subTest(aspect=aspect, refs=len(refs), prompt_length=len(prompt)):
                self.params.prompt, self.params.aspect_ratio = prompt, aspect
                with self.assertRaises(ValueError):
                    call_openai_images("key", self.params, [], refs)
        self.mock_post.assert_not_called()

    def test_error_messages_are_useful_and_redact_credentials(self):
        for status in (401, 403, 429, 500, 503):
            self.mock_post.return_value = self.response({"error": {"message": "Invalid secret-key"}}, status)
            with self.assertRaises(RuntimeError) as raised:
                call_openai_images("secret-key", self.params, [], [])
            self.assertIn(f"HTTP {status}", str(raised.exception))
            self.assertNotIn("secret-key", str(raised.exception))
        self.assertFalse(Path("last_params.json").exists())

    def test_empty_and_invalid_image_responses_fail(self):
        for body in ({"data": []}, {"data": [{}]}, {"data": [{"b64_json": "!not base64"}]},
                     {"data": [{"b64_json": base64.b64encode(b"not an image").decode()}]}, []):
            with self.subTest(body=body):
                self.mock_post.return_value = self.response(body)
                with self.assertRaises(RuntimeError):
                    call_openai_images("key", self.params, [], [])
        self.assertFalse(Path("last_params.json").exists())

    def test_non_json_and_network_failures(self):
        self.mock_post.return_value.json.side_effect = ValueError("not JSON")
        with self.assertRaisesRegex(RuntimeError, "非 JSON"):
            call_openai_images("key", self.params, [], [])
        for error, expected in [(requests.Timeout(), "timed out"), (requests.ConnectionError(), "connection")]:
            self.mock_post.side_effect = error
            with self.assertRaisesRegex(RuntimeError, expected):
                call_openai_images("key", self.params, [], [])

    def test_disable_png_parameters(self):
        self.params.save_png_parameters = False
        _, paths = call_openai_images("key", self.params, [], [])
        with self.assertRaisesRegex(ValueError, "不包含生成参数"):
            read_png_parameters(paths[0])

    def test_service_routes_providers_and_releases_semaphore_after_error(self):
        service = GenerationService()
        with patch("nbp.generation.call_openai_images", side_effect=RuntimeError("failed")) as openai, \
                patch("nbp.generation.call_gemini_vertex", return_value=("gemini", [])) as gemini:
            with self.assertRaises(RuntimeError):
                service.generate("google", self.params, openai_api_key="openai")
            openai.assert_called_once_with("openai", self.params, [], [])
            gemini.assert_not_called()
            self.assertEqual(service._active, 0)
            self.params.model_name = "gemini-3-pro-image-preview"
            self.assertEqual(service.generate("google", self.params, openai_api_key="openai"), ("gemini", []))
            gemini.assert_called_once_with("google", self.params, [], [])

    def test_queue_retains_key_per_group_without_exporting_it(self):
        service = GenerationService()
        queue = QueueService(service)
        for key in ("first-key", "second-key"):
            queue.submit_group("bird", [], 1, "Parameters Only", self.params, {}, "google", openai_api_key=key)
        with patch.object(service, "generate", return_value=("ok", [])) as generate:
            for group, key in zip(queue._groups, ("first-key", "second-key")):
                queue._run_item(group, group["items"][0])
                self.assertEqual(generate.call_args.kwargs, {"openai_api_key": key})
                self.assertEqual(group["items"][0]["status"], "completed")
                self.assertNotIn(key, json.dumps(group["base_params"].public_dict()))

    def test_file_credentials_and_environment_precedence(self):
        Path("OPENAI_API_KEY.txt").write_text("\ufeff file-key\n", encoding="utf-8")
        load_openai_api_key_from_file()
        self.assertEqual(os.environ["OPENAI_API_KEY"], "file-key")
        os.environ["OPENAI_API_KEY"] = "env-key"
        load_openai_api_key_from_file()
        self.assertEqual(os.environ["OPENAI_API_KEY"], "env-key")

    def test_snapshots_route_to_openai(self):
        for model in OPENAI_IMAGE_MODELS:
            self.assertTrue(is_openai_image_model(model))
            self.assertTrue(is_openai_image_model(model + "-2026-09-08"))
        self.assertFalse(is_openai_image_model("gemini-3-pro-image-preview"))


if __name__ == "__main__":
    unittest.main()
