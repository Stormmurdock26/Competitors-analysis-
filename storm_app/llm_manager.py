from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from .paths import CONFIG_DIR, ensure_external_resources


LOCAL_LLM_CONFIG_PATH = CONFIG_DIR / "local_llm.json"
REQUIRED_MODEL = "gemma4:e4b"
OLLAMA_INSTALL_SCRIPT_URL = "https://ollama.com/install.ps1"


@dataclass
class LLMStatus:
    ollama_path: str
    base_url: str
    model: str
    service_available: bool
    model_available: bool
    message: str


def load_llm_config(path: Path = LOCAL_LLM_CONFIG_PATH) -> dict:
    ensure_external_resources()
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if data.get("model") != REQUIRED_MODEL:
        data["model"] = REQUIRED_MODEL
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def check_llm_status(path: Path = LOCAL_LLM_CONFIG_PATH) -> LLMStatus:
    config = load_llm_config(path)
    base_url = str(config.get("base_url", "http://localhost:11434")).rstrip("/")
    model = REQUIRED_MODEL
    ollama_path = find_ollama()
    if not ollama_path:
        return LLMStatus("", base_url, model, False, False, "LLM missing.")

    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        response.raise_for_status()
    except Exception as exc:
        return LLMStatus(ollama_path, base_url, model, False, False, f"LLM error: {exc}")

    models = response.json().get("models", [])
    model_names = {item.get("name", "") for item in models}
    available = model in model_names
    message = "LLM ready." if available else "LLM missing."
    return LLMStatus(ollama_path, base_url, model, True, available, message)


def install_ollama(progress: Callable[[str], None] | None = None) -> None:
    winget = shutil.which("winget")
    if winget:
        command = [
            winget,
            "install",
            "Ollama.Ollama",
            "--accept-package-agreements",
            "--accept-source-agreements",
        ]
        try:
            run_streamed(command, progress)
            return
        except RuntimeError as exc:
            if progress:
                progress(f"winget install failed: {exc}")
                progress("Trying official Ollama Windows installer script...")
    elif progress:
        progress("winget was not found. Trying official Ollama Windows installer script...")

    install_ollama_from_script(progress)


def install_ollama_from_script(progress: Callable[[str], None] | None = None) -> None:
    powershell = (
        shutil.which("powershell")
        or str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
    )
    command = [
        powershell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        f"irm {OLLAMA_INSTALL_SCRIPT_URL} | iex",
    ]
    run_streamed(command, progress)


def find_ollama() -> str:
    path = shutil.which("ollama")
    if path:
        return path

    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Ollama" / "ollama.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Ollama" / "ollama.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return ""


def start_ollama_service(ollama_path: str, progress: Callable[[str], None] | None = None) -> None:
    if progress:
        progress("Starting local LLM runtime...")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    subprocess.Popen(
        [ollama_path, "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=True,
    )
    time.sleep(3)


def pull_model(model: str, progress: Callable[[str], None] | None = None) -> None:
    ollama = find_ollama()
    if not ollama:
        raise RuntimeError("Ollama is not installed.")
    run_streamed([ollama, "pull", model], progress)


def ensure_model(progress: Callable[[str], None] | None = None) -> LLMStatus:
    status = check_llm_status()
    if not status.ollama_path:
        if progress:
            progress("Installing local LLM runtime...")
        install_ollama(progress)
        status = check_llm_status()
    if not status.service_available:
        if status.ollama_path:
            start_ollama_service(status.ollama_path, progress)
            status = check_llm_status()
    if not status.service_available:
        raise RuntimeError(status.message)
    if not status.model_available:
        if progress:
            progress("Downloading required LLM...")
        pull_model(status.model, progress)
    return check_llm_status()


def run_streamed(command: list[str], progress: Callable[[str], None] | None = None) -> None:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert process.stdout is not None
    for line in process.stdout:
        if progress:
            progress(line.rstrip())
    exit_code = process.wait()
    if exit_code:
        raise RuntimeError(f"Command failed with exit code {exit_code}: {' '.join(command)}")
