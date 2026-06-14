import asyncio
import json
import httpx

APP_URL = "http://127.0.0.1:7000"

PROMPT = json.dumps({
    "instructions": "Audit the local skills library at ~/.hermes/skills for dead links, stale version references, duplicate names, missing validation, and missing YAML frontmatter fields. Produce a concise markdown report.",
    "subagent_meta": {
        "max_steps": 8,
        "timeout": 360,
        "allowed_tools": ["web_search", "read_file", "terminal", "patch", "search_files"]
    }
})

async def main() -> None:
    payload = {
        "name": "Skills Audit — dead links / stale / duplicates",
        "task_type": "subagent",
        "prompt": PROMPT,
        "owner": "local",
        "schedule": "weekly",
        "scheduled_time": "02:00",
        "scheduled_day": 6,
        "notifications_enabled": True,
        "max_steps": 8,
        "run_count": 0,
    }
    async with httpx.AsyncClient(base_url=APP_URL, timeout=30) as c:
        r = await c.post("/api/tasks", json=payload)
        print("status:", r.status_code)
        try:
            print(r.json())
        except Exception:
            print(r.text[:1000])

if __name__ == "__main__":
    asyncio.run(main())
