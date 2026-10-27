#!/usr/bin/env python3
"""Runs one command with a time limit and puts its output in a file.

    python with_timeout.py <seconds> <output-file> <command> [args...]

If the command is still running after the time limit, it and everything it started are stopped, and a
"FAIL ... timed out" line is added to the output file, so a hung test fails clearly instead of blocking
the whole run. The exit code is the command's (124 on timeout). Standard library only (Python 3.8+).
"""
import os
import signal
import subprocess
import sys


def stop_tree(proc):
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass


def main(argv):
    if len(argv) < 4:
        sys.stderr.write(__doc__)
        return 2
    seconds, out_path, command = float(argv[1]), argv[2], argv[3:]
    name = os.path.splitext(os.path.basename(out_path))[0]
    with open(out_path, "wb") as out:
        kwargs = {} if os.name == "nt" else {"start_new_session": True}
        proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, **kwargs)
        try:
            return proc.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            stop_tree(proc)
            proc.wait()
            out.write(("\n  FAIL      %s timed out after %d seconds and was stopped\n" % (name, seconds)).encode())
            return 124


if __name__ == "__main__":
    sys.exit(main(sys.argv))
