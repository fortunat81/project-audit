# Changelog

What changed, newest first. The audit records the commit it ran with (`methodology_commit` in `meta.txt`),
so a report can always be matched to the version of the tool that made it.

## 2026-10-27

- Fixes from the first real-use test report (each has a test that failed first):
  - The scan now warns when its own copy has no git history or is behind GitHub (`tool_copy=` in `meta.txt`); an old copy used to run silently.
  - Tools installed with `pip install --user` are found on Windows even when pip's Scripts folder is not on PATH (including the Microsoft Store Python).
  - Severity now matches the Supabase checklist: a table with no row-level security is critical, an open write policy is high; a file shows its worst finding.
- Maintainability rounds 1 to 3: trait detection is now tables plus small functions; `--status`, the
  release-readiness check, the live-site check, the Markdown renderer, the digest text and the scan run
  were each split into small functions, with new tests (`modes-check`, `helpers-check`).
- Tests: the parallel runner downloads the pinned npx tools once before starting (parallel downloads
  corrupted npm's cache on CI), and the stand-in tools are put on `PATH` in one path style.

## 2026-10 (earlier)

- The scanner moved from bash to Python (`scan.sh` is now a small launcher); same results, one engine.
- A web page per run (`report.html`) in English and French, light and dark, with tick-to-fix and a local
  server that starts Claude Code on the ticked fixes.
- Release gate: a 43-item checklist with a go / no-go verdict (`audit_verdict.py`).
- Tests run in parallel with a time limit per test; GitHub Actions runs them on Linux, macOS and Windows.
