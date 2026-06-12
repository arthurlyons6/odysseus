@echo off
REM Gracefully restart the running Odysseus server (port 7000).
REM Uses the standard launcher: a full restart preserves ChromaDB, state, and logs.

call start_odysseus.bat
