# Release gate: launch checklist, verdict and maintenance plan

Loaded in Step 6 of every audit. It turns the scan and the review into one plain answer: **can this go live?** The list is short on purpose: it covers the mistakes behind most real breaches of websites and small apps, not every control a large organisation would track. Finishing it is a finish line; it is not a promise that nothing can go wrong.

Built from OWASP ASVS (application requirements), OWASP Top 10 and NIST SSDF (secure delivery and patching), trimmed to what a small agency or solo builder can verify. Area names below follow ASVS wording.

## Who checks each item

| Tag | Meaning | How to mark it |
|---|---|---|
| **[T]** | A tool or script checks it | Take the result from `manifest.tsv` / `release-checks.txt`. Pass if the row is clean, fail if confirmed, **not verified** if the tool didn't run. |
| **[C]** | Claude checks it by reading the code | Only after doing the matching step in `reviews/`. If that step wasn't done (quick mode), mark **not verified**. |
| **[Y]** | Only the owner can confirm it (dashboards, accounts, habits) | Ask once, in plain words. Unanswered means **not verified**. Never assume. |

Marks: ✅ pass · ❌ fail · ⚠️ partly · ❓ not verified · ➖ not applicable (say why).

## Pick the level

| Level | What it is | Items that apply |
|---|---|---|
| **1 Website** | Marketing site, brochure, blog, no logins or payments | All items without a level tag, plus those tagged `L1` |
| **2 App with users** | Has logins, a database, payments through a provider, or an API | Everything for Level 1 plus items tagged `L2` |
| **3 Sensitive** | Health, financial or other regulated data; several customers sharing one system with private data | Everything for Level 2 plus `L3`. The tool cannot certify this level: say a specialist review is needed before launch |

Choose from the traits and the Step 1 answers (login, `supabase`, `firebase`, `payments`, `server-code` → at least Level 2; "handles health, payment or personal data" → ask whether Level 3 applies). Say which level you used and why.

## The checklist

Items marked `L2` or `L3` apply from that level up.

### A. Secrets and settings
1. **No secrets in the code, its history or committed `.env` files.** [T] `gitleaks`, `gitleaks-uncommitted`, `env-files`. *(Data protection)*
2. **No secret key inside the website or app people download.** [T] `exposed-keys`, plus Claude's read of `EXPO_PUBLIC_` / `NEXT_PUBLIC_` use. *(Data protection)*
3. **Debug mode off, no test logins left.** [T] `release-checks`: DEBUG-ON, TEST-ACCOUNT. *(Configuration)*
4. **Test and live keys are separate, and any key that ever leaked was replaced.** [Y]

### B. Login and sessions (`L2`)
5. **Login is handled by a trusted service (Supabase Auth, Firebase Auth, Clerk, Auth0...) or passwords are hashed with a modern method.** [C] *(Authentication)* `L2`
6. **Login and password reset are rate-limited; reset links are single-use and short-lived.** [C] *(Authentication)* `L2`
7. **Session cookies are Secure and HttpOnly; logout really ends the session.** [T] `release-checks`: COOKIE-FLAGS, then [C]. *(Session management)* `L2`
8. **Admin accounts use two-step sign-in.** [Y] `L2`

### C. Who can see what
9. **Every table, bucket and route checks who is asking** (Row Level Security, Firebase rules, server checks). [T] `supabase-rls`, `firebase-rules`, then [C] with the stack checklists. *(Access control)* `L2`
10. **Changing an ID in a URL or request never shows someone else's data.** [C] by reading the routes; [Y] try it with two test accounts before launch. *(Access control)* `L2`
11. **Admin features are blocked on the server, not just hidden in the screen.** [C] *(Access control)* `L2`
12. **One customer can never reach another customer's data** (several customers in one system). [C] and a specialist test. *(Access control)* `L3`

### D. Money and server logic
13. **Prices, permissions and "paid" status are decided on the server, never taken from the browser.** [C] with `reviews/payments.md`. *(Business logic)* `L2`
14. **Payment and other webhooks verify their signature and are handled once.** [C] *(API)* `L2`
15. **Everything users type is checked on the server; no raw text goes into queries, commands or pages.** [T] `semgrep`, then [C] input tracing in full mode. *(Validation)* `L2`
16. **The server answers only the websites it should** (no open CORS unless it is a public read-only API). [T] `release-checks`: CORS-OPEN. *(API)*
17. **Expensive or abusable actions are limited** (AI calls, emails, exports, sign-ups). [C] `L2`

### E. Data and privacy
18. **Only the personal data you need is collected, and the privacy notice matches what the site does.** [C] with `reviews/personal-data.md`, then [Y]. *(Data protection)*
19. **Traffic uses HTTPS and the browser protections are set.** [T] `live-site` (when a URL was given), else [Y]. *(Configuration)*
20. **Logs and error reports contain no passwords, tokens or personal data.** [C] *(Logging)* `L2`
21. **Test environments use fake data.** [Y] `L2`

