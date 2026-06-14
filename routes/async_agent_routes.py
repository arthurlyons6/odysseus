from fastapi import APIRouter
from pathlib import Path

from src.async_agents import registry
from src.async_agent_runner import execute_step, workspace, log_event, validate_manifest

router = APIRouter()
BASE_DIR = Path(__file__).resolve().parents[1]
OUT_BASE = BASE_DIR / "data" / "workspace"


@router.get("/api/async-agents")
async def list_async_agents():
    return {"items": registry(BASE_DIR / "data" / "async_agents")}


@router.post("/api/async-agents/{agent_id}/run")
async def run_async_agent(agent_id: str):
    manifest_path = BASE_DIR / "data" / "async_agents" / f"{agent_id}.json"
    if not manifest_path.exists():
        return {"agent_id": agent_id, "status": "error", "error": "manifest not found"}

    try:
        manifest = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"agent_id": agent_id, "status": "error", "error": f"invalid json: {e}"}

    errs = validate_manifest(manifest)
    if errs:
        return {"agent_id": agent_id, "status": "error", "validation_errors": errs}

    log_file = Path(manifest.get("memory", {}).get("log_file", ""))
    if not log_file:
        log_file = workspace(agent_id) / "run-log.jsonl"

    context = {"completed_steps": []}
    outputs = []
    for step in manifest.get("task_queue", []):
        res = execute_step(manifest, step)
        if res.get("output_path"):
            outputs.append(res["output_path"])
            context.setdefault("outputs", []).append(res["output_path"])
        log_event(
            log_file,
            {
                "agent_id": agent_id,
                "step_id": step.get("step_id"),
                "status": res.get("status", "ok"),
                "tool": res.get("tool"),
                "output_path": str(res.get("output_path", "")),
            },
        )
        context["completed_steps"].append(step.get("step_id"))

    from src.async_agent_runner import process_handoffs
    process_handoffs(manifest, context)

    return {
        "agent_id": agent_id,
        "status": "completed",
        "log_file": str(log_file),
        "outputs": outputs,
    }
