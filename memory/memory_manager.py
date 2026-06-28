from __future__ import annotations

import json
from datetime import datetime
from threading import Lock

from core.state_paths import atomic_write_json, memory_file, read_json

MEMORY_PATH = memory_file("long_term.json")
MEMORY_MAX_CHARS = 5000
MAX_VALUE_LENGTH = 380
_lock = Lock()


def _empty_memory() -> dict:
    return {
        "identity": {},
        "preferences": {},
        "projects": {},
        "research": {},
        "relationships": {},
        "wishes": {},
        "notes": {},
    }


def load_memory() -> dict:
    with _lock:
        data = read_json(MEMORY_PATH, {})
        if not isinstance(data, dict):
            return _empty_memory()
        base = _empty_memory()
        for key, value in data.items():
            if isinstance(value, dict):
                base[key] = value
        return base


def _all_entries(memory: dict) -> list[tuple[str, str, dict]]:
    entries = []
    for category, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if isinstance(entry, dict) and "value" in entry:
                entries.append((category, key, entry))
    return entries


def _trim_to_limit(memory: dict) -> dict:
    while len(json.dumps(memory, ensure_ascii=False)) > MEMORY_MAX_CHARS:
        entries = _all_entries(memory)
        if not entries:
            break
        entries.sort(key=lambda item: item[2].get("updated", "0000-00-00"))
        category, key, _ = entries[0]
        memory.get(category, {}).pop(key, None)
    return memory


def save_memory(memory: dict) -> None:
    if not isinstance(memory, dict):
        return
    with _lock:
        atomic_write_json(MEMORY_PATH, _trim_to_limit(memory), indent=2, ensure_ascii=False)


def _truncate(value: object) -> str:
    text = str(value if value is not None else "").strip()
    if len(text) > MAX_VALUE_LENGTH:
        return text[:MAX_VALUE_LENGTH].rstrip() + "..."
    return text


def update_memory(memory_update: dict) -> dict:
    memory = load_memory()
    if not isinstance(memory_update, dict):
        return memory

    changed = False
    for category, items in memory_update.items():
        category = str(category or "notes").strip() or "notes"
        if category not in memory or not isinstance(memory[category], dict):
            memory[category] = {}
        if not isinstance(items, dict):
            continue
        for key, value in items.items():
            key = str(key or "").strip()
            if not key:
                continue
            if isinstance(value, dict):
                value = value.get("value", "")
            text = _truncate(value)
            if not text:
                continue
            memory[category][key] = {
                "value": text,
                "updated": datetime.now().strftime("%Y-%m-%d"),
            }
            changed = True

    if changed:
        save_memory(memory)
    return memory


def format_memory_for_prompt(memory: dict | None = None) -> str:
    memory = memory if isinstance(memory, dict) else load_memory()
    lines: list[str] = []
    labels = {
        "identity": "Identity",
        "preferences": "Preferences",
        "projects": "Projects",
        "research": "Research memory",
        "relationships": "People",
        "wishes": "Plans/Wishes",
        "notes": "Notes",
    }
    for category, title in labels.items():
        items = memory.get(category, {})
        if not isinstance(items, dict) or not items:
            continue
        lines.append(f"{title}:")
        for key, entry in list(items.items())[:12]:
            value = entry.get("value") if isinstance(entry, dict) else entry
            if value:
                lines.append(f"- {str(key).replace('_', ' ').title()}: {value}")

    if not lines:
        return ""
    text = "[COSMIC CLOUD MEMORY]\n" + "\n".join(lines)
    if len(text) > 2200:
        return text[:2200] + "..."
    return text


def remember(key: str, value: str, category: str = "notes") -> str:
    update_memory({category: {key: {"value": value}}})
    return f"Remembered: {category}/{key}"


def forget(key: str, category: str = "notes") -> str:
    memory = load_memory()
    if isinstance(memory.get(category), dict):
        memory[category].pop(key, None)
        save_memory(memory)
    return f"Forgot: {category}/{key}"
