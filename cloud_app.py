from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
os.environ.setdefault("COSMIC_CLOUD_MODE", "1")
os.environ.setdefault("COSMIC_PROJECT_ROOT", str(PROJECT_ROOT))
os.environ.setdefault("COSMIC_WEB_HOST", "0.0.0.0")
os.environ.setdefault("COSMIC_WEB_PORT", os.getenv("PORT", "8775"))
if not os.getenv("COSMIC_STATE_DIR"):
    disk = Path("/var/data")
    os.environ["COSMIC_STATE_DIR"] = str(disk / "cosmic") if disk.exists() and os.access(disk, os.W_OK) else "/tmp/cosmic-mark5"

from core.state_paths import config_file, read_json, atomic_write_json, runtime_state_summary  # noqa: E402
from web_server import CosmicWebServer  # noqa: E402


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _slug(text: str, limit: int = 48) -> str:
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", str(text or "").strip().lower()).strip("_")
    return (clean or "note")[:limit]


def _extract_response_text(response: Any) -> str:
    pieces: list[str] = []
    direct = getattr(response, "text", None)
    if direct:
        pieces.append(str(direct))
    try:
        for candidate in getattr(response, "candidates", []) or []:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", []) or []:
                text = getattr(part, "text", None)
                if text:
                    pieces.append(str(text))
    except Exception:
        pass
    cleaned: list[str] = []
    seen: set[str] = set()
    for piece in pieces:
        piece = piece.strip()
        if piece and piece not in seen:
            cleaned.append(piece)
            seen.add(piece)
    return "\n".join(cleaned).strip()


def _api_key() -> str:
    return (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("GOOGLE_GENAI_API_KEY")
        or os.getenv("COSMIC_GEMINI_API_KEY")
        or ""
    ).strip()


