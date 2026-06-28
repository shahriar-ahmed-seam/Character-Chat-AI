# Character avatars (drop-in)

Drop a portrait here named by the character's **persona id** and the app uses it
automatically. If a file is missing, the app falls back to a gradient avatar with the
character's emoji + initials, so nothing breaks.

## Naming
- `elias.webp`, `luna.webp`, `sergeant_kane.webp` (match the `id` in
  `backend/app/personas/data/<character>.json`).

## Specs
- Format: **WebP** preferred (PNG/JPG also work — change the extension in
  `src/components/Avatar.jsx` if you don't use WebP).
- Size: **512×512**, square, subject centered (it's masked into a circle).
- Keep each file under ~150 KB for fast loading.
