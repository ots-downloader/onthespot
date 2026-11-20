# OnTheSpot web UI

React, Vite and Tailwind CSS. Components live in `src/components/ui/`; pages live in `src/components/`.

```
npm install
npm run dev     # dev server
npm run lint    # type check + colour check
npm run build   # production build into dist/
```

## Theming

Every colour is defined once, in `src/index.css`, as a role: `surface`, `fg`, `line`, `accent`, `danger` and so on. Each role has a light value and a dark value. Tailwind turns each role into utilities, so markup says what a colour is for, not which colour it is:

```tsx
<div className="bg-surface text-fg border border-line">
  <p className="text-fg-muted">Muted text</p>
</div>
```

Rules:

- Use role utilities only. Do not write `dark:` variants, palette classes such as `text-neutral-500`, or hex values in components. `npm run lint` fails if you do.
- Service brand colours are data, not theme. They live in `src/lib/catalogServices.ts` and go on with inline `style`.
- Reach for a component in `src/components/ui/` before you style a raw `<button>`, `<input>` or `<select>`.

To add a role: add the variable to the light block, the dark block and the system (`prefers-color-scheme`) block in `src/index.css`, then map it in the `@theme inline` block.

To add a theme: add one more block of values under a new `[data-theme="..."]` selector. No component changes.

The user's choice (`system`, `light` or `dark`) is the `theme` setting in the backend config. `src/lib/theme.ts` applies it by setting `data-theme` on `<html>`, and keeps a copy in `localStorage` so the page paints in the right mode before the config loads.
