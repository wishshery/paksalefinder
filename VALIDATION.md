# Responsive Sale Finder validation

Validated locally on 19 September 2026 against the repository's real embedded product catalogue.

- Five Node tests pass: sale-record validation and safe URLs; category/fabric normalization; combined filters and sorting; URL round trips; catalogue/template preservation.
- Two offline Python tests pass: the daily updater leaves the new layout untouched and still finds both data injection targets exactly once.
- Browser checks at 320, 360, 390, 412, 768, 1024 and 1440 CSS pixels: no document horizontal overflow; two product columns on phones, desktop sidebar and three columns on tablet/desktop. Four columns at 1500px and above.
- Exercised combined brand/search/budget filters, accessory metadata, sort order, history Back restoration, save/unsave controls, saved-item persistence after reload, mobile filter dialog, no-results reset, and pagination from 24 to 48 products.
- No JavaScript console errors observed during those checks.

The browser checks use Chromium at responsive viewport sizes. Physical Android devices and Safari on an iPhone were not available for testing. Mobile implementation uses native form controls and dialogs, 16px mobile form fields, at least 44px action targets, safe-area padding and dynamic viewport height with fallbacks. A physical-device smoke test remains recommended before a broad release.

The existing price/stock dataset and refresh timestamp are preserved. Historical price verification is not claimed. The UI suppresses fabric on identifiable non-textile products, but source catalogue classification and regional prices still depend on the existing scraper.
