from __future__ import annotations

# COSMIC_PERSONAL_MASTER_STATE_PATHS

import json
import re
import sys
from pathlib import Path
from typing import Any

from core.state_paths import config_file, read_json, atomic_write_json


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()
CONFIG_PATH = config_file("autonomy.json")

LEVELS = {"low", "balanced", "high"}

DEFAULT_CONFIG: dict[str, Any] = {
    "version": 2,
    "level": "balanced",
    "allow_background_research": True,
    "allow_multistep_tasks": True,
    "allow_memory_updates": True,
    "progress_updates": True,
    "protected_actions_require_confirmation": True,
    "allow_protected_actions": False,
    "research_default_depth": "standard",
    "max_background_tasks": 3,
}

LEVEL_DESCRIPTIONS = {
    "low": "Careful mode: COSMIC asks before complex background work.",
    "balanced": "Recommended Mark 5 mode: safe autonomy, progress updates, and protected-action brakes.",
    "high": "Active mode: COSMIC takes more initiative on safe tasks; destructive/external actions stay protected.",
}

PROTECTED_TOOL_REASONS = {
    "shutdown_cosmic": "shutting down COSMIC",
    "send_message": "sending messages to other people",
}

PROTECTED_FILE_ACTIONS = {"delete", "remove", "move", "rename", "overwrite", "format", "clear", "wipe"}
PROTECTED_WORKFLOW_ACTIONS = {"delete", "disable"}
PROTECTED_SYSTEM_WORDS = {
    "shutdown", "restart", "power", "sleep", "hibernate", "logoff", "signout",
    "uninstall", "delete", "remove", "factory", "format", "firewall", "registry",
}


