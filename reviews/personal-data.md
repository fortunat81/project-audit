# Review checklist: personal, health or payment data

Loaded when the user says the project handles health, payment or personal data, or when you find forms or tables collecting names, addresses, phone numbers, emails, health or location data.

## Always (quick and full)
- **Map the data:** list each kind of personal data collected, where it's stored (which table, service or inbox), and who can read it. Put this map in the report; it's useful for the privacy policy.
- **Access:** the storage for that data is covered by the backend rules (RLS, Firebase rules) or server checks. Flag any path where it's readable without being the owner or an admin.

## Full mode
- **Sent to third parties:** analytics, crash reporting, AI providers, email/SMS services. Each must be in the privacy policy.
- **Logged:** personal data in logs, error reports or analytics events.
- **Kept forever:** no deletion path (user request or retention period).
- **In transit and at rest:** https everywhere; sensitive fields (health) not stored in plain device storage.
- **Privacy policy and consent:** a reachable privacy policy; consent where required; text in every language the product uses. Quebec's Law 25 applies to personal information of people in Quebec (this is a code check, not legal advice; suggest a professional review before launch).
- **Health data:** extra care; recommend a professional review before launch.
