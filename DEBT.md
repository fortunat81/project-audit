# Known debt

What is not as good as it should be, in priority order. Remove an item when it is fixed. Nothing here
is broken; these are things that make the project harder to change or less proven than it looks.

## Unproven

1. **The Claude steps from a clean start.** The written steps in `SKILL.md` have been followed by the
   author's own session, not by a fresh one. Run a fresh session on a project it hasn't seen and compare.
   Also measure how much scores move when the same project is audited twice.
2. **"Fix with Claude" on a real project.** The server and the prompt are tested with a stand-in for
   `claude`, plus one real harmless call to confirm the flags. A real fix run (Windows permissions for the
   test and lint scripts) has not happened.
3. **macOS and Windows beyond this machine.** GitHub Actions now runs the quick set on all three; keep it green.

## Design debt

4. **Scanner and rule versions drift.** Python scanners are installed unpinned and Semgrep downloads its
   rules at scan time. Idea: a pinned tools environment (`scan.sh --setup`, `uv`) and saved rules.
5. **Long functions in our own code.** The audit tool's own scan flags a few (for example `render_markdown`,
   `compute_verdict`, `check_report`, `write_outputs`). Split when touching them.
6. **French and English tables are written by hand.** `tests/translate_test.py` checks both exist and match
   the numbering; it can't judge the translation quality.

## Process

7. **No review of the local server by someone else.** It starts something that edits files. It has a token,
   host/origin checks, a fixed prompt and blocked commands, but deserves one independent read.
8. **Real-world coverage is small.** Four of the owner's projects and three public repos so far. Each new
   project has found one or two gaps; expect that to continue.
9. **Self-audit noise.** Auditing this repo reports the planted problems in `tests/scenarios/` (expected).