def _merge_defaults(data: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = dict(DEFAULT_CONFIG)
    if isinstance(data, dict):
        merged.update(data)
    level = str(merged.get("level", "balanced")).lower()
    merged["level"] = level if level in LEVELS else "balanced"
    depth = str(merged.get("research_default_depth", "standard")).lower()
    merged["research_default_depth"] = depth if depth in {"quick", "standard", "deep"} else "standard"
    try:
        merged["max_background_tasks"] = max(1, min(6, int(merged.get("max_background_tasks", 3))))
    except Exception:
        merged["max_background_tasks"] = 3
    return merged


def load_autonomy_config() -> dict[str, Any]:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    return _merge_defaults(data if isinstance(data, dict) else {})


def save_autonomy_config(config: dict[str, Any]) -> dict[str, Any]:
    clean = _merge_defaults(config)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(CONFIG_PATH, clean, indent=2)
    return clean


def update_autonomy_config(updates: dict[str, Any]) -> dict[str, Any]:
    config = load_autonomy_config()
    for key, value in (updates or {}).items():
        if key == "level":
            value = str(value).lower().strip()
            if value not in LEVELS:
                raise ValueError("Autonomy level must be low, balanced, or high.")
        if key == "research_default_depth":
            value = str(value).lower().strip()
            if value not in {"quick", "standard", "deep"}:
                raise ValueError("Research depth must be quick, standard, or deep.")
        if key in DEFAULT_CONFIG:
            config[key] = value
    return save_autonomy_config(config)


def _action(parameters: dict[str, Any]) -> str:
    for key in ("action", "operation", "intent", "command"):
        if key in parameters:
            return str(parameters.get(key, "")).strip().lower()
    return ""


def _contains_protected_system_word(parameters: dict[str, Any]) -> str:
    joined = " ".join(str(v).lower() for v in parameters.values() if not isinstance(v, (dict, list)))
    for word in sorted(PROTECTED_SYSTEM_WORDS):
        if re.search(rf"\b{re.escape(word)}\b", joined):
            return word
    return ""


def _protected_reason(tool_name: str, parameters: dict[str, Any]) -> str:
    tool = str(tool_name or "").strip()
    params = parameters or {}
    action = _action(params)

    if tool in PROTECTED_TOOL_REASONS:
        return PROTECTED_TOOL_REASONS[tool]
    if tool == "file_controller" and action in PROTECTED_FILE_ACTIONS:
        return f"{action} files"
    if tool == "workflow_manager" and action in PROTECTED_WORKFLOW_ACTIONS:
        return f"{action} workflows"
    if tool in {"computer_settings", "computer_control", "desktop_control"}:
        risky_word = _contains_protected_system_word(params)
        if risky_word:
            return f"system-level action containing '{risky_word}'"
    if tool in {"code_helper", "dev_agent"} and action in {"delete", "remove", "overwrite"}:
        return f"{action} code/files"
    return ""


def guard_tool_call(tool_name: str, parameters: dict[str, Any] | None = None) -> tuple[bool, str]:
    config = load_autonomy_config()
    params = parameters or {}
    tool = str(tool_name or "").strip()
    action = _action(params)

    if tool in {"autonomy_settings", "voice_settings"}:
        return True, "Settings tools are allowed."

    if tool == "save_memory" and not bool(config.get("allow_memory_updates", True)):
        return False, "Memory updates are disabled in COSMIC autonomy settings."

    if tool == "research_agent" and action == "start" and not bool(config.get("allow_background_research", True)):
        return False, "Background research is disabled in COSMIC autonomy settings."

    if tool == "agent_task" and not bool(config.get("allow_multistep_tasks", True)):
        return False, "Multi-step autonomous tasks are disabled in COSMIC autonomy settings."

    reason = _protected_reason(tool, params)
    if reason and bool(config.get("protected_actions_require_confirmation", True)):
        if not bool(config.get("allow_protected_actions", False)):
            return (
                False,
                "Autonomy Guard paused this action because it involves "
                f"{reason}. Ask Dhaval for explicit confirmation before proceeding."
            )

    if config.get("level") == "low" and tool in {"agent_task", "dev_agent"}:
        return False, "Low autonomy mode pauses complex background work. Ask Dhaval before continuing."

    return True, "Allowed by COSMIC autonomy settings."


def format_autonomy_for_prompt() -> str:
    config = load_autonomy_config()
    level = config.get("level", "balanced")
    return f"""
AUTONOMY GOVERNOR:
- Current autonomy level: {level.upper()}.
- {LEVEL_DESCRIPTIONS.get(level, LEVEL_DESCRIPTIONS["balanced"])}
- Work independently on safe information tasks: research, summarization, planning, workflow inspection, and progress reporting.
- For broad safe tasks, create a plan internally and post short progress updates.
- Use research_agent for autonomous research missions; save useful findings when memory updates are enabled.
- Protected actions require explicit confirmation: deleting/moving files, sending messages to other people, shutdown/restart/power actions, uninstall/system destructive changes, and deleting workflows.
- If a protected action is needed, ask Dhaval first instead of calling the tool.
""".strip()


def handle_autonomy_settings(parameters: dict[str, Any] | None = None) -> str:
    params = parameters or {}
    action = str(params.get("action", "status")).strip().lower()

    if action in {"set", "update"}:
        updates: dict[str, Any] = {}
        for key in DEFAULT_CONFIG:
            if key in params:
                updates[key] = params[key]
        config = update_autonomy_config(updates)
        return _format_status(config, prefix="Autonomy settings updated.")

    return _format_status(load_autonomy_config(), prefix="COSMIC autonomy status.")


def _format_status(config: dict[str, Any], prefix: str = "COSMIC autonomy status.") -> str:
    level = config.get("level", "balanced")
    lines = [
        prefix,
        f"Level: {level}",
        LEVEL_DESCRIPTIONS.get(level, LEVEL_DESCRIPTIONS["balanced"]),
        f"Background research: {'on' if config.get('allow_background_research') else 'off'}",
        f"Multi-step tasks: {'on' if config.get('allow_multistep_tasks') else 'off'}",
        f"Memory updates: {'on' if config.get('allow_memory_updates') else 'off'}",
        f"Default research depth: {config.get('research_default_depth', 'standard')}",
        f"Protected actions require confirmation: {'yes' if config.get('protected_actions_require_confirmation') else 'no'}",
    ]
    return "\n".join(lines)