### F. Packages and build
22. **A lockfile is committed, so installs are repeatable.** [T] `release-checks`: NO-LOCKFILE.
23. **No known serious vulnerabilities in packages.** [T] `osv-scanner`, `npm-audit`, `pip-audit`.
24. **Every package name is real and expected** (AI tools sometimes invent names). [Y] until an automatic check exists.
25. **Automated workflows can't be tricked by outside text.** [T] `zizmor`.
26. **The code repository is private unless meant to be public, and sign-in to it uses two-step verification.** [Y]

### G. Hosting
27. **Databases and storage are not open to the public internet or to "anyone signed in".** [T] `supabase-rls`, `firebase-rules`, then [Y] for rules set only in the dashboard. *(Configuration)*
28. **Containers don't run as root and use a pinned image version.** [T] `release-checks`: DOCKER-ROOT, DOCKER-UNPINNED.
29. **The runtime (Node, Python) still gets security fixes.** [T] `release-checks`: RUNTIME-EOL.
30. **Staging and preview sites are not public, or hold no real data.** [Y]

### H. Before it goes live
31. **There are automated tests, including some for login and access rules.** [T] `release-checks`: NO-TESTS; access-rule tests [C]. `L2`
32. **Checks run on every change.** [T] `release-checks`: NO-CI.
33. **The main journeys were tried on the live build** (sign up, pay, reset password, contact form). [Y]
34. **Source maps and debug files aren't published.** [T] `release-checks`: SOURCEMAPS-COMMITTED.

### I. After launch
35. **Backups are on and a restore was tried once.** [Y] `L2`
36. **Errors and downtime reach a person** (error tracking, uptime alerts). [Y] `L2`
37. **There is a way back** (previous version can be restored quickly). [Y] `L2`
38. **Someone owns updates:** who patches packages, how often, and what happens when a serious vulnerability is announced. [Y]
39. **Handover note exists:** where the keys live, who has access, what to do if one leaks, who owns the domain and hosting. [Y]

### J. Added at Level 3 (a specialist is needed, the tool can't confirm these)
40. Written threat model of the sensitive flows. `L3`
41. Independent penetration test of the live system, with fixes retested. `L3`
42. Restore exercise with measured recovery time; incident plan with contacts. `L3`
43. Legal review of privacy and data-location obligations for the clients' regions. `L3`

### Stack add-ons
Also mark the items in `reviews/wordpress.md` (WordPress or other CMS sites), `reviews/mobile.md`, `reviews/ai.md` and the rest that were loaded. Treat a **critical** item there like an item in A–D.

## The verdict

Look at confirmed findings (after Step 3) and the checklist, in this order. The first rule that matches wins.

| Verdict | When | What to say |
|---|---|---|
| 🔴 **Don't launch yet** | A confirmed critical or high finding; or ❌ on any item in A, B, C or D that applies at this level | Name the blockers. They must be fixed, or knowingly accepted by the owner in writing (see "Accepted risks"). |
| 🟡 **Launch with limits** | No blockers, but some required items are ⚠️ or ❓, or medium findings remain | List each open item with who must do it and a date. Say plainly that ❓ means "not checked", not "fine". |
| 🟢 **No blocking problems found** | No blockers, and every required item is ✅ or ➖ with a reason | Say what was and wasn't covered. Never write "secure" or "no vulnerabilities". |

Rules that always hold:
- A good score never turns a 🔴 into a 🟡.
- Missing evidence is ❓, never ✅. A tool that didn't run leaves its items ❓.
- In quick mode most [C] items stay ❓, so a quick audit can end in 🟡 but never 🟢 for Level 2 or 3. Say so.
- Level 3 never reaches 🟢 without the J items done by a specialist.

## Finding record

Give every finding in the report an ID (`F-001`...) and these fields: where (file and line or setting), what is wrong in plain words, severity (critical / high / medium / low, judged by what an attacker gains and how easy it is, not only a tool's number), who fixes it, by when, how to check the fix worked, status (open / fixed and retested / accepted).

Suggested deadlines (the owner can change them): critical, stop and fix now; high, before launch; medium, within 30 days; low, at the next planned update.

## Accepted risks

A risk the owner chooses to live with goes in `audit-accepted.tsv` in the project root (committed, so it survives; tab-separated, one per line, first line is the header):

```
finding	reason	accepted_by	expires
semgrep:app/legacy.py	internal tool, behind VPN	Fortu	2027-03-01
```

In Step 3, a finding that matches a line whose `expires` date has not passed moves to "accepted" in the report, still listed, with the reason and expiry. After the date it counts as open again. Never add a line yourself; only the owner decides. A critical secret finding can't be accepted.

## Maintenance plan (always include this section)

Write it in plain words from what the audit found:
- **Re-check dependencies** monthly (or when the news names a package you use): `bash scan.sh` in quick mode is enough.
- **Re-run the full audit** before each major release, after changing login, payments or the database layout, and when `--status` says so.
- **End-of-support dates:** from `release-checks.txt` and the lockfile, list runtimes and frameworks that lose security fixes in the next 12 months.
- **Who does it:** the owner named in checklist item 38, or "not decided yet" if unanswered.
- **If a key leaks:** replace the key first, then clean the code, then check the provider's logs for misuse.
