from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import requests

from . import APP_VERSION
from .paths import CONFIG_DIR, ROOT, ensure_external_resources


APP_SETTINGS_PATH = CONFIG_DIR / "app_settings.json"
DEFAULT_UPDATE_SETTINGS = {
    "enabled": True,
    "github_owner": "Stormmurdock26",
    "github_repo": "Competitors-analysis-",
    "repository_url": "https://github.com/Stormmurdock26/Competitors-analysis-.git",
    "installer_asset_contains": "installer",
}


@dataclass
class UpdateStatus:
    enabled: bool
    update_available: bool
    current_version: str
    latest_version: str
    release_url: str
    message: str
    latest_ref: str = ""


def load_app_settings(path: Path = APP_SETTINGS_PATH) -> dict:
    ensure_external_resources()
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    updates = data.setdefault("updates", {})
    changed = False
    if not updates.get("github_owner") and not updates.get("github_repo"):
        updates.update(DEFAULT_UPDATE_SETTINGS)
        changed = True
    for key, value in DEFAULT_UPDATE_SETTINGS.items():
        if key not in updates:
            updates[key] = value
            changed = True
    if changed:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def check_for_updates(settings_path: Path = APP_SETTINGS_PATH) -> UpdateStatus:
    settings = load_app_settings(settings_path).get("updates", {})
    enabled = bool(settings.get("enabled", False))
    owner = str(settings.get("github_owner", "")).strip()
    repo = str(settings.get("github_repo", "")).strip()
    repo_url = str(settings.get("repository_url", "")).strip()
    if not enabled:
        return UpdateStatus(False, False, APP_VERSION, "", "", "Update checks are disabled.")
    if not owner or not repo:
        return UpdateStatus(True, False, APP_VERSION, "", "", "GitHub update repository is not configured.")

    latest, release_url, source, latest_ref = latest_published_version(owner, repo)
    if not latest:
        location = repo_url or f"https://github.com/{owner}/{repo}"
        return UpdateStatus(
            True,
            False,
            APP_VERSION,
            "",
            location,
            "No GitHub release or version tag has been published yet.",
        )
    available = compare_versions(latest, APP_VERSION) > 0
    message = f"Version {latest} is available from GitHub {source}." if available else "Application is up to date."
    return UpdateStatus(True, available, APP_VERSION, latest, release_url, message, latest_ref)


def latest_published_version(owner: str, repo: str) -> tuple[str, str, str, str]:
    release_response = github_get(f"https://api.github.com/repos/{owner}/{repo}/releases/latest")
    if release_response.status_code == 200:
        release = release_response.json()
        tag_name = str(release.get("tag_name", ""))
        return tag_name.lstrip("v"), str(release.get("html_url", "")), "release", tag_name
    if release_response.status_code not in {404, 403}:
        release_response.raise_for_status()

    tags_response = github_get(f"https://api.github.com/repos/{owner}/{repo}/tags")
    if tags_response.status_code == 200:
        tags = tags_response.json()
        if isinstance(tags, list) and tags:
            tag = tags[0]
            tag_name = str(tag.get("name", ""))
            return tag_name.lstrip("v"), f"https://github.com/{owner}/{repo}/releases/tag/{tag_name}", "tag", tag_name
        return "", "", "", ""
    if tags_response.status_code == 404:
        return "", "", "", ""
    tags_response.raise_for_status()
    return "", "", "", ""


def github_get(url: str) -> requests.Response:
    return requests.get(url, headers={"Accept": "application/vnd.github+json"}, timeout=15)


