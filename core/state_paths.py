from __future__ import annotations

import json
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any


def project_root() -> Path:
    override = os.getenv("COSMIC_PROJECT_ROOT", "").strip()
    if override:
        return Path(override).expanduser()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = project_root()


def state_root() -> Path:
    override = os.getenv("COSMIC_STATE_DIR", "").strip()
    if override:
        root = Path(override).expanduser()
    else:
        local = os.getenv("LOCALAPPDATA")
        root = (Path(local) if local else Path.home() / "AppData" / "Local") / "COSMIC" / "Mark5"
    root.mkdir(parents=True, exist_ok=True)
    return root


STATE_ROOT = state_root()
_MIGRATED = False


_CONFIG_FILES = [
    "api_keys.json",
    "phone_access.json",
    "voice.json",
    "autonomy.json",
    "performance.json",
    "research_tasks.json",
    "ui_tasks.json",
]
_DATA_FILES = ["calendar_events.json", "active_goals.json", "cosmic_calendar_export.ics"]
_MEMORY_FILES = ["long_term.json", "research_knowledge.json"]


def _copy_file_if_missing(src: Path, dst: Path) -> None:
    if dst.exists() or not src.exists() or not src.is_file():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _copy_dir_if_missing(src: Path, dst: Path) -> None:
    if dst.exists() or not src.exists() or not src.is_dir():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)


def ensure_state_ready(project: Path | None = None) -> Path:
    global _MIGRATED
    root = STATE_ROOT
    for folder in ("config", "data", "memory", "logs", "research_reports"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    if _MIGRATED:
        return root
    project = Path(project or PROJECT_ROOT)
    for name in _CONFIG_FILES:
        _copy_file_if_missing(project / "config" / name, root / "config" / name)
    for name in _DATA_FILES:
        _copy_file_if_missing(project / "data" / name, root / "data" / name)
    for name in _MEMORY_FILES:
        _copy_file_if_missing(project / "memory" / name, root / "memory" / name)
    _copy_dir_if_missing(project / "memory" / "research_reports", root / "research_reports")
    _MIGRATED = True
    return root


def state_file(*parts: str) -> Path:
    ensure_state_ready()
    return STATE_ROOT.joinpath(*parts)


def config_file(name: str) -> Path:
    return state_file("config", name)


def data_file(name: str) -> Path:
    return state_file("data", name)


def memory_file(name: str) -> Path:
    return state_file("memory", name)


def log_file(name: str) -> Path:
    return state_file("logs", name)


def research_reports_dir() -> Path:
    return state_file("research_reports")


def read_json(path: Path, fallback: Any) -> Any:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data
    except Exception:
        return fallback


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8", newline: str | None = None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(str(text), encoding=encoding, newline=newline)
    os.replace(tmp, path)


def atomic_write_json(path: Path, data: Any, *, indent: int = 2, ensure_ascii: bool = False) -> None:
    atomic_write_text(path, json.dumps(data, indent=indent, ensure_ascii=ensure_ascii), encoding="utf-8")


def runtime_state_summary() -> dict[str, str]:
    ensure_state_ready()
    return {
        "project_root": str(PROJECT_ROOT),
        "state_root": str(STATE_ROOT),
        "config": str(STATE_ROOT / "config"),
        "data": str(STATE_ROOT / "data"),
        "memory": str(STATE_ROOT / "memory"),
        "logs": str(STATE_ROOT / "logs"),
        "research_reports": str(STATE_ROOT / "research_reports"),
    }