def _write_runtime_api_key() -> None:
    key = _api_key()
    if not key:
        return
    payload = {
        "gemini_api_key": key,
        "GEMINI_API_KEY": key,
        "api_key": key,
        "google_api_key": key,
    }
    atomic_write_json(config_file("api_keys.json"), payload, indent=2)
    project_config = PROJECT_ROOT / "config"
    project_config.mkdir(exist_ok=True)
    (project_config / "api_keys.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_cloud_pin() -> None:
    pin = (os.getenv("COSMIC_WEB_PIN") or os.getenv("COSMIC_PHONE_PIN") or "").strip()
    if not pin:
        return
    salt = os.getenv("COSMIC_PIN_SALT") or uuid.uuid4().hex
    pin_hash = hashlib.sha256((salt + pin).encode("utf-8")).hexdigest()
    atomic_write_json(
        config_file("phone_access.json"),
        {
            "enabled": True,
            "strict_web_pin": True,
            "salt": salt,
            "pin_hash": pin_hash,
            "created_by": "cloud_app.py",
            "updated_at": _now(),
        },
        indent=2,
    )


def _looks_like_research_request(text: str) -> bool:
    lower = text.lower().strip()
    return bool(re.search(r"\b(research|investigate|deep dive|deep-dive|study in detail|find sources|look into)\b", lower))


def _research_topic(text: str) -> str:
    cleaned = re.sub(
        r"(?i)^\s*(cosmic[, ]*)?(please\s+)?(research|investigate|deep dive into|deep-dive into|look into|study in detail)\s+",
        "",
        text,
    ).strip(" .")
    return cleaned or text.strip()


def _is_laptop_control_request(text: str) -> bool:
    lower = text.lower()
    local_terms = [
        "shutdown",
        "restart my laptop",
        "open app",
        "open chrome",
        "open file",
        "delete file",
        "move file",
        "rename file",
        "click",
        "press key",
        "type on my laptop",
        "screenshot",
        "control my laptop",
        "windows setting",
        "uninstall",
    ]
    return any(term in lower for term in local_terms)


class CloudCosmic:
    def __init__(self) -> None:
        self._logs: list[str] = []
        self._log_start = 0
        self._lock = threading.RLock()
        self._muted = False
        self._autonomy = {"level": os.getenv("COSMIC_AUTONOMY", "balanced")}
        self._performance = {"mode": "cloud", "web_poll_ms": 3000}
        self.write_log("SYS: COSMIC Mark5 Cloud Mode starting.")
        self.write_log("SYS: Laptop-control actions are disabled in cloud mode.")
        if not _api_key():
            self.write_log("ERR: GEMINI_API_KEY is not set in Render.")

    def write_log(self, text: str) -> None:
        text = str(text or "").strip()
        if not text:
            return
        print(f"[{_now()}] {text}", flush=True)
        with self._lock:
            self._logs.append(text)
            if len(self._logs) > 500:
                overflow = len(self._logs) - 500
                self._logs = self._logs[overflow:]
                self._log_start += overflow

    def get_logs(self, after: int = 0) -> dict:
        with self._lock:
            after = max(self._log_start, int(after or 0))
            relative = min(max(0, after - self._log_start), len(self._logs))
            items = self._logs[relative:]
            return {"items": items, "next": self._log_start + len(self._logs)}

    def get_confirmations(self) -> dict:
        return {"items": []}

    def resolve_confirmation(self, _id: str, _approved: bool) -> bool:
        self.write_log("SYS: Cloud mode has no local protected-action queue.")
        return False

    def set_muted(self, muted: bool) -> bool:
        self._muted = bool(muted)
        self.write_log(f"Web: Cloud notifications {'muted' if self._muted else 'active'}.")
        return True

    def set_autonomy(self, level: str) -> bool:
        level = str(level or "balanced").lower().strip()
        if level not in {"low", "balanced", "high"}:
            level = "balanced"
        self._autonomy["level"] = level
        self.write_log(f"Web: Cloud autonomy set to {level}.")
        return True

    def set_performance(self, mode: str) -> bool:
        self._performance["mode"] = "cloud"
        self.write_log("Web: Cloud mode keeps performance fixed for Render.")
        return True

    def _research_snapshot(self) -> list[dict]:
        try:
            data = read_json(config_file("research_tasks.json"), {})
            tasks = data.get("tasks", []) if isinstance(data, dict) else []
            output: list[dict] = []
            for task in tasks[:8]:
                if not isinstance(task, dict):
                    continue
                progress = task.get("progress", [])
                if isinstance(progress, list):
                    progress = progress[-3:]
                else:
                    progress = []
                result = str(task.get("result") or "")
                output.append(
                    {
                        "id": task.get("id", ""),
                        "topic": task.get("topic", ""),
                        "depth": task.get("depth", ""),
                        "status": task.get("status", ""),
                        "created_at": task.get("created_at", ""),
                        "updated_at": task.get("updated_at", ""),
                        "confidence": task.get("confidence", ""),
                        "source_count": task.get("source_count", 0),
                        "progress": progress,
                        "report_path": task.get("report_path", ""),
                        "result_preview": result[:240] if result else "",
                    }
                )
            return output
        except Exception:
            return []

    def get_status(self) -> dict:
        return {
            "connected": True,
            "text_connected": bool(_api_key()),
            "live_connected": False,
            "cloud_mode": True,
            "state": "TEXT ONLINE" if _api_key() else "API KEY NEEDED",
            "muted": self._muted,
            "system_metrics": {
                "health": 96 if _api_key() else 50,
                "health_label": "Cloud Online" if _api_key() else "Missing API Key",
                "cpu": 0,
                "memory": 0,
                "network_mbps": 0,
                "processes": "-",
                "uptime_seconds": int(time.monotonic()),
            },
            "voice": {"engine": "cloud-text", "windows_voice": "", "gemini_voice": "text"},
            "autonomy": self._autonomy,
            "performance": self._performance,
            "background_tasks": [],
            "research_tasks": self._research_snapshot(),
            "confirmations": [],
            "runtime_state": runtime_state_summary(),
        }

    def submit_message(self, text: str) -> bool:
        text = str(text or "").strip()
        if not text:
            return False
        self.write_log(f"Dhaval: {text}")
        threading.Thread(target=self._handle_message, args=(text,), daemon=True, name="CosmicCloudText").start()
        return True

    def _handle_message(self, text: str) -> None:
        try:
            if _is_laptop_control_request(text):
                self.write_log(
                    "Cosmic: I am running in Render Cloud Mode, so I cannot control your laptop while the laptop agent is offline. "
                    "Use local Mark5 for laptop actions; use cloud Mark5 for chat, research, memory, tasks, and calendar."
                )
                return

            if text.lower().startswith("remember "):
                note = text[9:].strip()
                if note:
                    from memory.memory_manager import update_memory

                    update_memory({"notes": {_slug(note): {"value": note}}})
                    self.write_log("Cosmic: Remembered that in cloud memory.")
                    return

            if _looks_like_research_request(text):
                from actions.research_agent import research_agent

                topic = _research_topic(text)

                def progress(message: str) -> None:
                    self.write_log(f"Research: {message}")

                result = research_agent(
                    {"action": "start", "topic": topic, "depth": os.getenv("COSMIC_RESEARCH_DEPTH", "standard"), "save_to_memory": True},
                    progress_callback=progress,
                )
                self.write_log(f"Cosmic: {result}")
                return

            answer = self._generate_answer(text)
            self.write_log(f"Cosmic: {answer}")
        except Exception as exc:
            self.write_log(f"ERR: Cloud response failed — {exc}")

    def _generate_answer(self, text: str) -> str:
        key = _api_key()
        if not key:
            return "I need GEMINI_API_KEY set in Render before I can answer."

        memory_context = ""
        try:
            from memory.memory_manager import format_memory_for_prompt

            memory_context = format_memory_for_prompt()
        except Exception:
            memory_context = ""

        prompt = f"""
You are COSMIC: Centralized Omniscient System for Machine Intelligence and Control.
You are Dhaval's personal AI command system, created by Dhaval.

You are currently running in Render Cloud Mode:
- You can chat, research, reason, remember, manage tasks, and manage calendar data.
- You cannot directly control Dhaval's laptop unless a separate local laptop agent is online.
- Be direct, useful, and concise unless Dhaval asks for detail.

Memory context:
{memory_context or "No stored cloud memory yet."}

Dhaval says:
{text}
""".strip()

        from google import genai

        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model=os.getenv("COSMIC_TEXT_MODEL", "gemini-2.5-flash"),
            contents=prompt,
        )
        answer = _extract_response_text(response)
        return answer or "I processed that, but the model returned an empty response."


def main() -> None:
    _write_runtime_api_key()
    _write_cloud_pin()
    app = CloudCosmic()
    server = CosmicWebServer(
        submit_message=app.submit_message,
        get_status=app.get_status,
        get_logs=app.get_logs,
        set_muted=app.set_muted,
        set_autonomy=app.set_autonomy,
        set_performance=app.set_performance,
        get_confirmations=app.get_confirmations,
        resolve_confirmation=app.resolve_confirmation,
        write_log=app.write_log,
        host=os.getenv("COSMIC_WEB_HOST", "0.0.0.0"),
        port=int(os.getenv("PORT") or os.getenv("COSMIC_WEB_PORT", "8775")),
    )
    url = server.start()
    app.write_log(f"SYS: COSMIC Cloud web app listening on {url}")
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
