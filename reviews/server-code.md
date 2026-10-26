# Review checklist: server code (trait `server-code`)

Loaded when the project has API routes, serverless functions or a backend framework.

## Always (quick and full)
- **Unprotected routes:** list the API routes/functions. For each one that reads or changes user data, is there an authentication check on the server (not only hidden buttons in the UI)? A route that returns or changes other users' data without a check is **critical**.
- **Ownership checks:** for routes taking an id (`/bookings/:id`), does the server confirm the record belongs to the caller? Missing checks let users read others' data by changing the id.

## Full mode
- **Injection:** request data (body, query, params, headers) reaching SQL strings, shell commands, file paths, `eval`, or HTML without escaping or parameterised queries. Trace across files; the free Semgrep doesn't.
- **Validation:** request bodies used without schema validation (zod, yup, pydantic...), especially amounts, ids, emails and URLs.
- **Rate limits and abuse:** login, sign-up, password reset, contact and booking endpoints without rate limits or bot protection.
- **CORS:** `Access-Control-Allow-Origin: *` combined with cookies or auth headers.
- **Errors:** stack traces or database errors returned to the client.
- **Secrets in code or logs:** keys hard-coded instead of read from environment variables; tokens, passwords or personal data written to logs.
- **Webhooks:** incoming webhooks (Stripe, etc.) must verify the signature.
- **Scalability:** queries inside loops, lists without pagination, heavy work inside the request, no caching for repeated expensive calls.
