# Milestones 7B–7C Frontend Typed Client + Legacy Freeze

## 7B

- Extended `shared/api/v1Client.ts` with `post` / `put` / `patch`.
- New Admin settings feature module: `frontend/admin/features/settings/settingsApi.js` uses v1 only.
- Existing critical E2E / unit toolchain unchanged.

## 7C

- `frontend/legacy-api-allowlist.json` freezes known `fetch('/api/...')` call sites.
- Vitest `legacy-api-allowlist.test.js` fails if new unlisted legacy fetches appear.
- Current allowlist size: 2 (admin members list/export). New features must not add entries without explicit reduction plan.

## Known gaps

- Large admin.js / app.js residual legacy modules migrate feature-by-feature.
- Full members/export v1 write remains follow-up.
