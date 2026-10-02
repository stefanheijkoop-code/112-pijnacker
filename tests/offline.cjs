// Run: node --test tests/offline.cjs (Node 18+; no dependencies).
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const root=path.join(__dirname,'..');
function harness(){
 const stores=new Map(),handlers={},requests=[];let response,writeFails=false;
 const cache=()=>({match:async key=>stores.get(key)?.clone(),put:async(key,r)=>{if(writeFails)throw Error('quota');stores.set(key,r.clone())},addAll:async files=>{for(const f of files){requests.push(f.url);stores.set(f.url,new Response('shell'));}}});
 const ctx={self:{registration:{scope:'https://example.test/112-pijnacker/'},clients:{claim:async()=>{}},addEventListener:(name,fn)=>handlers[name]=fn},caches:{open:async()=>cache(),keys:async()=>['unrelated','112-pijnacker-data-v1'],delete:async()=>{}},URL,Request,Response,Headers,AbortController,setTimeout:fn=>{ctx.abort=fn;return 1},clearTimeout:()=>{},fetch:async()=>{if(response instanceof Error)throw response;return response.clone()}};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(root,'service-worker.js'),'utf8'),ctx);
 return {ctx,stores,requests,handlers,setResponse:r=>response=r,failWrites:()=>writeFails=true,run:()=>vm.runInContext('loadData()',ctx)};
}
const data=(updated='2026-10-02T20:24:04+02:00',incidents=[{title:'Melding',service:'Brandweer'}])=>new Response(JSON.stringify({updated,incidents}),{headers:{'Content-Type':'application/json'}});
test('shell paths exist, install caches project assets and navigation falls back',async()=>{
 const h=harness();let installed;h.handlers.install({waitUntil:p=>installed=p});await installed;
 for(const u of h.requests)assert(fs.existsSync(path.join(root,new URL(u).pathname.replace('/112-pijnacker/',''))));
 assert(h.requests.some(u=>u.endsWith('marker-icon-2x.png')));
 let result;h.handlers.fetch({request:{url:'https://example.test/112-pijnacker/',method:'GET',mode:'navigate'},respondWith:p=>result=p});assert.equal(await(await result).text(),'shell');
});
test('valid data cached; network/HTTP/JSON/schema errors preserve saved data',async()=>{
 const h=harness();h.setResponse(data());let r=await h.run();assert.equal(r.headers.get('X-112-Data-Stored'),'yes');
 for(const fail of [Error('offline'),new Response('error',{status:500}),new Response('{bad'),new Response('{"incidents":[]}')]){h.setResponse(fail);r=await h.run();assert.equal(r.headers.get('X-112-Data-Source'),'cache');assert.equal((await r.json()).incidents.length,1);}
});
test('older data cannot replace newer; valid empty dataset accepted',async()=>{
 const h=harness();h.setResponse(data());await h.run();h.setResponse(data('2026-10-01T12:00:00Z'));assert.equal((await h.run()).headers.get('X-112-Data-Source'),'cache');
 h.setResponse(data('2026-10-03T12:00:00Z',[]));assert.deepEqual((await(await h.run()).json()).incidents,[]);
});
test('no saved dataset yields 503; quota failure preserves valid online response',async()=>{
 const h=harness();h.setResponse(Error('offline'));assert.equal((await h.run()).status,503);h.failWrites();h.setResponse(data());const r=await h.run();assert.equal(r.status,200);assert.equal(r.headers.get('X-112-Data-Stored'),'no');
});
test('inline scripts parse and no CDN runtime dependency remains',()=>{
 const html=fs.readFileSync(path.join(root,'index.html'),'utf8');for(const match of html.matchAll(/<script>([\s\S]*?)<\/script>/g))new vm.Script(match[1]);assert(!html.includes('unpkg.com'));assert(html.includes('if(!markers)return'));assert(html.includes('aria-live="polite"'));
});
