from __future__ import annotations

import copy
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime
from typing import Any

from .export import log_queue_group_to_md
from .generation import GenerationService
from .params import GenerationParams


TERMINAL_STATUSES = {"completed", "failed", "partial", "skipped", "canceled"}
STATUS_LABELS = {
    "pending": "等待中",
    "running": "运行中",
    "completed": "已完成",
    "failed": "失败",
    "partial": "部分完成",
    "skipped": "已跳过",
    "canceled": "已取消",
}

STRATEGY_ALIASES = {
    "随机种子扰动": "Random Seed Salt",
    "风格轮换": "Simple Style Rotation",
    "仅参数变化": "Parameters Only",
}


TRANSIENT_ERROR_MARKERS = (
    "429",
    "RESOURCE_EXHAUSTED",
    "SSL",
    "WRONG_VERSION_NUMBER",
    "UNAVAILABLE",
    "DEADLINE_EXCEEDED",
    "Connection",
    "connection",
    "timeout",
    "timed out",
    "HTTP 500",
    "HTTP 502",
    "HTTP 503",
    "HTTP 504",
)


def parse_param_array(input_str: str, target_length: int, default_val: Any, converter=str) -> list[Any]:
    if not input_str or not str(input_str).strip():
        return [default_val] * target_length
    values = []
    for raw in str(input_str).split(","):
        raw = raw.strip()
        try:
            values.append(converter(raw))
        except Exception:
            values.append(default_val)
    if not values:
        return [default_val] * target_length
    if len(values) >= target_length:
        return values[:target_length]
    return values + [values[-1]] * (target_length - len(values))


def apply_strategy(prompt: str, strategy: str, index: int) -> tuple[str, dict[str, Any]]:
    strategy = STRATEGY_ALIASES.get(strategy, strategy)
    if strategy == "Random Seed Salt":
        seed = random.randint(10000, 99999)
        return f"{prompt}\n(Random Seed: {seed}, Batch: {index + 1})", {"seed": seed}
    if strategy == "Simple Style Rotation":
        modifiers = ["Cinematic Lighting", "Wide Angle", "Close-up", "Cyberpunk Style", "Watercolor"]
        modifier = modifiers[index % len(modifiers)]
        return f"{prompt}, {modifier}", {"modifier": modifier}
    return prompt, {}


