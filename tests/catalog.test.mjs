import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { DEFAULTS, normalize, classify, safeUrl, readState, stateQuery, filterProducts } from '../assets/catalog.mjs';
const sample={brand:'Example',title:'Lawn kurta',image:'https://cdn.shopify.com/a.jpg',product_link:'https://example.com/product',sale_price:2000,original_price:4000,fabric:'Lawn',category:'Pret Dresses',availability:'in_stock'};
test('only valid sale products and HTTPS links are rendered; duplicate links collapse',()=>{
 const input=[sample,{...sample},null,{...sample,product_link:'javascript:alert(1)'},{...sample,product_link:'https://example.com/invalid',sale_price:Infinity},{...sample,product_link:'https://example.com/nosale',original_price:1000}];
 assert.equal(normalize(input).length,1);assert.equal(normalize(input)[0].discount,50);assert.equal(safeUrl('https://user:password@example.com'), '');
});
test('accessories and cosmetics do not receive textile fabric; ambiguous lawn suits are not invented as unstitched',()=>{
 assert.equal(normalize([{...sample,title:'Funky Chain Earings'}])[0].fabric,'');
 assert.equal(classify({...sample,title:'Nail Color'}),'Beauty');
 assert.equal(classify({...sample,title:'Unstitched printed lawn',category:'Lawn Suits'}),'Unstitched');
 assert.equal(classify({...sample,title:'3 piece printed loose fabric',category:'Lawn Suits'}),'Unstitched');
 assert.equal(classify({...sample,title:'Lawn suit',category:'Lawn Suits'}),'Clothing');
 assert.equal(classify({...sample,title:'Hand-Crochet Potli'}),'Accessories');
 assert.equal(classify({...sample,title:'Fabrics 2 Piece | Top and Bottom'}),'Unstitched');
});
test('search, budget, stock and saved filters compose without mutating source order',()=>{
 const products=normalize([sample,{...sample,title:'Silk kurta',fabric:'Silk',sale_price:3000,availability:'out_of_stock',product_link:'https://example.com/second'}]);
 assert.equal(filterProducts(products,DEFAULTS).length,1);
 assert.equal(filterProducts(products,{...DEFAULTS,q:'example lawn',maxPrice:2000}).length,1);
 assert.equal(filterProducts(products,{...DEFAULTS,q:'silk'}).length,0);
 assert.equal(filterProducts(products,{...DEFAULTS,stock:false,q:'silk'}).length,1);
 assert.equal(filterProducts(products,{...DEFAULTS,saved:true},new Set([products[0].key])).length,1);
 assert.equal(filterProducts(products,{...DEFAULTS,stock:false,sort:'high'})[0].price,3000);
 assert.equal(products[0].price,2000);
});
test('shareable URLs round trip all meaningful filters; malformed inputs have safe defaults',()=>{
 const state={...DEFAULTS,q:'lawn & silk',brand:'Sana Safinaz',fabric:'Lawn',maxPrice:5000,minOff:30,category:'Unstitched',stock:false,saved:true,sort:'low'};
 assert.deepEqual(readState(stateQuery(state)),state);
 assert.equal(readState('?sort=invalid&minOff=-4&maxPrice=no').sort,'discount');
 assert.equal(readState('?minOff=-4').minOff,0);
 assert.equal(stateQuery(DEFAULTS),'');
});
test('production catalogue and daily replacement contract remain intact',()=>{
 const html=fs.readFileSync(new URL('../index.html',import.meta.url),'utf8');
 const data=html.match(/window\.LIVE_PRODUCTS\s*=\s*\[.*?\];/s), meta=html.match(/window\.LIVE_META\s*=\s*\{.*?\};/s);
 assert.ok(data&&meta);const context={window:{}};vm.runInNewContext(data[0]+'\n'+meta[0],context);
 const products=normalize(context.window.LIVE_PRODUCTS);assert.ok(products.length>1000);assert.ok(context.window.LIVE_META.last_updated);
 assert.ok(products.every(p=>p.price>0&&p.original>p.price));
 assert.match(html,/data-ui="sale-finder-v2"/);
 assert.equal((html.match(/id="brandFilter"/g)||[]).length,1);
 assert.ok(!html.includes('__LIVE_DATA__'));
 const patched=html.replace(/window\.LIVE_PRODUCTS\s*=\s*\[.*?\];/s,'window.LIVE_PRODUCTS = [];').replace(/window\.LIVE_META\s*=\s*\{.*?\};/s,'window.LIVE_META = {};');
 assert.ok(patched.includes('src="./assets/app.mjs"'));
 assert.ok(patched.includes('data-ui="sale-finder-v2"'));
});
