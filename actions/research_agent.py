from __future__ import annotations

import json
# COSMIC_PERSONAL_MASTER_STATE_PATHS
import re
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

from actions.web_search import web_search
from memory.memory_manager import update_memory
from agent.autonomy import load_autonomy_config
from core.state_paths import config_file, memory_file, research_reports_dir, read_json, atomic_write_json, atomic_write_text


ProgressCallback = Callable[[str], None]


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _get_base_dir()
TASKS_PATH = config_file("research_tasks.json")
REPORTS_DIR = research_reports_dir()
KNOWLEDGE_PATH = memory_file("research_knowledge.json")

_lock = threading.RLock()
_cancel_requested: set[str] = set()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _load_json(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    try:
        data = read_json(path, fallback)
        return data if isinstance(data, dict) else fallback
    except Exception:
        return fallback


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, data, indent=2, ensure_ascii=False)


def _load_store() -> dict:
    data = _load_json(TASKS_PATH, {"tasks": []})
    if not isinstance(data.get("tasks"), list):
        data["tasks"] = []
    return data


def _save_store(store: dict) -> None:
    _save_json(TASKS_PATH, store)


def _load_knowledge() -> dict:
    data = _load_json(KNOWLEDGE_PATH, {"entries": []})
    if not isinstance(data.get("entries"), list):
        data["entries"] = []
    return data


def _save_knowledge(data: dict) -> None:
    data["entries"] = data.get("entries", [])[:250]
    _save_json(KNOWLEDGE_PATH, data)


def _slug(text: str, limit: int = 48) -> str:
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    return (clean or "research")[:limit]


def _compact(text: str, limit: int = 360) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _find_task(store: dict, task_id: str) -> dict | None:
    for task in store.get("tasks", []):
        if task.get("id") == task_id:
            return task
    return None


def _update_task(task_id: str, **updates) -> dict | None:
    with _lock:
        store = _load_store()
        task = _find_task(store, task_id)
        if not task:
            return None
        task.update(updates)
        task["updated_at"] = _now()
        _save_store(store)
        return dict(task)


def _add_progress(task_id: str, message: str, progress_callback: ProgressCallback | None = None) -> None:
    task_topic = "Research"
    with _lock:
        store = _load_store()
        task = _find_task(store, task_id)
        if not task:
            return
        task_topic = task.get("topic", "Research")
        task.setdefault("progress", []).append({"time": _now(), "message": message})
        task["progress"] = task["progress"][-120:]
        task["updated_at"] = _now()
        _save_store(store)

    if progress_callback:
        try:
            progress_callback(f"{task_topic}: {message}")
        except Exception:
            pass


def _build_queries(topic: str, depth: str) -> list[str]:
    year = datetime.now().year
    query_sets = {
        "quick": [
            f"{topic} overview key facts current {year}",
        ],
        "standard": [
            f"{topic} overview key facts current {year}",
            f"{topic} latest developments current {year}",
            f"{topic} benefits limitations risks analysis",
            f"{topic} examples practical guide",
        ],
        "deep": [
            f"{topic} overview key facts current {year}",
            f"{topic} latest developments current {year}",
            f"{topic} expert analysis benefits limitations risks",
            f"{topic} practical examples case studies",
            f"{topic} best practices recommendations",
            f"{topic} future trends current research",
        ],
    }
    return query_sets.get(depth, query_sets["standard"])


def _extract_text_from_response(response) -> str:
    text = getattr(response, "text", None)
    if text:
        return str(text).strip()

    pieces: list[str] = []
    try:
        for candidate in response.candidates:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", []) or []:
                part_text = getattr(part, "text", None)
                if part_text:
                    pieces.append(part_text)
    except Exception:
        pass
    return "\n".join(pieces).strip()


def _extract_sources(text: str) -> list[dict]:
    urls = re.findall(r"https?://[^\s)>\]]+", text or "")
    seen: set[str] = set()
    sources: list[dict] = []
    for raw_url in urls:
        url = raw_url.rstrip(".,;")
        if url in seen:
            continue
        seen.add(url)
        domain = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
        sources.append({"title": domain or url, "url": url})
    return sources[:20]


def _confidence_for(results: list[dict], sources: list[dict]) -> str:
    joined = "\n".join(str(item.get("result", "")) for item in results).lower()
    failures = joined.count("search failed") + joined.count("no results found")
    source_count = len(sources)
    if failures == 0 and source_count >= 5:
        return "high"
    if failures <= 1 and source_count >= 2:
        return "medium"
    return "low"


