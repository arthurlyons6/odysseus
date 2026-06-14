import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.expanduser("~/odysseus"))

from core.database import SessionLocal
from src.task_scheduler import ScheduledTask, TaskScheduler


async def main() -> None:
    db = SessionLocal()
    try:
        scheduler = TaskScheduler(db=db)
        task = ScheduledTask(
            id="audit-skill-run-002",
            name="Skill Audit",
            owner="local",
            prompt=json.dumps({
                "instructions": "Audit the local skills library for dead links, stale version references, and duplicate names. Produce a concise markdown report.",
                "subagent_meta": {
                    "max_steps": 6,
                    "timeout": 240,
                    "allowed_tools": ["web_search", "read_file", "terminal", "patch"]
                }
            }),
            model="default",
            session_id="audit-skill-run-002",
        )
        db.add(task)
        db.commit()
        print("Starting subagent task:", task.id)
        out = await scheduler._execute_subagent_task(task, run_id="run-002")
        print(out[:5000])
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
