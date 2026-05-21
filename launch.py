from __future__ import annotations

import os
import shutil
from pathlib import Path

from nbp.config import find_free_port, load_google_api_key_from_file
from nbp.ui import create_gradio_app


def patch_gradio_node_lookup() -> None:
    """Avoid Gradio's Windows `where node` probe leaking an INFO line to stderr."""
    def quiet_get_node_path():
        env_node_path = os.environ.get("GRADIO_NODE_PATH")
        if env_node_path:
            return env_node_path
        which_node_path = shutil.which("node")
        if which_node_path:
            return which_node_path
        for node_path in (
            r"C:\Program Files\nodejs\node.exe",
            r"C:\Program Files (x86)\nodejs\node.exe",
            "/usr/bin/node",
            "/usr/local/bin/node",
        ):
            if os.path.exists(node_path):
                return node_path
        return None

    try:
        import gradio.blocks as gradio_blocks
        import gradio.routes as gradio_routes
        import gradio.utils as gradio_utils

        gradio_utils.get_node_path = quiet_get_node_path
        gradio_blocks.get_node_path = quiet_get_node_path
        gradio_routes.get_node_path = quiet_get_node_path
    except Exception as exc:
        print(f"[banana startup] failed to patch Gradio node lookup: {exc}")


def main() -> None:
    app_root = Path(__file__).resolve().parent
    os.chdir(app_root)
    for dirname in ("outputs", "exports", "plugins"):
        (app_root / dirname).mkdir(exist_ok=True)
    allowed_paths = [str((app_root / name).resolve()) for name in (".", "outputs", "exports")]
    print(f"[banana] app root: {app_root}")
    print(f"[banana] cwd: {Path.cwd()}")
    print(f"[banana] allowed_paths: {allowed_paths}")

    load_google_api_key_from_file()
    patch_gradio_node_lookup()
    demo = create_gradio_app()
    port = find_free_port(7860, 7880, host="127.0.0.1")
    demo.queue(default_concurrency_limit=16)
    demo.launch(
        server_name="127.0.0.1",
        server_port=port,
        allowed_paths=allowed_paths,
    )
    print(f"[banana] Gradio running on http://127.0.0.1:{port}")


if __name__ == "__main__":
    main()
