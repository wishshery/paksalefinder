export const DEFAULTS = Object.freeze({ q: '', brand: '', fabric: '', category: '', minOff: 0, maxPrice: 0, sort: 'discount', stock: true, saved: false });
const SORTS = new Set(['discount', 'saving', 'low', 'high']);
export function safeUrl(value) {
  try { const u = new URL(value); return u.protocol === 'https:' && !u.username && !u.password ? u.href : ''; } catch { return ''; }
}
export function classify(p) {
  const text = `${p.title || ''} ${p.category || ''}`.toLowerCase();
  if (/earrings?|earings?|bangles?|necklace|jewel|accessor|bracelet|handbag|hand bag|hair clip|\bpotli\b/.test(text)) return 'Accessories';
  if (/nail (colou?r|polish)|perfume|fragrance|lipstick|makeup/.test(text)) return 'Beauty';
  if (/unstitched|un-stitched|loose fabric|fabrics?\s+\d\s*piece/.test(text)) return 'Unstitched';
  if (/\bpret\b|ready.?to.?wear|\brtw\b|\bstitched\b|kurta|kurti|bottoms|trouser|culotte/.test(text)) return 'Ready to wear';
  return 'Clothing';
}
export function normalize(raw) {
  const seen = new Set();
  return (Array.isArray(raw) ? raw : []).flatMap(p => {
    if (!p || typeof p !== 'object') return [];
    const href = safeUrl(p.product_link), image = safeUrl(p.image), price = Number(p.sale_price), original = Number(p.original_price);
    if (!href || !image || !p.title || !p.brand || !Number.isFinite(price) || price <= 0 || !Number.isFinite(original) || original <= price || seen.has(href)) return [];
    seen.add(href);
    const category = classify(p);
    // Non-textile products must never inherit the scraper's default "Lawn" fabric.
    const fabric = ['Accessories', 'Beauty'].includes(category) ? '' : String(p.fabric || '');
    return [{ key: href, href, image, title: String(p.title), brand: String(p.brand), category, fabric,
      price, original, discount: Math.round((1 - price / original) * 100), saving: original - price,
      stock: p.availability === 'in_stock', haystack: `${p.brand} ${p.title} ${fabric} ${category}`.toLowerCase() }];
  });
}
export function readState(search) {
  const p = new URLSearchParams(search), number = key => { const n = Number(p.get(key)); return Number.isFinite(n) ? Math.max(0, n) : 0; };
  return { ...DEFAULTS, q: (p.get('q') || '').slice(0, 200), brand: p.get('brand') || '', fabric: p.get('fabric') || '',
    category: p.get('category') || '', minOff: Math.min(100, number('minOff')), maxPrice: number('maxPrice'),
    sort: SORTS.has(p.get('sort')) ? p.get('sort') : DEFAULTS.sort, stock: p.get('stock') !== 'all', saved: p.get('saved') === '1' };
}
export function stateQuery(state) {
  const p = new URLSearchParams();
  for (const key of ['q', 'brand', 'fabric', 'category', 'minOff', 'maxPrice']) if (state[key]) p.set(key, state[key]);
  if (state.sort !== DEFAULTS.sort) p.set('sort', state.sort);
  if (!state.stock) p.set('stock', 'all');
  if (state.saved) p.set('saved', '1');
  return p.toString();
}
export function filterProducts(products, state, saved = new Set()) {
  const words = state.q.toLowerCase().trim().split(/\s+/).filter(Boolean);
  const sort = { discount: (a,b) => b.discount-a.discount || b.saving-a.saving, saving: (a,b) => b.saving-a.saving,
    low: (a,b) => a.price-b.price, high: (a,b) => b.price-a.price }[state.sort];
  return products.filter(p => (!state.brand || p.brand.toLowerCase() === state.brand.toLowerCase()) && (!state.fabric || p.fabric === state.fabric)
    && (!state.category || p.category === state.category) && p.discount >= state.minOff && (!state.maxPrice || p.price <= state.maxPrice)
    && (!state.stock || p.stock) && (!state.saved || saved.has(p.key)) && words.every(w => p.haystack.includes(w))).sort(sort);
}
