import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker,{validEvent,SLUG} from '../src/machine-stats.js';
const payload=()=>({slug:SLUG,eventId:crypto.randomUUID(),sessionId:crypto.randomUUID(),name:'page_view',videoId:''});
const req=(body,origin='https://raggedya.github.io',method='POST')=>new Request('https://example.com/api/events',{method,headers:{origin},...(method==='POST'?{body:JSON.stringify(body)}:{})});
test('accepted event fields, types, exact machine and safe video ID',()=>{
  assert.ok(validEvent({...payload(),slug:'football',name:'spin'}));
  for(const name of ['page_view','spin','play_click','share_click','spotify_click'])assert.ok(validEvent({...payload(),name}));
  for(const override of [{slug:'another-machine'},{name:'watched_video'},{videoId:'invalid'},{eventId:'bad'},{sessionId:'bad'},{email:'not-permitted'}])assert.ok(!validEvent({...payload(),...override}));
});

test('public counts expose only machine-scoped spins; cache avoids repeated database reads',async()=>{
 let calls=0;const saved=new Map();globalThis.caches={default:{async match(key){return saved.get(key.url)?.clone();},async put(key,value){saved.set(key.url,value);}}};
 const waits=[];const ctx={waitUntil(p){waits.push(p);}};
 const DB={prepare(sql){calls++;assert.equal(sql,"SELECT COUNT(*) AS count FROM machine_statistics WHERE slug=?1 AND event_name='spin'");return {bind(slug){return {async first(){return {count:slug===SLUG?391:7};}};}};}};
 try{
  const get=slug=>new Request(`https://example.com/api/spins?slug=${slug}`);
  const response=await worker.fetch(get(SLUG),{DB},ctx);assert.deepEqual(await response.json(),{count:391});
  assert.equal(response.headers.get('cache-control'),'public, max-age=30');await Promise.all(waits);
  assert.deepEqual(await (await worker.fetch(get(SLUG),{DB},ctx)).json(),{count:391});assert.equal(calls,1);
  assert.deepEqual(await (await worker.fetch(get('football'),{DB},ctx)).json(),{count:7});
  assert.equal((await worker.fetch(get('../bad'),{DB},ctx)).status,400);
  assert.equal((await worker.fetch(get('uncached'),{},ctx)).status,503);
  assert.equal((await worker.fetch(new Request('https://example.com/api/report'),{DB})).status,404);
 }finally{delete globalThis.caches;}
});
test('origin, method, missing body, malformed and oversized rejection do not reach DB',async()=>{
  const env={DB:{prepare(){throw Error('must not reach DB');}}};
  assert.equal((await worker.fetch(req(payload(),'https://evil.test'),env)).status,403);
  assert.equal((await worker.fetch(req(null,undefined,'GET'),env)).status,405);
  assert.equal((await worker.fetch(req({bad:'field'}),env)).status,400);
  assert.equal((await worker.fetch(req('x'.repeat(2048)),env)).status,413);
  assert.equal((await worker.fetch(new Request('https://example.com/api/events',{method:'POST',headers:{origin:'https://raggedya.github.io'},body:'{'}),env)).status,400);
});
test('parameterised insertion, idempotence, rate bounds and private report surface',async()=>{
  const seen=new Set();let values;
  const DB={prepare(sql){assert.match(sql,/INSERT OR IGNORE/);assert.match(sql,/<60/);assert.match(sql,/<600/);return {bind(...args){values=args;return {async run(){const changes=seen.has(args[0])?0:1;seen.add(args[0]);return {meta:{changes}};}};}};}};
  const body=payload();
  assert.equal((await worker.fetch(req(body),{DB})).status,204);
  assert.deepEqual(values,[body.eventId,body.sessionId,SLUG,'page_view','']);
  assert.equal((await worker.fetch(req(body),{DB})).status,202);
  assert.equal((await worker.fetch(new Request('https://example.com/api/report'),{DB})).status,404);
});
test('storage failure is safe and preflight restricted',async()=>{
  assert.equal((await worker.fetch(req(payload()),{})).status,503);
  const response=await worker.fetch(req(null,undefined,'OPTIONS'),{});
  assert.equal(response.status,204);assert.equal(response.headers.get('access-control-allow-origin'),'https://raggedya.github.io');
});
