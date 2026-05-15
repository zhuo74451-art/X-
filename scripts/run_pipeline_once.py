from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run(script_name: str) -> None:
    root = _project_root()
    script_path = root / "scripts" / script_name
    subprocess.run([sys.executable, str(script_path)], cwd=str(root), check=True)


def main() -> None:
    _run("init_db.py")
    _run("import_sample_hot_inputs.py")
    _run("evaluate_hot_input.py")
    _run("generate_hot_draft.py")
    _run("export_review_queue.py")
    print("[run_pipeline_once] ok")


if __name__ == "__main__":
    main()

