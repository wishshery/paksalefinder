# PakSaleFinder

Static, responsive fashion-sale discovery site for GitHub Pages. No frontend build or dependencies are required.

## Preview and checks

With Node.js 22 or newer:

```sh
node scripts/serve.mjs
node --test tests/catalog.test.mjs
python tests/test_updater.py
```

Open http://127.0.0.1:4173. Use an HTTP server instead of opening index.html directly: the application uses JavaScript modules.

## Files and daily updates

- `index.html`: semantic page shell, metadata and daily `LIVE_PRODUCTS` / `LIVE_META` data.
- `assets/site.css`: desktop grid, responsive layouts, mobile navigation, safe-area spacing, reduced motion.
- `assets/app.mjs`: rendering, native modal filter sheet, local saved items, URL filters and browser-history restoration.
- `assets/catalog.mjs`: validation, category normalization, search and sort logic.
- `scraper/update.py`: existing daily catalogue update. The `data-ui="sale-finder-v2"` marker disables obsolete structural patches; data injection continues unchanged.

Preserve the data assignments and template marker during future edits. Do not replace the catalogue with sample records. Prices are brand-supplied comparisons, not verified historical lows. Clearly identifiable non-textile products have fabric suppressed in the presentation layer; unknown clothing remains unclassified rather than being assumed unstitched.

Saved items are local to the browser and keyed by product URL, so daily numeric ID changes do not break them. Storage failure keeps favourites for the current visit and displays a notice. No account or checkout is added.

## Deployment

Publish the repository root using the existing GitHub Pages setup. Keep `CNAME`, all `assets/` files, and the daily updater together. Check the deployed site after publishing. This is a responsive website for desktop/mobile browsers, not a native Android or iOS app.
