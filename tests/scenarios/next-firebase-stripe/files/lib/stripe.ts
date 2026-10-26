import Stripe from "stripe";
// Fine: server-only secret read from a server-only variable. Must NOT be flagged.
export const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);
