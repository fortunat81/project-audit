# Review checklist: websites (trait `web`, or a live URL)

Loaded for website projects (Next.js, Astro, Vite/React, Vue, Svelte, static HTML, WordPress) and whenever a live URL was checked.

## Always (quick and full)
- **Live-site results:** if `live-site.txt` exists, report every FAIL. `.env` or `.git` publicly readable is **critical** (rotate everything in it). Missing https redirect is **high**. Missing headers are **medium**; give the exact header lines for the host in use (Vercel `vercel.json`, Netlify `_headers`, Next.js `next.config` headers, nginx, Apache `.htaccess`).
- **Forms:** every form that collects data (contact, booking, quote, newsletter): where does it go (email service, database, third-party form tool)? Is there spam/bot protection (rate limit, honeypot, captcha) and server-side validation?

## Full mode
- **XSS:** user or CMS content rendered as raw HTML (`dangerouslySetInnerHTML`, `innerHTML`, `v-html`, `{@html}`, `set:html`) without sanitising.
- **Third-party keys in the browser:** Google Maps, analytics, reCAPTCHA site keys are meant to be public; report them as "verify it's restricted to the client's domain", not as leaks.
- **Languages:** for multilingual sites (e.g. FR/EN), check `<html lang>`, `hreflang` links, and untranslated strings or images with text in one language only.
- **Lighthouse:** if `lighthouse.json` exists, report the four category scores (performance, accessibility, best practices, SEO) and the top 3 failed audits in each category below 90. Accessibility issues are quality findings; mention that they matter for clients.
- **Privacy basics:** a privacy policy link on pages with forms, cookie/analytics consent where trackers load, and consent text in every language the site uses (in Quebec, Law 25 applies; this is a code check, not legal advice).
- **Dependencies loaded from CDNs:** scripts from third-party CDNs without integrity attributes.
