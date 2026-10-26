# Review checklist: AI features (trait `ai`)

Loaded when the project uses an AI SDK (OpenAI, Anthropic, Gemini, Vercel AI SDK, LangChain...).

## Always (quick and full)
- **Where is the AI key used?** Find every call to the AI provider. The key must only be read in server code (API route, serverless/edge function, backend). A key read in app or browser code, or via a client prefix (`EXPO_PUBLIC_`, `NEXT_PUBLIC_`, `VITE_`...), is **critical**: anyone can extract it and spend on your account. Cross-check `exposed-keys.txt`.
- **Can anyone call the AI endpoint?** For each server route that calls the AI: is there a login check, or for public chat widgets a per-visitor rate limit (per IP or session), a cap on message length, `max_tokens` on every call, and a daily spending cap or provider budget alert? A public route with none of these is **high**: it can drain the account.

## Full mode
- **AI output used unsafely:** model output inserted as HTML (`dangerouslySetInnerHTML`, `innerHTML`, `v-html`, `{@html}`), run as code (`eval`, `new Function`), used in SQL or shell commands, or used as a URL/redirect without checks.
- **User text steering the AI (prompt injection):** user messages, page content, emails or documents fed into a prompt that also has tools or private data. Check that tools the AI can call are limited to what that user may do, and that the system prompt holds nothing secret (assume it will leak).
- **Agent permissions:** if the AI can call tools or functions (send email, write to the database, book, refund), each action must check the user's own permissions server-side, and destructive actions need confirmation.
- **What gets sent to the AI provider:** personal data (names, addresses, health details) sent in prompts. Note it for the privacy policy.
- **Logging:** full prompts and replies logged with personal data or keys.
- **Cost and failure handling:** retries without limits, no timeout, no fallback message when the provider is down or rate-limits.
