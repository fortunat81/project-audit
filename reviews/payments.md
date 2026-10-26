# Review checklist: payments (trait `payments`)

## Always (quick and full)
- **Secret keys:** Stripe secret keys (`sk_live_`, `sk_test_`), restricted keys and webhook secrets only in server code. A secret key in app or browser code is **critical**.
- **Prices from the client:** the amount charged must be computed on the server from product ids, never taken from the request body.

## Full mode
- Webhooks verify the signature and handle each event once (idempotency), and the order is only marked paid from the webhook, not from the client's "success" redirect.
- Refund and admin payment actions check the caller is allowed.
- No card data handled directly (use Checkout, Elements or Payment Sheet).
- Test keys and live keys not mixed between environments.
