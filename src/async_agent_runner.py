# C:\Users\13464\odysseus\src\async_agent_runner.py
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from urllib.request import urlopen, Request as _HttpRequest
    from urllib.error import URLError, HTTPError
except Exception:  # pragma: no cover
    urlopen = None
    HTTPError = Exception
    URLError = Exception

ROOT = Path(__file__).resolve().parents[1]
ASYNC_DIR = ROOT / "data" / "async_agents"
OUT_BASE = ROOT / "data" / "workspace"
DEFAULT_BASE_URL = "http://127.0.0.1:7000"

ALLOWED_ROLES = {"research", "development", "deal", "performance", "content", "vertical"}
ALLOWED_STATUSES = {"active", "paused", "archived"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(log_file: Path, event: dict[str, Any]) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": utc_now(), **event}) + "\n")


def workspace(agent_id: str) -> Path:
    w = OUT_BASE / agent_id
    w.mkdir(parents=True, exist_ok=True)
    return w


def validate_manifest(manifest: dict) -> list[str]:
    errors: list[str] = []
    required = [
        "agent_id",
        "display_name",
        "mission",
        "role",
        "status",
        "tags",
        "inputs",
        "skills",
        "memory",
        "task_queue",
        "escalation",
        "reporting",
    ]
    for f in required:
        if f not in manifest:
            errors.append(f"missing required field: {f}")

    if not isinstance(manifest.get("tags"), list):
        errors.append("tags must be list")
    if not isinstance(manifest.get("inputs"), dict):
        errors.append("inputs must be dict")
    if not isinstance(manifest.get("skills"), list):
        errors.append("skills must be list")
    if not isinstance(manifest.get("task_queue"), list):
        errors.append("task_queue must be list")
    if not isinstance(manifest.get("escalation"), dict):
        errors.append("escalation must be dict")
    if not isinstance(manifest.get("reporting"), dict):
        errors.append("reporting must be dict")

    if "role" in manifest and manifest["role"] not in ALLOWED_ROLES:
        errors.append(f"role must be one of {sorted(ALLOWED_ROLES)}")
    if "status" in manifest and manifest["status"] not in ALLOWED_STATUSES:
        errors.append(f"status must be one of {sorted(ALLOWED_STATUSES)}")

    mem = manifest.get("memory", {})
    if isinstance(mem, dict):
        if mem.get("save_outputs_to"):
            p = Path(mem["save_outputs_to"])
            if not Path(p).is_absolute():
                errors.append("memory.save_outputs_to must be absolute")
        if mem.get("log_file"):
            p = Path(mem["log_file"])
            if not Path(p).is_absolute():
                errors.append("memory.log_file must be absolute")

    queue = manifest.get("task_queue", [])
    if isinstance(queue, list):
        for i, step in enumerate(queue):
            if not isinstance(step, dict):
                errors.append(f"task_queue[{i}]: expected object")
                continue
            if "step_id" not in step:
                errors.append(f"task_queue[{i}]: missing step_id")
            if "prompt" not in step:
                errors.append(f"task_queue[{i}]: missing prompt")

    return errors


def needs_approval(step: dict, approval_required_before: list[str]) -> bool:
    return step.get("tool") in approval_required_before


def cmd_runner_default_timeout() -> int:
    return int(os.getenv("ODYSSEUS_CMD_TIMEOUT", "120"))


def execute_step(manifest: dict, step: dict) -> dict[str, Any]:
    tool = step.get("tool", "terminal")
    step_id = step.get("step_id", "unknown")
    approvals = manifest.get("escalation", {}).get("approval_required_before", [])

    result: dict[str, Any] = {
        "step_id": step_id,
        "tool": tool,
        "status": "blocked" if needs_approval(step, approvals) else "ok",
    }

    output_text = ""
    output_path = ""

    if tool == "terminal":
        output_text = _tool_terminal(step)

    elif tool == "read_file":
        target = step.get("output_path") or step.get("path") or ""
        if not target:
            result.update(status="error", error="read_file: missing path")
        else:
            try:
                output_text = Path(target).read_text(encoding="utf-8")
                result.update(status="ok", output_path=str(target))
            except Exception as e:
                result.update(status="error", error=f"read_file failed: {e}")

    elif tool == "write_file":
        if needs_approval(step, approvals):
            result.update(status="blocked", error="approval required before write_file")
        else:
            content = step.get("content") or step.get("prompt") or ""
            rel = step.get("output_path") or f"{step_id}.md"
            out_base = Path(manifest.get("memory", {}).get("save_outputs_to", "")) or workspace(manifest["agent_id"])
            out_path = Path(out_base) / rel
            try:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(content, encoding="utf-8")
                result.update(status="ok", output_path=str(out_path))
                output_text = content
            except Exception as e:
                result.update(status="error", error=f"write_file failed: {e}")

    elif tool == "patch":
        if needs_approval(step, approvals):
            result.update(status="blocked", error="approval required before patch")
        else:
            path = step.get("path") or step.get("output_path") or ""
            old = step.get("old_string") or step.get("find")
            new = step.get("new_string") or step.get("replace")
            if not path or old is None or new is None:
                result.update(status="error", error="patch: missing path/old_string/new_string")
            else:
                try:
                    src = Path(path).read_text(encoding="utf-8")
                    if old not in src:
                        result.update(status="error", error="patch: old_string not found")
                    else:
                        out = src.replace(old, new, 1 if not step.get("replace_all") else -1)
                        Path(path).write_text(out, encoding="utf-8")
                        result.update(status="ok", output_path=str(path))
                        output_text = out
                except Exception as e:
                    result.update(status="error", error=f"patch failed: {e}")

    elif tool == "web_search":
        query = step.get("query") or step.get("prompt") or ""
        output_text = _tool_web_search(query)
        result.update(status="ok", output_path="")

    elif tool == "web_fetch":
        url = step.get("url") or step.get("output_path") or ""
        if not url:
            result.update(status="error", error="web_fetch: missing url")
        else:
            output_text = _tool_web_fetch(url)
            result.update(status="ok", output_path=url)

    else:
        output_text = f"[unknown tool={tool}] prompt={step.get('prompt','')!r}"
        result.update(status="error", error=f"unsupported tool: {tool}")

    # Persist terminal/web results into workspace output when no explicit path exists
    if tool in {"terminal", "web_search", "web_fetch"} and result.get("status") == "ok" and not output_path:
        ws = workspace(manifest["agent_id"])
        out_path = ws / f"{step_id}.out"
        out_path.write_text(output_text, encoding="utf-8")
        result["output_path"] = str(out_path)

    if tool == "write_file" and result.get("status") == "ok":
        output_text = Path(result["output_path"]).read_text(encoding="utf-8")

    return result


def _tool_terminal(step: dict) -> str:
    cmd = step.get("command") or step.get("prompt") or ""
    if not cmd.strip():
        return "[terminal step skipped: no command provided]"
    timeout = int(step.get("timeout") or cmd_runner_default_timeout())
    try:
        import subprocess
        shell = os.name == "nt"
        completed = subprocess.run(
            cmd,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = completed.stdout or ""
        err = completed.stderr or ""
        code = completed.returncode
        return f"$ {cmd}\n[exit {code}]\n{out}\n{err}".strip()
    except Exception as e:
        return f"$ {cmd}\n[error] {e}"


def _tool_web_search(query: str) -> str:
    if not query:
        return ""
    try:
        import urllib.parse
        import urllib.request
        q = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={q}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode("utf-8", errors="replace")
        # Very light snippet extraction for proof-of-life only
        snippet = data[:4000]
        return f"web_search({query!r})\n" + snippet
    except Exception as e:
        return f"web_search({query!r})\n[error] {e}"


def _tool_web_fetch(url: str) -> str:
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode("utf-8", errors="replace")
        return f"web_fetch({url})\n" + data[:8000]
    except Exception as e:
        return f"web_fetch({url})\n[error] {e}"


def process_handoffs(manifest: dict, context: dict[str, Any]) -> None:
    handoffs = manifest.get("escalation", {}).get("handoff_rules", [])
    for rule in handoffs:
        match = rule.get("match")
        to_agent = rule.get("to_agent")
        condition = rule.get("condition", "")
        if not to_agent:
            continue
        ws = workspace(manifest["agent_id"])
        note = ws / f"handoff-{manifest['agent_id']}-{match}.md"
        note.write_text(
            f"# Handoff note: {manifest['agent_id']} -> {to_agent}\n\n"
            f"Match: {match}\nCondition: {condition}\nContext: {json.dumps(context, default=str)}\n",
            encoding="utf-8",
        )


def load_manifests() -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    if not ASYNC_DIR.exists():
        return manifests
    for p in sorted(ASYNC_DIR.glob("*.json")):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"ERR load {p}: {e}", file=sys.stderr)
            continue
        errs = validate_manifest(m)
        m["_validation_errors"] = errs
        m["_source"] = str(p)
        manifests.append(m)
    return manifests


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Validate only")
    ap.add_argument("--run-limit", type=int, default=0, help="Max active agents to execute")
    args = ap.parse_args()

    manifests = load_manifests()
    active = [m for m in manifests if m.get("status") == "active"]
    print(f"Loaded {len(manifests)} manifest(s), {len(active)} active")

    if args.dry_run:
        for m in active:
            errs = m.get("_validation_errors", [])
            print(
                f"- {m['agent_id']}: {'OK' if not errs else 'FAIL ' + '; '.join(errs)}"
            )
        return 0

    executed = 0
    for m in active:
        if args.run_limit and executed >= args.run_limit:
            break
        log_file = Path(m.get("memory", {}).get("log_file", ""))
        if not log_file:
            log_file = workspace(m["agent_id"]) / "run-log.jsonl"
        ws = workspace(m["agent_id"])
        context: dict[str, Any] = {"completed_steps": []}
        for step in m.get("task_queue", []):
            print(f"[{m['agent_id']}] step {step.get('step_id')} ...")
            res = execute_step(m, step)
            if res.get("output_path"):
                context.setdefault("outputs", []).append(res["output_path"])
            if res.get("status") == "blocked":
                log_event(
                    log_file,
                    {
                        "agent_id": m.get("agent_id"),
                        "step_id": step.get("step_id"),
                        "status": "blocked",
                        "tool": res.get("tool"),
                        "error": "approval required before write_file/patch",
                    },
                )
            else:
                log_event(
                    log_file,
                    {
                        "agent_id": m.get("agent_id"),
                        "step_id": step.get("step_id"),
                        "status": "ok",
                        "tool": res.get("tool"),
                        "output_path": str(res.get("output_path", "")),
                    },
                )
            context["completed_steps"].append(step.get("step_id"))
        process_handoffs(m, context)
        print(f"[{m['agent_id']}] wrote logs to {log_file}")
        executed += 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