def _ai_synthesis(topic: str, depth: str, research_results: list[dict], sources: list[dict]) -> str:
    evidence = "\n\n".join(
        f"QUERY: {item['query']}\nRESULT:\n{item['result']}"
        for item in research_results
    )
    source_text = "\n".join(f"- {s.get('title')}: {s.get('url')}" for s in sources[:12])
    evidence = evidence[:16000]

    prompt = f"""
You are COSMIC's private research brain.
Synthesize this research mission into a clear report for Dhaval.

Topic: {topic}
Depth: {depth}

Output format:
1. Direct answer / executive summary
2. Key findings
3. Important details or caveats
4. Practical next steps
5. What COSMIC should remember in one sentence

Use only the evidence below. Be concise but useful.

SOURCES:
{source_text}

EVIDENCE:
{evidence}
""".strip()

    try:
        from google import genai
        from actions.web_search import _get_api_key

        client = genai.Client(api_key=_get_api_key())
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        text = _extract_text_from_response(response)
        if text:
            return text
    except Exception:
        pass

    bullets: list[str] = []
    for item in research_results:
        result = re.sub(r"\s+", " ", item.get("result", "")).strip()
        if result:
            bullets.append(f"- {item['query']}: {_compact(result, 420)}")

    return (
        f"Research summary for {topic}:\n\n"
        + "\n".join(bullets[:8])
        + "\n\nWhat COSMIC should remember: "
        + _compact(" ".join(bullets), 300)
    )


def _write_report(task: dict, synthesis: str, research_results: list[dict], sources: list[dict], confidence: str) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    topic = task.get("topic", "research")
    report_path = REPORTS_DIR / f"{_slug(topic)}_{task['id']}.md"
    sections = [
        "# COSMIC Research Report",
        "",
        f"Topic: {topic}",
        f"Task ID: {task['id']}",
        f"Depth: {task.get('depth', 'standard')}",
        f"Confidence: {confidence}",
        f"Created: {task.get('created_at', '')}",
        f"Completed: {_now()}",
        "",
        "## Synthesis",
        "",
        synthesis,
        "",
        "## Sources",
        "",
    ]
    if sources:
        sections.extend(f"- [{source.get('title')}]({source.get('url')})" for source in sources)
    else:
        sections.append("- No explicit source URLs were captured from the search backend.")

    sections.extend(["", "## Research Trail", ""])
    for index, item in enumerate(research_results, 1):
        sections.extend([
            f"### {index}. {item['query']}",
            "",
            item.get("result", "").strip() or "No result.",
            "",
        ])

    atomic_write_text(report_path, "\n".join(sections).strip() + "\n", encoding="utf-8")
    return report_path


def _memory_sentence(topic: str, synthesis: str, confidence: str, source_count: int) -> str:
    marker = "What COSMIC should remember"
    remembered = ""
    if marker.lower() in synthesis.lower():
        for line in synthesis.splitlines():
            if marker.lower() in line.lower():
                remembered = line.split(":", 1)[-1].strip()
                break
    if not remembered:
        remembered = re.sub(r"[*#`>\-]+", " ", synthesis)
    return _compact(
        f"{topic}: {remembered} (researched {_today()}, confidence: {confidence}, sources: {source_count})",
        360,
    )


def _save_knowledge_entry(task: dict, synthesis: str, memory_note: str, sources: list[dict], confidence: str, report_path: Path) -> None:
    knowledge = _load_knowledge()
    entries = [entry for entry in knowledge.get("entries", []) if entry.get("task_id") != task.get("id")]
    entries.insert(0, {
        "id": _slug(task.get("topic", "research")),
        "task_id": task.get("id"),
        "topic": task.get("topic"),
        "summary": memory_note,
        "confidence": confidence,
        "sources": sources,
        "source_count": len(sources),
        "report_path": str(report_path),
        "researched_at": _now(),
        "depth": task.get("depth", "standard"),
        "synthesis": synthesis[:2500],
    })
    knowledge["entries"] = entries
    _save_knowledge(knowledge)


def _run_task(task_id: str, progress_callback: ProgressCallback | None = None) -> None:
    with _lock:
        store = _load_store()
        task = _find_task(store, task_id)
        if not task:
            return
        topic = task.get("topic", "").strip()
        depth = task.get("depth", "standard")
        save_to_memory = bool(task.get("save_to_memory", True))

    try:
        _update_task(task_id, status="running", started_at=_now())
        _add_progress(task_id, "Mission accepted. Building research plan.", progress_callback)

        research_results: list[dict] = []
        queries = _build_queries(topic, depth)
        for index, query in enumerate(queries, 1):
            if task_id in _cancel_requested:
                _update_task(task_id, status="cancelled", completed_at=_now())
                _add_progress(task_id, "Mission cancelled.", progress_callback)
                return

            _add_progress(task_id, f"Searching source set {index}/{len(queries)}.", progress_callback)
            result = web_search({"query": query}, player=None)
            sources = _extract_sources(result)
            research_results.append({"query": query, "result": result, "sources": sources})
            _update_task(task_id, source_count=sum(len(item.get("sources", [])) for item in research_results))

        all_sources: list[dict] = []
        seen_urls: set[str] = set()
        for item in research_results:
            for source in item.get("sources", []):
                url = source.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_sources.append(source)

        confidence = _confidence_for(research_results, all_sources)
        _update_task(task_id, confidence=confidence, sources=all_sources[:20], source_count=len(all_sources))

        _add_progress(task_id, f"Synthesizing findings. Confidence: {confidence}.", progress_callback)
        synthesis = _ai_synthesis(topic, depth, research_results, all_sources)

        _add_progress(task_id, "Saving research report with sources.", progress_callback)
        with _lock:
            store = _load_store()
            task = _find_task(store, task_id) or {"id": task_id, "topic": topic, "depth": depth}
        report_path = _write_report(task, synthesis, research_results, all_sources, confidence)

        memory_note = _memory_sentence(topic, synthesis, confidence, len(all_sources))
        _save_knowledge_entry(task, synthesis, memory_note, all_sources, confidence, report_path)

        if save_to_memory:
            _add_progress(task_id, "Updating COSMIC memory and knowledge base.", progress_callback)
            update_memory({
                "research": {
                    _slug(topic): {"value": memory_note}
                }
            })

        _update_task(
            task_id,
            status="completed",
            completed_at=_now(),
            result=synthesis,
            memory_note=memory_note,
            report_path=str(report_path),
            confidence=confidence,
            sources=all_sources[:20],
            source_count=len(all_sources),
        )
        _add_progress(task_id, f"Mission complete. Report saved: {report_path}", progress_callback)

    except Exception as exc:
        _update_task(task_id, status="failed", error=str(exc), completed_at=_now())
        _add_progress(task_id, f"Mission failed: {exc}", progress_callback)
    finally:
        _cancel_requested.discard(task_id)


