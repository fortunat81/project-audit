# PLANTED: a .env.local committed to git, with a client-visible secret name
printf 'NEXT_PUBLIC_STRIPE_SECRET_KEY=placeholder\n' > .env.local
git add .env.local && git commit -qm "add env"
