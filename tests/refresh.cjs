const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const html=fs.readFileSync(require('node:path').join(__dirname,'../index.html'),'utf8');
const code=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1].split('\nchips();')[0];
function harness(failLive=false){
 const calls=[],messages=[];let redraws=0;
 const btn={classList:{add(){},remove(){}},setAttribute(){}};
 const ctx={console,URL,Date,AbortController,setTimeout,clearTimeout,updated:{textContent:''},offlineReady:{textContent:''},navigator:{onLine:true,serviceWorker:{controller:{postMessage:m=>messages.push(m)},getRegistration:async()=>({update:async()=>{}})}},document:{getElementById:()=>btn},fetch:async url=>{calls.push(url);if(failLive&&url.includes('/api/refresh'))throw Error('offline');return new Response(JSON.stringify({updated:url.includes('/api/refresh')?'2026-10-11T22:00:00+02:00':'2026-10-11T18:13:00+02:00',incidents:[{title:'Nieuwe melding',service:'Ambulance'}],partial:false}));}};
 vm.createContext(ctx);vm.runInContext(code,ctx);vm.runInContext('render=()=>{};tiles={redraw:()=>onRedraw()}',Object.assign(ctx,{onRedraw:()=>redraws++}));
 return {ctx,calls,messages,get redraws(){return redraws},run:()=>vm.runInContext('load(true)',ctx)};
}
test('manual refresh fetches live sources, stores result and redraws map',async()=>{
 const h=harness();await h.run();assert.equal(h.calls.length,1);assert(h.calls[0].includes('/api/refresh?t='));assert.equal(h.messages[0].type,'STORE_LIVE_DATA');assert.equal(h.redraws,1);assert(h.ctx.updated.textContent.includes('Bronnen gecontroleerd'));
});
test('live failure reloads saved JSON and explicitly reports failed source refresh',async()=>{
 const h=harness(true);await h.run();assert.equal(h.calls.length,2);assert(h.calls[1].startsWith('./data.json?t='));assert.equal(h.messages.length,0);assert(h.ctx.updated.textContent.includes('Nieuwe bronmeldingen ophalen mislukt'));
});