def start_self_update(status: UpdateStatus) -> Path:
    repo_root = find_repo_root()
    exe_path = repo_root / "dist" / "Storm Competitor Analysis.exe"
    if not exe_path.exists():
        exe_path = Path(sys.executable).resolve()
    if not (repo_root / ".git").exists():
        raise RuntimeError(f"Cannot update because no git repo was found from {ROOT}.")
    if not (repo_root / "scripts" / "build_exe.ps1").exists():
        raise RuntimeError(f"Cannot update because build script is missing from {repo_root}.")

    log_path = repo_root / "storm_update.log"
    bootstrap_log_path = repo_root / "storm_update_bootstrap.log"
    script_path = repo_root / "storm_update_runner.ps1"
    script_path.write_text(update_runner_script(), encoding="utf-8")
    log_path.write_text(f"Updater launch requested for {status.latest_ref or 'current branch'}.\n", encoding="utf-8")
    bootstrap_log_path.write_text("Updater process launch output.\n", encoding="utf-8")
    powershell_exe = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not powershell_exe.exists():
        powershell_exe = Path("powershell")
    command = [
        str(powershell_exe),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-RepoRoot",
        str(repo_root),
        "-ExePath",
        str(exe_path),
        "-ParentPid",
        str(os.getpid()),
        "-LogPath",
        str(log_path),
    ]
    if status.latest_ref:
        command.extend(["-TargetRef", status.latest_ref])
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    with bootstrap_log_path.open("a", encoding="utf-8") as log_file:
        subprocess.Popen(
            command,
            cwd=str(repo_root),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
    return log_path


def find_repo_root() -> Path:
    candidates = [ROOT, ROOT.parent, *ROOT.parents]
    for candidate in candidates:
        if (candidate / ".git").exists() and (candidate / "pyproject.toml").exists():
            return candidate
    raise RuntimeError(f"No git-backed project root found from {ROOT}.")


def update_runner_script() -> str:
    return r'''param(
    [Parameter(Mandatory=$true)][string]$RepoRoot,
    [Parameter(Mandatory=$true)][string]$ExePath,
    [Parameter(Mandatory=$true)][int]$ParentPid,
    [AllowEmptyString()][string]$TargetRef = "",
    [Parameter(Mandatory=$true)][string]$LogPath
)
$ErrorActionPreference = "Stop"
function Write-UpdateLog([string]$Message) {
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogPath -Value "[$stamp] $Message"
}
try {
    Write-UpdateLog "Waiting for application process $ParentPid to exit."
    Wait-Process -Id $ParentPid -ErrorAction SilentlyContinue
    Set-Location $RepoRoot
    Write-UpdateLog "Fetching updates from origin."
    git fetch --tags origin *>> $LogPath
    if ($TargetRef) {
        Write-UpdateLog "Checking out $TargetRef."
        git checkout $TargetRef *>> $LogPath
    } else {
        Write-UpdateLog "Pulling current branch."
        git pull --ff-only origin *>> $LogPath
    }
    Write-UpdateLog "Rebuilding executable."
    $buildScript = Join-Path $RepoRoot "scripts\build_exe.ps1"
    $powershellExe = Join-Path $PSHOME "powershell.exe"
    $buildCommand = '"' + $powershellExe + '" -NoProfile -ExecutionPolicy Bypass -File "' + $buildScript + '" >> "' + $LogPath + '" 2>&1'
    cmd.exe /d /s /c $buildCommand
    $buildExitCode = $LASTEXITCODE
    if ($buildExitCode -ne 0) {
        throw "Build failed with exit code $buildExitCode."
    }
    $versionMarker = Join-Path $RepoRoot "dist\app_version.txt"
    if (Test-Path $versionMarker) {
        Write-UpdateLog ("Built app version marker: " + (Get-Content $versionMarker -Raw).Trim())
    } else {
        Write-UpdateLog "Built app version marker missing."
    }
    Write-UpdateLog "Launching rebuilt application."
    Start-Process -FilePath $ExePath
    Write-UpdateLog "Update completed."
} catch {
    Write-UpdateLog ("Update failed: " + $_.Exception.Message)
    throw
}
'''


def compare_versions(left: str, right: str) -> int:
    left_parts = version_parts(left)
    right_parts = version_parts(right)
    max_len = max(len(left_parts), len(right_parts))
    left_parts.extend([0] * (max_len - len(left_parts)))
    right_parts.extend([0] * (max_len - len(right_parts)))
    if left_parts == right_parts:
        return 0
    return 1 if left_parts > right_parts else -1


def version_parts(value: str) -> list[int]:
    parts = []
    for token in value.replace("-", ".").split("."):
        try:
            parts.append(int(token))
        except ValueError:
            parts.append(0)
    return parts
