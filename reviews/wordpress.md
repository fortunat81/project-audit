# Review checklist: WordPress and other CMS sites (trait `wordpress`)

Loaded for WordPress projects. For another CMS (Drupal, headless CMS) apply the same ideas to its own plugins and admin.

## Always (quick and full)
- **Plugins and themes:** list them (`wp-content/plugins`, `wp-content/themes`). Flag any that are abandoned, not from the official directory or a known vendor, or not used. Unused ones should be deleted, not just switched off. Known-vulnerable ones are **high**.
- **Credentials:** `wp-config.php` must not be committed with real database passwords or salts. Committed secrets are **critical**.
- **Uploads can't run code:** nothing in `wp-content/uploads` should be executable (no `.php` files there; the server should refuse to run PHP from that folder).
- **Debug off:** `WP_DEBUG` is not true in production (the `release-checks` file reports this).

## Full mode
- Admin: default `admin` username removed, strong passwords, two-step sign-in for administrators, login attempts limited.
- Roles: editors and authors have only the permissions they need; former staff and agencies have no accounts.
- Forms: contact and booking forms have spam protection and don't email raw input to unexpected places.
- Exposure: staging copies, backup archives (`.zip`, `.sql`) and directory listings are not publicly reachable; XML-RPC is off unless used.
- Caching and CDN rules never serve one visitor's private page to another.
- Updates: core, plugins and themes are on supported versions, and someone is named to apply updates (see the maintenance plan).
- Ownership: domain, hosting and WordPress admin accounts are in the client's name, or the handover note says exactly who holds them.
