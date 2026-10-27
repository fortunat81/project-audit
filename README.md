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
