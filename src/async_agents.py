import json
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = {
    "agent_id": str,
    "display_name": str,
    "mission": str,
    "role": str,
    "status": str,
    "tags": list,
    "inputs": dict,
    "skills": list,
    "memory": dict,
    "task_queue": list,
    "escalation": dict,
    "reporting": dict,
}

ALLOWED_ROLES = {"research", "development", "deal", "performance", "content", "vertical"}
ALLOWED_STATUSES = {"active", "paused", "archived"}
ALLOWED_SCHEDULES = {"once", "daily", "weekly", "monthly", "cron"}


def _check_type(value: Any, expected: type, path: str, errors: list[str]) -> None:
    if not isinstance(value, expected):
        errors.append(f"{path}: expected {expected.__name__}, got {type(value).__name__}")


def validate_manifest(manifest: dict) -> list[str]:
    errors: list[str] = []

    # Required fields + rough typing
    for field, expected in REQUIRED_FIELDS.items():
        if field not in manifest:
            errors.append(f"missing required field: {field}")
        else:
            _check_type(manifest[field], expected, field, errors)

    # Enums
    if "role" in manifest and manifest["role"] not in ALLOWED_ROLES:
        errors.append(f"role must be one of {sorted(ALLOWED_ROLES)}")
    if "status" in manifest and manifest["status"] not in ALLOWED_STATUSES:
        errors.append(f"status must be one of {sorted(ALLOWED_STATUSES)}")

    # Memory fields
    mem = manifest.get("memory", {})
    if isinstance(mem, dict):
        if "save_outputs_to" in mem:
            p = Path(mem["save_outputs_to"])
            if not p.is_absolute():
                errors.append("memory.save_outputs_to must be an absolute path")

    # Task queue shape
    queue = manifest.get("task_queue", [])
    if isinstance(queue, list):
        for idx, step in enumerate(queue):
            if not isinstance(step, dict):
                errors.append(f"task_queue[{idx}]: expected object")
                continue
            if "step_id" not in step:
                errors.append(f"task_queue[{idx}]: missing step_id")
            if "prompt" not in step:
                errors.append(f"task_queue[{idx}]: missing prompt")

    # Escalation sanity
    esc = manifest.get("escalation", {})
    if isinstance(esc, dict):
        if "max_tool_calls" in esc and not isinstance(esc["max_tool_calls"], int):
            errors.append("escalation.max_tool_calls must be an integer")
        if "timeout" in esc and not isinstance(esc["timeout"], int):
            errors.append("escalation.timeout must be an integer (seconds)")

    return errors


def load_manifest(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    return json.loads(raw)


def registry(base_dir: Path) -> list[dict]:
    results = []
    for p in sorted(base_dir.glob("*.json")):
        try:
            manifest = load_manifest(p)
        except Exception as e:
            results.append({
                "file": p.name,
                "agent_id": None,
                "display_name": p.stem,
                "status": "error",
                "errors": [f"failed to parse JSON: {e}"],
            })
            continue
        errors = validate_manifest(manifest)
        results.append({
            "file": p.name,
            "agent_id": manifest.get("agent_id"),
            "display_name": manifest.get("display_name"),
            "role": manifest.get("role"),
            "status": manifest.get("status"),
            "errors": errors,
            "valid": not errors,
        })
    return results


if __name__ == "__main__":
    base = Path("C:/Users/13464/odysseus/data/async_agents")
    agents = registry(base)
    print(f"Async agent registry — {len(agents)} manifest(s)\n")
    for a in agents:
        tag = "OK" if a["valid"] else "FAIL"
        print(f"[{tag}] {a['file']} :: {a.get('display_name')} (id={a.get('agent_id')})")
        for err in a["errors"]:
            print(f"       - {err}")
    if not agents:
        print("No manifests found.")
