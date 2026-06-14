# C:\Users\13464\odysseus\scripts\install_mcp_tools.py
"""Install a single MCP-tool assignment block into each Odysseus agent manifest."""

from pathlib import Path

AGENT_TOOL_ASSIGNMENTS = {
    "church-intel-001": {
        "mcp": "web_search",
        "tools": ["web_search", "read_file", "write_file"],
        "reason": "needs web research and report output only",
    },
    "pe-diligence-001": {
        "mcp": "web_search",
        "tools": ["web_search", "read_file", "write_file", "patch"],
        "reason": "research and memo generation with schema patching",
    },
    "industrial-research-001": {
        "mcp": "web_search",
        "tools": ["web_search", "read_file", "write_file", "patch"],
        "reason": "market scan and scoring with doc generation",
    },
    "exec-synthesis-001": {
        "mcp": "file_io",
        "tools": ["read_file", "write_file", "patch"],
        "reason": "synthesis only, no shell",
    },
    "pc-performance-001": {
        "mcp": "terminal",
        "tools": ["terminal", "read_file", "write_file"],
        "reason": "needs host checks and safer local ops",
    },
    "research-001": {
        "mcp": "web_search",
        "tools": ["web_search", "read_file", "write_file"],
        "reason": "research tasks and memo output",
    },
}

MANIFEST_DIR = Path(r"C:\Users\13464\odysseus\data\async_agents")


def _render_block(assignment: dict) -> str:
    return (
        "  \"mcp_tools\": {\n"
        f"    \"server\": \"{assignment['mcp']}\",\n"
        f"    \"allowed\": {assignment['tools']},\n"
        f"    \"note\": \"{assignment['reason']}\"\n"
        "  },\n"
    )


def _write_batch() -> None:
    for manifest_path in sorted(MANIFEST_DIR.glob("*.json")):
        text = manifest_path.read_text(encoding="utf-8")
        agent_id = manifest_path.stem
        assignment = AGENT_TOOL_ASSIGNMENTS.get(agent_id)
        if assignment is None:
            continue

        block = _render_block(assignment)

        body = text
        if '"mcp_tools":' in body:
            head, rest = body.split('"mcp_tools":', 1)
            try:
                _, tail = rest.split('",', 1)
                tail = tail.split('"', 1)[1]
                tail = tail.split('"', 1)[1]
                tail = tail.split('"', 1)[1]
            except Exception:
                tail = rest
            text = head + block + tail
        else:
            text = text.replace('"task_queue": [', block + '"task_queue": [', 1)

        manifest_path.write_text(text, encoding="utf-8")
        print(f"assigned {agent_id} -> {assignment['mcp']}: {assignment['tools']}")


if __name__ == "__main__":
    _write_batch()
