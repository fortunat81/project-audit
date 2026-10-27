# project-audit

A Claude Code skill that audits a whole project (mobile app, website, backend, any stack). It detects what the project is, runs the free scanners that fit it, verifies their findings, adds a stack-specific review, and writes a report with scores, the tools behind each score, and proposed fixes. Nothing changes until you pick a fix.

## Install

The repo folder *is* the skill. Clone it into your Claude Code skills folder (Git Bash, Windows or macOS):

```bash
git clone https://github.com/fortunat81/project-audit ~/.claude/skills/project-audit
```

Update later:

```bash
cd ~/.claude/skills/project-audit && git pull
```

Install the free scanners the auditor uses (once; it skips anything already installed):

```bash
bash ~/.claude/skills/project-audit/scripts/scan.sh --install all
```

Then, in Claude Code inside any project, ask: "audit this project". If a project needs a scanner that's missing, Claude asks before installing it. The install never uses admin rights, and never installs Node.js, Flutter or Dart for you (it prints the download link instead). On Windows, winget may ask you to accept its terms the first time.

## What's inside

| Path | What it is |
|---|---|
| `SKILL.md` | The instructions Claude follows: tools first, then verification, review, scores, report |
| `scripts/scan.sh` | Detects the project's traits and runs the check modules |
| `scripts/checks/` | One module per kind of check (secrets, code security, dependencies, structure, types/lint, health, backend rules, exposed keys, CI, release readiness, native mobile, live site) |
| `reviews/` | Review checklists Claude loads per trait (AI, server code, web, Supabase, Firebase, mobile, payments, WordPress, personal data), plus `release-gate.md`: the launch checklist, the go/no-go verdict (don't launch / launch with limits / no blocking problems found) and the maintenance plan |
| `audit-accepted.tsv` | Optional, in the audited project: risks the owner knowingly accepted, each with a reason and an expiry date |
| `tests/` | Test scenarios with planted problems, and the runner that checks the auditor catches them |

## What you get after a scan

| File in `audit/<run>/` | What it is |
|---|---|
| `report.html` | One web page for the run: verdict, findings you can filter and search, what was and wasn't checked, scores, the launch checklist and the written report. Open it in any browser (`bash scripts/scan.sh --open`). No internet needed. |
| `digest.txt`, `findings.tsv` | A short digest and the list of findings with stable IDs |
| `AUDIT.md`, `scores.json` | The written report and its scores (written by Claude; checked by `--verify-report`) |
| `manifest.tsv`, `meta.txt` | What ran and how it ended; what exactly was audited |

**Approving fixes from the page.** The page lists the proposed fixes (`fixes.json`) with a tick box each, in English or French, light or dark. Run `bash scripts/scan.sh --serve` to open it from a small server that only listens on your own computer. Tick the fixes you approve, add a note if you like and click **Fix with Claude**: Claude Code starts in your project, makes a new git branch, applies the fixes one commit at a time, runs the scan again and writes `fix-report.md`. It never pushes. Safety: the server needs a random token, refuses requests from other websites, only accepts fixes listed in `fixes.json`, builds Claude's instructions itself, blocks `git push`, and refuses runs made with `--untrusted`. Without the server the page can still copy the approved fixes as a message for Claude or save them as `approved-fixes.json`.

Other commands: `--verdict` (the release verdict computed from the rules), `--verify-report`, `--all` (every project folder), `--untrusted`, `--check` / `--install`. The scripts that build the digest, the report check, the verdict and the web page are Python 3.8 or newer using only the standard library; the scanners themselves are separate programs.

## What runs code from the audited project

Most checks only read files. A few run the project's own code, which is fine for your own projects and risky for anyone else's. For code you didn't write, run `bash scripts/scan.sh --untrusted`: it skips the ones marked "runs project code", says so in the report, and removes secret-looking environment variables first. Network access stays on (rules and advisories are downloaded).

| Check | Reads files only | Runs project code | Notes |
|---|---|---|---|
| gitleaks, semgrep, osv-scanner, zizmor, ruff, mobsfscan, lizard | yes | | |
| madge, jscpd | yes | | Downloaded with `npx` at a pinned version; in untrusted mode a program of the same name inside the project's `node_modules` is not used |
| The script's own checks (exposed keys, release checks, backend rules, Astro code extraction) | yes | | |
| tsc | | yes | The project's own compiler and plugins |
| ESLint | | yes | Loads the project's config file and plugins |
| knip, expo-doctor | | yes | Load the project's config files |
| flutter analyze, dart analyze | | yes | Can run package build hooks |
| npm audit | | yes | Reads the project's `.npmrc` |
| pip-audit | | yes | Installs the packages to check them, which runs their setup code |
| `--install-deps` | | yes | Packages are installed with install scripts switched off, but it is still a download from the project's choice of packages |

## Test the auditor

```bash
bash tests/run-tests.sh --install          # install missing scanners first, then run everything
bash tests/run-tests.sh                    # all scenarios
bash tests/run-tests.sh expo-supabase-ai   # one scenario
KEEP=1 bash tests/run-tests.sh             # keep the temporary projects to inspect
```

Each scenario in `tests/scenarios/` is a small fake project with planted problems (an open database table, a paid AI key in app code, a committed `.env`, open Firebase rules, a secret in git history...) plus harmless look-alikes that must **not** be flagged. `expected.tsv` lists what the auditor must find. Results are PASS, FAIL, or UNTESTED (that scanner isn't installed on this machine).

Fake secrets are generated at test time, so no secret-looking values are ever committed here.

Run the tests after every change to the skill. When an audit of a real project misses something, add a scenario that reproduces it first, then fix the module until the test passes.

## Note

Auditing this repo itself will report the planted problems in `tests/scenarios/`. That's expected.
