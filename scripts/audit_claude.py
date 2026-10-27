#!/usr/bin/env python3
"""Shared helpers for starting the Claude Code program (`claude`) in print mode from the audit scripts.
Standard library only (Python 3.8+)."""
import os
import shutil
import subprocess
import sys


def find_claude():
    """The `claude` program: AUDIT_CLAUDE_BIN (used by tests), the PATH, or the usual install folder."""
    override = os.environ.get("AUDIT_CLAUDE_BIN")
    if override:
        return override
    found = shutil.which("claude")
    if found:
        return found
    for cand in (os.path.join(os.path.expanduser("~"), ".local", "bin", "claude.exe"),
                 os.path.join(os.path.expanduser("~"), ".local", "bin", "claude")):
        if os.path.exists(cand):
            return cand
    return None


def launch(prompt, cwd, allowed, blocked, log_path):
    """Starts claude -p with `prompt` on stdin, tools limited to `allowed`, output streamed to log_path.
    Returns the process. Raises RuntimeError when claude is not installed."""
    claude = find_claude()
    if not claude:
        raise RuntimeError("The Claude Code program ('claude') was not found on this computer.")
    args = ([sys.executable, claude] if claude.endswith(".py") else [claude]) + [
        "-p", "--permission-mode", "acceptEdits", "--output-format", "stream-json", "--verbose",
        "--allowedTools"] + list(allowed) + ["--disallowedTools"] + list(blocked)
    log = open(log_path, "w", encoding="utf-8", errors="replace", newline="\n")
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    proc = subprocess.Popen(args, cwd=cwd, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
    proc.stdin.write(prompt.encode("utf-8"))
    proc.stdin.close()
    return proc
