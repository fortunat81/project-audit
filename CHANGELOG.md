# Changelog

What changed, newest first. The audit records the commit it ran with (`methodology_commit` in `meta.txt`),
so a report can always be matched to the version of the tool that made it.

## 2026-10-27

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