def _format_task(task: dict, detailed: bool = False) -> str:
    lines = [
        f"ID: {task.get('id')}",
        f"Topic: {task.get('topic')}",
        f"Status: {task.get('status')}",
        f"Depth: {task.get('depth')}",
        f"Confidence: {task.get('confidence', 'pending')}",
        f"Sources: {task.get('source_count', 0)}",
        f"Updated: {task.get('updated_at', task.get('created_at', ''))}",
    ]
    if task.get("report_path"):
        lines.append(f"Report: {task['report_path']}")
    if task.get("error"):
        lines.append(f"Error: {task['error']}")
    if detailed:
        progress = task.get("progress", [])[-12:]
        if progress:
            lines.append("Progress:")
            lines.extend(f"- {p.get('time')}: {p.get('message')}" for p in progress)
        sources = task.get("sources", [])[:8]
        if sources:
            lines.append("Sources:")
            lines.extend(f"- {s.get('title')}: {s.get('url')}" for s in sources)
        if task.get("result"):
            lines.append("\nResult:")
            lines.append(task["result"])
    return "\n".join(lines)


def research_agent(parameters: dict | None, progress_callback: ProgressCallback | None = None) -> str:
    """Start or manage autonomous COSMIC research missions."""
    params = parameters or {}
    action = str(params.get("action", "start")).strip().lower() or "start"

    if action == "start":
        topic = str(params.get("topic") or params.get("query") or "").strip()
        if not topic:
            return "Please provide a research topic."

        default_depth = load_autonomy_config().get("research_default_depth", "standard")
        depth = str(params.get("depth", default_depth)).strip().lower()
        if depth not in {"quick", "standard", "deep"}:
            depth = "standard"

        task_id = uuid.uuid4().hex[:8]
        task = {
            "id": task_id,
            "topic": topic,
            "depth": depth,
            "status": "queued",
            "created_at": _now(),
            "updated_at": _now(),
            "save_to_memory": bool(params.get("save_to_memory", True)),
            "progress": [{"time": _now(), "message": "Queued."}],
            "confidence": "pending",
            "sources": [],
            "source_count": 0,
        }

        with _lock:
            store = _load_store()
            store.setdefault("tasks", []).insert(0, task)
            store["tasks"] = store["tasks"][:100]
            _save_store(store)

        thread = threading.Thread(
            target=_run_task,
            args=(task_id, progress_callback),
            name=f"cosmic-research-{task_id}",
            daemon=True,
        )
        thread.start()

        if progress_callback:
            progress_callback(f"{topic}: Research mission started ({task_id}).")
        return (
            f"Research mission started. ID: {task_id}. "
            "COSMIC will post progress updates, save sources, and update research memory."
        )

    if action in {"list", "status"} and not params.get("task_id"):
        with _lock:
            tasks = _load_store().get("tasks", [])[:8]
        if not tasks:
            return "No research missions yet."
        return "\n\n".join(_format_task(task, detailed=False) for task in tasks)

    if action in {"knowledge", "memory"}:
        entries = _load_knowledge().get("entries", [])[:8]
        if not entries:
            return "No research knowledge entries yet."
        return "\n\n".join(
            f"{entry.get('topic')} ({entry.get('confidence')}, {entry.get('researched_at')}): {entry.get('summary')}"
            for entry in entries
        )

    task_id = str(params.get("task_id", "")).strip()
    if not task_id:
        return "Please provide task_id."

    with _lock:
        task = _find_task(_load_store(), task_id)
    if not task:
        return f"Research mission not found: {task_id}"

    if action in {"status", "get"}:
        return _format_task(task, detailed=True)

    if action == "cancel":
        if task.get("status") not in {"queued", "running", "cancelling"}:
            return f"Research mission {task_id} is already {task.get('status')}."
        _cancel_requested.add(task_id)
        _update_task(task_id, status="cancelling")
        return f"Cancellation requested for research mission {task_id}."

    return f"Unknown research action: {action}"
