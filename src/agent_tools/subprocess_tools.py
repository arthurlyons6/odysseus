import asyncio
import os
import sys
import time
import collections
from typing import Optional, Callable, Awaitable, Tuple, Dict

from src.constants import MAX_OUTPUT_CHARS

DEFAULT_BASH_TIMEOUT = 60 * 60
DEFAULT_PYTHON_TIMEOUT = 60 * 60
DEFAULT_POWERSHELL_TIMEOUT = 120

PROGRESS_INTERVAL_S = 2.0
PROGRESS_TAIL_LINES = 12

async def _run_subprocess_streaming(
    proc: asyncio.subprocess.Process,
    *,
    timeout: float,
    progress_cb: Optional[Callable[[Dict], Awaitable[None]]] = None,
) -> Tuple[str, str, Optional[int], bool]:
    started = time.time()
    stdout_full: list[str] = []
    stderr_full: list[str] = []
    tail = collections.deque(maxlen=PROGRESS_TAIL_LINES)

    async def _reader(stream, full_buf, label: str):
        if stream is None:
            return
        while True:
            line = await stream.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").rstrip("\n")
            full_buf.append(decoded)
            if label == "err":
                tail.append(f"! {decoded}")
            else:
                tail.append(decoded)

    async def _progress_emitter():
        await asyncio.sleep(PROGRESS_INTERVAL_S)
        while True:
            if progress_cb:
                try:
                    await progress_cb({
                        "elapsed_s": round(time.time() - started, 1),
                        "tail": "\n".join(list(tail)),
                    })
                except Exception:
                    pass
            await asyncio.sleep(PROGRESS_INTERVAL_S)

    rd_out = asyncio.create_task(_reader(proc.stdout, stdout_full, "out"))
    rd_err = asyncio.create_task(_reader(proc.stderr, stderr_full, "err"))
    prog_task = asyncio.create_task(_progress_emitter()) if progress_cb else None

    timed_out = False
    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        timed_out = True
        try:
            proc.kill()
        except Exception:
            pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
        except Exception:
            pass
    except asyncio.CancelledError:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
        except Exception:
            pass
        for t in (rd_out, rd_err):
            t.cancel()
        if prog_task is not None:
            prog_task.cancel()
        raise
    finally:
        if prog_task is not None and not prog_task.done():
            prog_task.cancel()
            try:
                await prog_task
            except (asyncio.CancelledError, Exception):
                pass
        for t in (rd_out, rd_err):
            try:
                await asyncio.wait_for(t, timeout=1)
            except Exception:
                pass

    return (
        "\n".join(stdout_full),
        "\n".join(stderr_full),
        proc.returncode,
        timed_out,
    )


class BashTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        from src.tool_execution import _AGENT_WORKDIR, _truncate
        progress_cb = ctx.get("progress_cb")
        workspace = ctx.get("workspace")
        _subproc_env = ctx.get("subproc_env")
        proc = await asyncio.create_subprocess_shell(
            content,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_subproc_env,
            cwd=workspace or _AGENT_WORKDIR,
        )
        stdout, stderr, rc, timed_out = await _run_subprocess_streaming(
            proc,
            timeout=DEFAULT_BASH_TIMEOUT,
            progress_cb=progress_cb,
        )
        if timed_out:
            return {"error": f"bash: timed out after {DEFAULT_BASH_TIMEOUT}s — process killed", "exit_code": 124, "stdout": _truncate(stdout, MAX_OUTPUT_CHARS), "stderr": _truncate(stderr, MAX_OUTPUT_CHARS)}
        output = stdout.rstrip()
        err = stderr.rstrip()
        if err:
            output = (output + "\nSTDERR: " + err).strip() if output else "STDERR: " + err
        output = _truncate(output, MAX_OUTPUT_CHARS)
        return {"output": output or "(no output)", "exit_code": rc or 0}


class PythonTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        from src.tool_execution import _AGENT_WORKDIR, _truncate
        progress_cb = ctx.get("progress_cb")
        workspace = ctx.get("workspace")
        _subproc_env = ctx.get("subproc_env")
        proc = await asyncio.create_subprocess_exec(
            (sys.executable or "python"), "-I", "-c", content,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_subproc_env,
            cwd=workspace or _AGENT_WORKDIR,
        )
        stdout, stderr, rc, timed_out = await _run_subprocess_streaming(
            proc,
            timeout=DEFAULT_PYTHON_TIMEOUT,
            progress_cb=progress_cb,
        )
        if timed_out:
            return {"error": f"python: timed out after {DEFAULT_PYTHON_TIMEOUT}s — process killed", "exit_code": 124, "stdout": _truncate(stdout, MAX_OUTPUT_CHARS), "stderr": _truncate(stderr, MAX_OUTPUT_CHARS)}
        output = stdout.rstrip()
        err = stderr.rstrip()
        if err:
            output = (output + "\nSTDERR: " + err).strip() if output else "STDERR: " + err
        output = _truncate(output, MAX_OUTPUT_CHARS)
        return {"output": output or "(no output)", "exit_code": rc or 0}


class PowerShellTool:
    """First-class PowerShell execution routed through SubprocessTools."""

    BLOCKED_PREFIXES = (
        "remove-item ",
        "rm ",
        "del ",
        "rmdir ",
        "rd ",
        "clear-item ",
        "clv ",
        "format-",
        "out-null",
    )

    @staticmethod
    def _default_cwd() -> str:
        try:
            return os.path.expanduser("~")
        except Exception:
            return os.getcwd()

    @classmethod
    async def run_powershell(
        cls,
        script: str,
        *,
        cwd: Optional[str] = None,
        timeout: Optional[int] = None,
        extra_env: Optional[Dict[str, str]] = None,
    ) -> Dict:
        """Execute a PowerShell script and return structured output."""
        allow_destructive = False
        if isinstance(extra_env, dict):
            allow_destructive = bool(extra_env.get("ODYSSEUS_ALLOW_DESTRUCTIVE"))

        lowered = script.lower()
        if not allow_destructive:
            for prefix in cls.BLOCKED_PREFIXES:
                if lowered.startswith(prefix) or f" {prefix}" in lowered:
                    return {
                        "ok": False,
                        "exit_code": -1,
                        "stdout": "",
                        "stderr": "Blocked: destructive PowerShell pattern detected. "
                                  "Set allow_destructive=true (in extra_env) if intentional.",
                    }

        cmd = [
            "powershell",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd or cls._default_cwd(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=dict(os.environ, **(extra_env or {})),
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout or DEFAULT_POWERSHELL_TIMEOUT
            )
            return {
                "ok": proc.returncode == 0,
                "exit_code": proc.returncode or 0,
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
            }
        except asyncio.TimeoutError:
            return {
                "ok": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout or DEFAULT_POWERSHELL_TIMEOUT}s",
            }
        except FileNotFoundError:
            return {
                "ok": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "PowerShell runtime not found on PATH",
            }
        except Exception as exc:
            return {"ok": False, "exit_code": -1, "stdout": "", "stderr": str(exc)}

    async def execute(self, content: str, ctx: dict) -> dict:
        result = await self.run_powershell(
            content,
            cwd=ctx.get("workspace") or self._default_cwd(),
            extra_env=ctx.get("subproc_env"),
        )
        if not result.get("ok"):
            return {
                "error": result.get("stderr") or "PowerShell execution failed",
                "exit_code": result.get("exit_code", -1),
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
            }
        out = (result.get("stdout") or "").rstrip()
        err = (result.get("stderr") or "").rstrip()
        if err:
            out = (out + "\nSTDERR: " + err).strip() if out else "STDERR: " + err
        return {"output": out or "(no output)", "exit_code": result.get("exit_code", 0)}
