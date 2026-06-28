from __future__ import annotations

import json
import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


WORKFLOW_PATH = get_base_dir() / "config" / "workflows.json"
_LOCK = threading.RLock()

# Recursive workflows and shutdown/memory mutations are intentionally blocked.
# A workflow may still use every normal COSMIC action tool.
BLOCKED_STEP_TOOLS = {"workflow_manager", "shutdown_cosmic", "save_memory"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower())
    return value.strip("-")[:64]


def _load() -> dict:
    with _LOCK:
        if not WORKFLOW_PATH.exists():
            return {"version": 1, "workflows": {}}
        try:
            data = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("workflows"), dict):
                raise ValueError("Invalid workflow database")
            return data
        except Exception as exc:
            raise RuntimeError(f"Could not read workflows: {exc}") from exc


def _save(data: dict) -> None:
    with _LOCK:
        WORKFLOW_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp_path = WORKFLOW_PATH.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temp_path.replace(WORKFLOW_PATH)


def _resolve(data: dict, identifier: str) -> tuple[str, dict]:
    wanted = identifier.strip().lower()
    for workflow_id, workflow in data["workflows"].items():
        if workflow_id.lower() == wanted or workflow.get("name", "").lower() == wanted:
            return workflow_id, workflow
    raise ValueError(f"Workflow '{identifier}' was not found")


def _validate_steps(steps: object) -> list[dict]:
    if not isinstance(steps, list) or not steps:
        raise ValueError("A workflow needs at least one step")
    if len(steps) > 25:
        raise ValueError("A workflow can contain at most 25 steps")

    clean_steps = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise ValueError(f"Step {index} must be an object")
        tool = str(step.get("tool", "")).strip()
        parameters = step.get("parameters", {})
        if isinstance(parameters, str):
            try:
                parameters = json.loads(parameters)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Step {index} parameters are not valid JSON") from exc
        if not tool:
            raise ValueError(f"Step {index} is missing a tool name")
        if tool in BLOCKED_STEP_TOOLS:
            raise ValueError(f"Tool '{tool}' cannot be placed inside a workflow")
        if not isinstance(parameters, dict):
            raise ValueError(f"Step {index} parameters must be an object")
        clean_steps.append(
            {
                "tool": tool,
                "parameters": parameters,
                "description": str(step.get("description", "")).strip(),
            }
        )
    return clean_steps


def _summary(workflow: dict, include_steps: bool = False) -> dict:
    result = {
        "id": workflow["id"],
        "name": workflow["name"],
        "description": workflow.get("description", ""),
        "enabled": workflow.get("enabled", True),
        "step_count": len(workflow.get("steps", [])),
        "run_count": workflow.get("run_count", 0),
        "last_run": workflow.get("last_run"),
    }
    if include_steps:
        result["steps"] = workflow.get("steps", [])
    return result


async def workflow_manager(
    parameters: dict,
    step_runner: Callable[[str, dict], Awaitable[str]] | None = None,
) -> str:
    """Create, manage, and execute reusable named workflows."""
    action = str(parameters.get("action", "list")).strip().lower()
    identifier = str(parameters.get("workflow_id") or parameters.get("name") or "").strip()
    data = _load()

    if action == "list":
        workflows = sorted(
            (_summary(item) for item in data["workflows"].values()),
            key=lambda item: item["name"].lower(),
        )
        return json.dumps({"workflows": workflows}, ensure_ascii=False)

    if action == "create":
        name = str(parameters.get("name", "")).strip()
        if not name:
            raise ValueError("Workflow name is required")
        workflow_id = _slug(name)
        if not workflow_id:
            raise ValueError("Workflow name must contain letters or numbers")
        if workflow_id in data["workflows"]:
            raise ValueError(f"Workflow '{name}' already exists")
        timestamp = _now()
        workflow = {
            "id": workflow_id,
            "name": name[:100],
            "description": str(parameters.get("description", "")).strip()[:500],
            "enabled": bool(parameters.get("enabled", True)),
            "steps": _validate_steps(parameters.get("steps")),
            "created_at": timestamp,
            "updated_at": timestamp,
            "last_run": None,
            "run_count": 0,
        }
        data["workflows"][workflow_id] = workflow
        _save(data)
        return json.dumps({"created": _summary(workflow, include_steps=True)}, ensure_ascii=False)

    if not identifier:
        raise ValueError("Provide a workflow name or workflow_id")

    workflow_id, workflow = _resolve(data, identifier)

    if action == "get":
        return json.dumps({"workflow": _summary(workflow, include_steps=True)}, ensure_ascii=False)

    if action == "delete":
        del data["workflows"][workflow_id]
        _save(data)
        return f"Deleted workflow '{workflow['name']}'."

    if action in {"enable", "disable"}:
        workflow["enabled"] = action == "enable"
        workflow["updated_at"] = _now()
        _save(data)
        return f"Workflow '{workflow['name']}' is now {action}d."

    if action == "update":
        new_name = parameters.get("new_name")
        if new_name is not None:
            new_name = str(new_name).strip()
            if not new_name:
                raise ValueError("new_name cannot be empty")
            workflow["name"] = new_name[:100]
        if "description" in parameters:
            workflow["description"] = str(parameters.get("description", "")).strip()[:500]
        if "enabled" in parameters:
            workflow["enabled"] = bool(parameters["enabled"])
        if "steps" in parameters:
            workflow["steps"] = _validate_steps(parameters["steps"])
        workflow["updated_at"] = _now()
        _save(data)
        return json.dumps({"updated": _summary(workflow, include_steps=True)}, ensure_ascii=False)

    if action == "run":
        if not workflow.get("enabled", True):
            raise ValueError(f"Workflow '{workflow['name']}' is disabled")
        if step_runner is None:
            raise RuntimeError("Workflow execution is unavailable")

        results = []
        for index, step in enumerate(workflow.get("steps", []), start=1):
            result = await step_runner(step["tool"], dict(step.get("parameters", {})))
            results.append(
                {
                    "step": index,
                    "tool": step["tool"],
                    "result": str(result)[:1000],
                }
            )

        workflow["last_run"] = _now()
        workflow["run_count"] = int(workflow.get("run_count", 0)) + 1
        workflow["updated_at"] = _now()
        _save(data)
        return json.dumps(
            {"workflow": workflow["name"], "status": "completed", "results": results},
            ensure_ascii=False,
        )

    raise ValueError(
        "Unknown workflow action. Use create, list, get, update, delete, run, enable, or disable."
    )
