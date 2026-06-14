from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from feature_alignment_llm import load_llm_config


def run_command(command: list[str]) -> tuple[int, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
        return result.returncode, (result.stdout or result.stderr).strip()
    except Exception as exc:
        return 1, str(exc)


def main() -> None:
    config = load_llm_config()
    report = {
        "config": {
            "enabled": config.enabled,
            "provider": config.provider,
            "base_url": config.base_url,
            "model": config.model,
            "num_ctx": config.num_ctx,
        },
        "ollama": {
            "installed": bool(shutil.which("ollama")),
            "models": "",
        },
        "gpu": {
            "nvidia_smi_available": bool(shutil.which("nvidia-smi")),
            "devices": "",
        },
    }
    if report["ollama"]["installed"]:
        _, output = run_command(["ollama", "list"])
        report["ollama"]["models"] = output
    if report["gpu"]["nvidia_smi_available"]:
        _, output = run_command(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
        report["gpu"]["devices"] = output

    output_path = Path("scraper_outputs") / "local_llm_environment.json"
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