class QueueService:
    def __init__(self, generation_service: GenerationService, request_timeout: int = 900) -> None:
        self.generation_service = generation_service
        self.request_timeout = request_timeout
        self._groups: list[dict[str, Any]] = []
        self._lock = threading.RLock()
        self._runners: list[threading.Thread] = []
        self._paused = False
        self._stop_current = False

    def submit_group(
        self,
        prompt: str,
        ref_images: list[str],
        batch_count: int,
        strategy: str,
        base_params: GenerationParams,
        param_arrays: dict[str, str],
        api_key: str,
        openai_api_key: str = "",
    ) -> None:
        batch_count = max(1, int(batch_count or 1))
        items = []
        aspects = parse_param_array(param_arrays.get("aspect_ratio", ""), batch_count, base_params.aspect_ratio)
        sizes = parse_param_array(param_arrays.get("image_size", ""), batch_count, base_params.image_size)
        searches = parse_param_array(param_arrays.get("enable_search", ""), batch_count, int(base_params.enable_search), int)
        temps = parse_param_array(param_arrays.get("temperature", ""), batch_count, base_params.temperature, float)
        top_ps = parse_param_array(param_arrays.get("top_p", ""), batch_count, base_params.top_p, float)
        top_ks = parse_param_array(param_arrays.get("top_k", ""), batch_count, base_params.top_k, int)
        tokens = parse_param_array(param_arrays.get("max_output_tokens", ""), batch_count, base_params.max_output_tokens, int)
        for idx in range(batch_count):
            item_prompt, extra = apply_strategy(prompt, strategy, idx)
            params = GenerationParams.from_dict(base_params.public_dict())
            params.prompt = item_prompt
            params.aspect_ratio = aspects[idx]
            params.image_size = sizes[idx]
            params.enable_search = bool(searches[idx])
            params.temperature = temps[idx]
            params.top_p = top_ps[idx]
            params.top_k = top_ks[idx]
            params.max_output_tokens = tokens[idx]
            params.extra.update(extra)
            params.normalize()
            items.append(
                {
                    "index": idx,
                    "status": "pending",
                    "params": params,
                    "images": [],
                    "text": "",
                    "error": "",
                    "started_at": "",
                    "finished_at": "",
                }
            )
        group = {
            "id": datetime.now().strftime("%Y%m%d%H%M%S"),
            "prompt": prompt,
            "status": "pending",
            "done_count": 0,
            "total_count": batch_count,
            "result_count": 0,
            "error_msg": "",
            "strategy": strategy,
            "ref_images": list(ref_images or []),
            "api_key": api_key,
            "openai_api_key": openai_api_key,
            "base_params": copy.deepcopy(base_params),
            "items": items,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "started_at": "",
            "finished_at": "",
            "skip_item_requested": False,
            "skip_group_requested": False,
            "abort_requested": False,
        }
        with self._lock:
            existing_ids = {queued_group["id"] for queued_group in self._groups}
            base_id = group["id"]
            suffix = 2
            while group["id"] in existing_ids:
                group["id"] = f"{base_id}_{suffix}"
                suffix += 1
            self._groups.append(group)

    def ensure_running(self) -> None:
        with self._lock:
            self._runners = [runner for runner in self._runners if runner.is_alive()]
            target_count = self.generation_service.max_concurrency
            while len(self._runners) < target_count:
                runner = threading.Thread(target=self._run_loop, daemon=True)
                self._runners.append(runner)
                runner.start()

    def set_concurrency(self, value: int) -> None:
        self.generation_service.set_max_concurrency(value)

    def move_group(self, group_id: str, direction: int) -> None:
        with self._lock:
            idx = self._find_index(group_id)
            if idx is None or self._groups[idx]["status"] != "pending":
                return
            new_idx = idx + direction
            if new_idx < 0 or new_idx >= len(self._groups):
                return
            if self._groups[new_idx]["status"] != "pending":
                return
            self._groups[idx], self._groups[new_idx] = self._groups[new_idx], self._groups[idx]

    def delete_group(self, group_id: str) -> None:
        with self._lock:
            idx = self._find_index(group_id)
            if idx is None:
                return
            if self._groups[idx]["status"] == "running":
                self._groups[idx]["status"] = "canceled"
                self._groups[idx]["error_msg"] = "Canceled while running."
                self._groups[idx]["skip_group_requested"] = True
                return
            self._groups.pop(idx)

    def _target_group(self, group_id: str | None = None) -> dict[str, Any] | None:
        if group_id:
            idx = self._find_index(group_id)
            if idx is not None:
                return self._groups[idx]
        for group in self._groups:
            if group["status"] == "running":
                return group
        return None

    def skip_item(self, group_id: str | None = None) -> None:
        with self._lock:
            group = self._target_group(group_id)
            if group:
                group["skip_item_requested"] = True

    def skip_group(self, group_id: str | None = None) -> None:
        with self._lock:
            group = self._target_group(group_id)
            if group:
                group["skip_group_requested"] = True

    def abort(self) -> None:
        with self._lock:
            self._paused = True
            self._stop_current = True
            for group in self._groups:
                if group["status"] == "running":
                    group["abort_requested"] = True
                    group["skip_group_requested"] = True

    def resume(self) -> None:
        with self._lock:
            self._paused = False
            self._stop_current = False
            for group in self._groups:
                group["abort_requested"] = False
        self.ensure_running()

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._groups)

    def rows(self) -> list[list[Any]]:
        rows = []
        for display_index, group in enumerate(self.snapshot(), start=1):
            rows.append(
                [
                    display_index,
                    STATUS_LABELS.get(group["status"], group["status"]),
                    f"{group['done_count']}/{group['total_count']}",
                    group["result_count"],
                    group["prompt"][:80],
                    group.get("error_msg", ""),
                ]
            )
        return rows

    def group_choices(self) -> list[str]:
        return [str(index) for index, _ in enumerate(self.snapshot(), start=1)]

    def log_text(self) -> str:
        groups = self.snapshot()
        lines = [f"队列状态 @ {datetime.now().strftime('%H:%M:%S')}"]
        for display_index, group in enumerate(groups, start=1):
            lines.append(
                f"[{display_index}] {STATUS_LABELS.get(group['status'], group['status'])} "
                f"{group['done_count']}/{group['total_count']} 结果={group['result_count']} Prompt={group['prompt'][:50]}"
            )
            if group.get("error_msg"):
                lines.append(f"  错误: {group['error_msg']}")
        return "\n".join(lines)

    def gallery_paths(self) -> list[str]:
        paths: list[str] = []
        for group in self.snapshot():
            for item in group.get("items", []):
                for image_path in item.get("images", []):
                    if image_path and os.path.exists(image_path):
                        paths.append(image_path)
        return paths

    def _find_index(self, group_id: str) -> int | None:
        if str(group_id).isdigit():
            idx = int(group_id) - 1
            if 0 <= idx < len(self._groups):
                return idx
        for idx, group in enumerate(self._groups):
            if group["id"] == group_id:
                return idx
        return None

    def _next_group(self) -> dict[str, Any] | None:
        for group in self._groups:
            if group["status"] == "pending":
                return group
        return None

    def _run_loop(self) -> None:
        while True:
            with self._lock:
                if self._paused:
                    return
                group = self._next_group()
                if not group:
                    return
                group["status"] = "running"
                group["started_at"] = datetime.now().isoformat(timespec="seconds")
                self._stop_current = False
                group["skip_item_requested"] = False
                group["skip_group_requested"] = False
                group["abort_requested"] = False
            self._run_group(group)

    def _run_group(self, group: dict[str, Any]) -> None:
        for item in group["items"]:
            with self._lock:
                if group.get("skip_group_requested") or group.get("abort_requested") or group["status"] == "canceled":
                    item["status"] = "skipped"
                    continue
                item["status"] = "running"
                item["started_at"] = datetime.now().isoformat(timespec="seconds")
            self._run_item(group, item)
            with self._lock:
                item["finished_at"] = datetime.now().isoformat(timespec="seconds")
                group["done_count"] = len([x for x in group["items"] if x["status"] in TERMINAL_STATUSES])
                group["result_count"] = sum(len(x.get("images", [])) for x in group["items"])
            time.sleep(0.2)
        with self._lock:
            statuses = [item["status"] for item in group["items"]]
            if group["status"] == "canceled" or group.get("abort_requested"):
                group["status"] = "canceled"
                group["error_msg"] = group.get("error_msg") or "Aborted by user."
            elif all(status == "completed" for status in statuses):
                group["status"] = "completed"
            elif all(status in {"skipped", "canceled"} for status in statuses):
                group["status"] = "skipped"
            elif any(status == "completed" for status in statuses):
                group["status"] = "partial"
            else:
                group["status"] = "failed"
            failures = [item.get("error") for item in group["items"] if item.get("error")]
            if failures:
                group["error_msg"] = "; ".join(failures[:3])
            group["finished_at"] = datetime.now().isoformat(timespec="seconds")
        try:
            log_queue_group_to_md(group)
        except Exception as exc:
            print(f"[WARN] Failed to export queue group: {exc}")

    def _run_item(self, group: dict[str, Any], item: dict[str, Any]) -> None:
        max_retries = 3
        for attempt in range(max_retries):
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(
                self.generation_service.generate,
                group["api_key"],
                item["params"],
                [],
                group["ref_images"],
                openai_api_key=group.get("openai_api_key", ""),
            )
            start = time.monotonic()
            try:
                while True:
                    with self._lock:
                        should_skip = (
                            group.get("skip_item_requested")
                            or group.get("skip_group_requested")
                            or group.get("abort_requested")
                            or group["status"] == "canceled"
                        )
                    if should_skip:
                        future.cancel()
                        with self._lock:
                            item["status"] = "skipped"
                            item["error"] = "Skipped by user."
                            group["skip_item_requested"] = False
                        return
                    if time.monotonic() - start > self.request_timeout:
                        future.cancel()
                        with self._lock:
                            item["status"] = "failed"
                            item["error"] = f"Request timed out after {self.request_timeout} seconds."
                        return
                    try:
                        text, images = future.result(timeout=1)
                        with self._lock:
                            item["text"] = text
                            item["images"] = images
                            item["status"] = "completed" if images or text else "failed"
                            if item["status"] == "failed":
                                item["error"] = "No output returned."
                        return
                    except TimeoutError:
                        continue
            except Exception as exc:
                err = str(exc)
                if attempt < max_retries - 1 and any(marker in err for marker in TRANSIENT_ERROR_MARKERS):
                    time.sleep(5 * (2 ** attempt))
                    continue
                with self._lock:
                    item["status"] = "failed"
                    item["error"] = err
                return
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
