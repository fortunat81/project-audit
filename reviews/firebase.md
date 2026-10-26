# Review checklist: Firebase (trait `firebase`)

The Firebase config in the app is public by design. Security Rules decide who can read and write.

## Always (quick and full)
- **`firebase-rules.txt`:** "OPEN TO EVERYONE" is **critical** for any data that isn't meant to be public. "TEST MODE" rules are **high**: they either already expired (app broken) or were extended (still open).
- **"Any signed-in user" rules:** `request.auth != null` alone lets every user read and change everyone's data. **High** for personal data; the rule should compare `request.auth.uid` with the document owner.
- **Rules not in the repo:** say they couldn't be checked from code and tell the user to check the Rules tab in the Firebase console.

## Full mode
- Cloud Functions apply the server-code checklist (callable functions must check `context.auth`).
- Storage rules for user uploads (size and type limits, owner-only access).
- Firebase Admin SDK credentials (service account JSON) committed or bundled in client code: **critical**.
- App Check enabled for public apps that call paid APIs through Firebase.
