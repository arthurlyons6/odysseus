# Upgrade Status

## Subagent Task Type

Subagent task type is now supported via `routes/task_routes.py`. Tasks can be created with `task_type=subagent`, bounded toolset, timeout, and `max_tool_calls`. Execution uses Hermes leaf subagents or a local bounded runner.
