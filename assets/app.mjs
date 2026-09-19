import { DEFAULTS, normalize, readState, stateQuery, filterProducts } from './catalog.mjs';

const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const money = n => `PKR ${Math.round(n).toLocaleString('en-PK')}`;
const count = n => n.toLocaleString('en-PK');
const products = normalize(window.LIVE_PRODUCTS), meta = window.LIVE_META || {};
const brands = [...new Set([...(Array.isArray(meta.brands_scraped) ? meta.brands_scraped : []), ...products.map(p => p.brand)])].sort();
const fabrics = [...new Set(products.map(p => p.fabric).filter(Boolean))].sort();
let state = readState(location.search), limit = 24, current = [], queryTimer, toastTimer;
let saved = new Set();
try { const stored = JSON.parse(localStorage.getItem('psf:saved:v1') || '[]'); if (Array.isArray(stored)) saved = new Set(stored.filter(v => typeof v === 'string')); } catch {}
function element(tag, className, text) { const el = document.createElement(tag); if (className) el.className = className; if (text !== undefined) el.textContent = text; return el; }
function icon(name) { const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'), use = document.createElementNS('http://www.w3.org/2000/svg', 'use'); svg.setAttribute('aria-hidden','true'); use.setAttribute('href',`#${name}`); svg.append(use); return svg; }
function option(select, value, text) { const o = new Option(text, value); select.add(o); }
brands.forEach(b => option($('#brandFilter'), b, b)); fabrics.forEach(f => option($('#fabricFilter'), f, f));
function selectedValue(el, value) {
  // Deep links may include a previous brand or a custom budget; preserve them visibly.
  if (![...el.options].some(o => o.value === String(value))) option(el, value, String(value));
  el.value = String(value);
}
function syncControls() {
  $('#searchBox').value = state.q;
  selectedValue($('#brandFilter'), state.brand); selectedValue($('#fabricFilter'), state.fabric);
  selectedValue($('#priceFilter'), state.maxPrice); selectedValue($('#discountFilter'), state.minOff);
  $('#stockOnly').checked = state.stock; $('#sortBy').value = state.sort;
  $$('[data-category]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.category === state.category)));
  $$('[data-saved]').forEach(b => b.setAttribute('aria-pressed', String(state.saved)));
  $('[data-shop-all]').setAttribute('aria-pressed', String(!state.saved));
}
function saveUrl(replace = false) {
  const query = stateQuery(state), url = `${location.pathname}${query ? '?' + query : ''}${location.hash}`;
  if (url !== location.pathname + location.search + location.hash) history[replace ? 'replaceState' : 'pushState'](null, '', url);
}
function update(patch, {replace = false, scroll = false} = {}) {
  clearTimeout(queryTimer);
  // Flush pending search text when another control is used immediately after typing.
  state = {...state, q: $('#searchBox').value.trim(), ...patch}; limit = 24; saveUrl(replace); syncControls(); render();
  if (scroll) $('#edit').scrollIntoView({block:'start',behavior:'auto'});
}
function toast(message) { clearTimeout(toastTimer); $('#toast').textContent = message; $('#toast').hidden = false; toastTimer = setTimeout(() => $('#toast').hidden = true, 3500); }
function savedCounts() {
  const visibleSaved = products.filter(p => saved.has(p.key)).length;
  $$('[data-saved-count]').forEach(el => el.textContent = visibleSaved);
  $$('[data-saved]').forEach(el => el.setAttribute('aria-label', `Saved finds (${visibleSaved})`));
}
function productCard(p, i) {
  const article = element('article', 'product'); article.dataset.key = p.key;
  const media = element('div','product-media'), imageLink = element('a','product-image-link');
  imageLink.href = p.href; imageLink.target = '_blank'; imageLink.rel = 'noopener noreferrer'; imageLink.setAttribute('aria-label',`View ${p.title} at ${p.brand} (opens in new tab)`);
  const img = element('img','product-image'); const imageURL = new URL(p.image);
  if (imageURL.hostname === 'cdn.shopify.com') { imageURL.searchParams.set('width','600'); img.srcset = [300,450,600,900].map(w => { const u = new URL(imageURL); u.searchParams.set('width', w); return `${u.href} ${w}w`; }).join(', '); img.sizes = '(max-width: 760px) calc((100vw - 53px) / 2), (min-width: 1500px) 260px, 30vw'; }
  img.src = imageURL.href; img.alt = `${p.brand} ${p.title}`; img.width = 600; img.height = 800; img.loading = i < 3 ? 'eager' : 'lazy'; img.decoding = 'async';
  img.addEventListener('error', () => { img.hidden = true; imageLink.textContent = 'Image unavailable · view at brand'; imageLink.style.cssText = 'display:flex;align-items:center;justify-content:center;padding:30px;text-align:center;font-size:13px'; }, {once:true});
  imageLink.append(img); media.append(imageLink, element('span','discount',`${p.discount}% off`));
  const save = element('button','save'); save.type = 'button'; save.dataset.save = p.key;
  save.setAttribute('aria-label',`${saved.has(p.key) ? 'Unsave' : 'Save'} ${p.title}`); save.setAttribute('aria-pressed',String(saved.has(p.key))); save.append(icon('heart')); media.append(save);
  if (!p.stock) media.append(element('span','sold-out','Sold out'));
  article.append(media, element('p','product-brand',p.brand));
  const heading = element('h3','product-title'), link = element('a', '', p.title); link.href=p.href; link.target='_blank'; link.rel='noopener noreferrer'; heading.append(link); article.append(heading);
  article.append(element('p','product-meta',[p.category,p.fabric].filter(Boolean).join(' · ')));
  const prices = element('div','prices'); prices.append(element('span','price',money(p.price)),element('s','was',money(p.original))); article.append(prices,element('p','saving',`Save ${money(p.saving)}`));
  const shop = element('a','shop',`View at ${p.brand}`); shop.href=p.href; shop.target='_blank'; shop.rel='noopener noreferrer'; shop.setAttribute('aria-label',`View ${p.title} at ${p.brand} (opens in new tab)`); shop.append(icon('arrow')); article.append(shop);
  return article;
}
function chips() {
  const row = $('#active-filters'); row.replaceChildren();
  const values = [['q',state.q && `“${state.q}”`],['brand',state.brand],['fabric',state.fabric],['category',state.category],['maxPrice',state.maxPrice && `Up to ${money(state.maxPrice)}`],['minOff',state.minOff && `${state.minOff}%+ off`],['stock',!state.stock && 'Including sold out'],['saved',state.saved && 'Saved finds']];
  values.filter(([,label]) => label).forEach(([key,label]) => { const b=element('button','filter-chip',label); b.type='button'; b.setAttribute('aria-label',`Remove filter: ${label}`); b.append(icon('close')); b.addEventListener('click',()=>{update({[key]:DEFAULTS[key]}); $('#results-title').setAttribute('tabindex','-1'); $('#results-title').focus({preventScroll:true});}); row.append(b); });
  const n = ['brand','fabric','minOff','maxPrice'].filter(k=>Boolean(state[k])).length + (state.stock ? 0 : 1);
  $('#mobile-filter-label').textContent = n ? `Filters (${n})` : 'Filters';
}
function render(append = false) {
  current = filterProducts(products,state,saved);
  $('#results-title').textContent = state.saved ? 'Your saved finds' : state.brand ? `${state.brand} on sale` : state.category ? `${state.category} on sale` : 'Finds worth a look';
  $('#result-count').textContent = `${count(current.length)} ${current.length === 1 ? 'find' : 'finds'}${state.stock ? ' · in stock at last check' : ' · including sold out'}`;
  $('#apply-filters').textContent = `Show ${count(current.length)} ${current.length === 1 ? 'find' : 'finds'}`;
  const grid = $('#grid'), before = append ? grid.children.length : 0;
  if (!append) grid.replaceChildren();
  if (!current.length) {
    const empty=element('div','empty'), title=element('h3','',state.saved && !saved.size ? 'Keep your favourites close' : 'No matching finds');
    empty.append(title,element('p','',state.saved && !saved.size ? 'Tap the heart on a product to save it here. No account needed.' : 'Try another brand, a higher budget or fewer filters.'));
    const reset=element('button','primary',state.saved ? 'Explore the sale' : 'Reset filters'); reset.addEventListener('click',()=>update({...DEFAULTS})); empty.append(reset);grid.append(empty);
  } else { const fragment=document.createDocumentFragment(); current.slice(before,limit).forEach((p,i)=>fragment.append(productCard(p,before+i)));grid.append(fragment); }
  $('#load-row').hidden = !current.length;
  $('#load-count').textContent=`Showing ${count(Math.min(limit,current.length))} of ${count(current.length)} finds`;
  $('#loadMore').hidden=limit>=current.length;
  savedCounts(); chips();
}
$('#grid').addEventListener('click',e=>{
  const button=e.target.closest('[data-save]'); if(!button)return;
  const key=button.dataset.save, saving=!saved.has(key); saving?saved.add(key):saved.delete(key);
  let persisted=true; try{localStorage.setItem('psf:saved:v1',JSON.stringify([...saved]));}catch{persisted=false;}
  if(state.saved&&!saving){const cards=$$('.product');const index=cards.indexOf(button.closest('.product'));render();const next=$$('.save')[Math.min(index,$$('.save').length-1)];(next||$('#results-title')).focus({preventScroll:true});}
  else{button.setAttribute('aria-pressed',String(saving));const p=products.find(p=>p.key===key);button.setAttribute('aria-label',`${saving?'Unsave':'Save'} ${p.title}`);savedCounts();}
  toast(persisted?(saving?'Saved to your finds':'Removed from saved finds'):'Saved for this visit. Browser storage is unavailable.');
});
$('#searchBox').addEventListener('input',()=>{clearTimeout(queryTimer);queryTimer=setTimeout(()=>update({q:$('#searchBox').value.trim()},{replace:true}),180);});
$('#search-form').addEventListener('submit',e=>{e.preventDefault();update({q:$('#searchBox').value.trim()},{replace:true,scroll:true});$('#searchBox').blur();});
$('#filters').addEventListener('submit',e=>e.preventDefault());
$('#filters').addEventListener('change',e=>{const input=e.target;const value=input.type==='checkbox'?input.checked:['maxPrice','minOff'].includes(input.name)?+input.value:input.value;update({[input.name]:value});});
$('#sortBy').addEventListener('change',e=>update({sort:e.target.value}));
$$('[data-category]').forEach(b=>b.addEventListener('click',()=>update({category:b.dataset.category, fabric:b.dataset.category==='Accessories'?'':state.fabric})));
$$('[data-reset]').forEach(b=>b.addEventListener('click',()=>update({...DEFAULTS,saved:state.saved})));
$$('[data-saved]').forEach(b=>b.addEventListener('click',()=>{const showSaved=!state.saved;update({...DEFAULTS,stock:!showSaved,saved:showSaved},{scroll:true});}));
$('[data-shop-all]').addEventListener('click',()=>update({...DEFAULTS},{scroll:true}));
$('#loadMore').addEventListener('click',()=>{const previous=limit;limit+=24;render(true);const next=$$('.product')[previous]?.querySelector('a');if(next)next.focus({preventScroll:true});});
window.addEventListener('popstate',()=>{clearTimeout(queryTimer);state=readState(location.search);limit=24;syncControls();render();});
window.addEventListener('storage',e=>{if(e.key!=='psf:saved:v1')return;try{const value=JSON.parse(e.newValue||'[]');saved=new Set(Array.isArray(value)?value:[]);render();}catch{}});
const mobile=matchMedia('(max-width: 760px)'), filterDialog=$('#filter-dialog');
function placeFilters(){if(!mobile.matches&&filterDialog.open)filterDialog.close();(mobile.matches?$('#mobile-filters'):$('#desktop-filters')).append($('#filters'));}
mobile.addEventListener('change',placeFilters);placeFilters();
function openDialog(dialog){dialog.showModal();document.body.classList.add('no-scroll');}
$$('[data-filter-open]').forEach(b=>b.addEventListener('click',()=>openDialog(filterDialog)));
$$('[data-method]').forEach(b=>b.addEventListener('click',()=>openDialog($('#method-dialog'))));
$$('dialog').forEach(dialog=>{dialog.querySelector('[data-close]').addEventListener('click',()=>dialog.close());dialog.addEventListener('close',()=>document.body.classList.remove('no-scroll'));dialog.addEventListener('click',e=>{if(e.target!==dialog)return;const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();});});
$('#apply-filters').addEventListener('click',()=>{filterDialog.close();$('#edit').scrollIntoView({block:'start',behavior:'auto'});});
brands.forEach(brand=>{const b=element('button','',brand);b.type='button';const active=products.filter(p=>p.brand===brand).length;b.append(element('small','',active?count(active):'No sale'));b.addEventListener('click',()=>update({...DEFAULTS,brand},{scroll:true}));$('#brand-directory').append(b);});
$('#brand-count').textContent=`(${brands.length})`;
const date=new Date(meta.last_updated);if(Number.isFinite(date.getTime())){$('#updated').dateTime=date.toISOString();$('#updated').textContent=date.toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'});$('#updated').title=date.toLocaleString('en-GB',{timeZone:'Asia/Karachi'})+' PKT';if(Date.now()-date.getTime()>48*60*60*1000){$('#catalog-warning').textContent='This catalogue was last updated more than two days ago. Check current prices and availability at the brand’s store.';$('#catalog-warning').hidden=false;}}else{$('#updated').textContent='Date unavailable';}
if(!products.length){$('#catalog-warning').textContent='The product catalogue is unavailable right now. Please try again later.';$('#catalog-warning').hidden=false;}
$('#results-title').setAttribute('tabindex','-1');syncControls();render();
