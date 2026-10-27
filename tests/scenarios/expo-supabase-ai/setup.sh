# Runs inside the fresh test repo after the first commit. Fake secrets are made here,
# at test time, so nothing secret-looking is ever committed to the real repository.
# 1) A secret that exists only in git history (added, then deleted)
echo "export const awsKey = \"AKIA$(rand_upper 16)\";" > lib/old-config.ts
git add lib/old-config.ts && git commit -qm "add config"
git rm -q lib/old-config.ts && git commit -qm "remove config"
# 1b) NAME=value secrets in a plain notes file that was committed and then removed (gitleaks' own
#    rules miss these), plus a template that holds placeholders and must NOT be flagged
printf 'RESEND_API_KEY=%s\nDEPLOY_TOKEN=%s\n' "$(rand_alnum 40)" "$(rand_alnum 40)" > notes.txt
git add notes.txt && git commit -qm "add notes"
git rm -q notes.txt && git commit -qm "remove notes"
printf 'STRIPE_SECRET_KEY=your_key_here\nSUPABASE_SERVICE_ROLE_KEY=changeme-changeme-changeme\n' > .env.example
git add .env.example && git commit -qm "add env template"
# 2) A secret in a staged-but-not-committed file
echo "export const ghToken = \"ghp_$(rand_alnum 36)\";" > lib/config.ts
git add lib/config.ts
# 3) A .env that is not git-ignored, with a client-visible secret name
printf 'EXPO_PUBLIC_OPENAI_API_KEY=placeholder\nSTRIPE_SECRET=sk_live_%s\n' "$(rand_alnum 32)" > .env
