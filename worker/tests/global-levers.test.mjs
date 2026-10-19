import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import worker,{counterOrigin} from '../src/machine-stats.js';
import {localDatabase} from '../../tools/local_lever_database.mjs';
const origin='https://raggedya.github.io';
const event=(slug='test-music',name='spin')=>({eventId:crypto.randomUUID(),sessionId:crypto.randomUUID(),slug,name,videoId:''});
const request=body=>new Request('https://test.local/api/events',{method:'POST',headers:{origin},body:JSON.stringify(body)});
const total=async DB=>(await worker.fetch(new Request('https://test.local/api/lever-total'),{DB})).json();
test('real SQL deduplicates retries, consecutive accepted actions and concurrent visitors; only spins count',async()=>{
 const {sqlite,DB}=localDatabase();try{
  const one=event();assert.equal((await worker.fetch(request(one),{DB})).status,204);
  assert.equal((await worker.fetch(request(one),{DB})).status,202);
  assert.equal((await total(DB)).count,'1');
  await Promise.all(Array.from({length:30},(_,i)=>worker.fetch(request(event(i%2?'test-business':'test-music')),{DB})));
  assert.equal((await total(DB)).count,'31');
  for(const name of ['page_view','play_click','share_click','spotify_click','cta_click'])await worker.fetch(request(event('test-music',name)),{DB});
  assert.equal((await total(DB)).count,'31');
  for(const slug of ['comedy-arcade','test-standalone','test-shared-theatre','test-banjo','test-tourism','test-football'])await worker.fetch(request(event(slug)),{DB});
  assert.equal((await total(DB)).count,'37');
 }finally{sqlite.close()}
});
test('migration backfills only historic unique spins once and keeps counts when machines/events are removed',()=>{
 const db=new DatabaseSync(':memory:');try{
  for(const n of ['0004_machine_statistics.sql','0005_all_machine_spins.sql','0006_all_machine_details.sql'])db.exec(fs.readFileSync(path.resolve('worker/migrations',n),'utf8'));
  db.exec("INSERT INTO machine_statistics(event_id,session_id,slug,event_name,received_at) VALUES('old-spin','session','removed-machine','spin',1792298288),('old-view','session','removed-machine','page_view',1792298280)");
  const migration=fs.readFileSync('worker/migrations/0007_global_lever_total.sql','utf8');db.exec(migration);db.exec(migration);
  assert.equal(db.prepare('SELECT total FROM network_lever_total').get().total,1);
  assert.equal(db.prepare('SELECT since FROM network_lever_total').get().since,1792298288);
  db.exec("DELETE FROM machine_statistics WHERE slug='removed-machine'");
  assert.equal(db.prepare('SELECT total FROM network_lever_total').get().total,1);
 }finally{db.close()}
});
test('lifetime total survives connection/backend restart and exceeds six digits exactly',async()=>{
 const folder=fs.mkdtempSync(path.join(os.tmpdir(),'lever-sql-test-')),filename=path.join(folder,'local-test.sqlite');
 let local=localDatabase(filename);
 try{
  local.sqlite.exec('UPDATE network_lever_total SET total=999999');await worker.fetch(request(event()),{DB:local.DB});
  assert.equal((await total(local.DB)).count,'1000000');local.sqlite.close();
  const sqlite=new DatabaseSync(filename);try{assert.equal(sqlite.prepare('SELECT total FROM network_lever_total').get().total,1000000);
   sqlite.exec('UPDATE network_lever_total SET total=9007199254740993');
   assert.equal(sqlite.prepare('SELECT CAST(total AS TEXT) AS total FROM network_lever_total').get().total,'9007199254740993');
  }finally{sqlite.close()}
 }finally{fs.rmSync(filename,{force:true});fs.rmdirSync(folder)}
});
test('global endpoint is aggregate only, bounded-cache/CORS, read-only, and missing schema never fabricates zero',async()=>{
 const {sqlite,DB}=localDatabase();try{
  const result=await worker.fetch(new Request('https://test.local/api/lever-total'),{DB});
  assert.equal(result.headers.get('cache-control'),'public, max-age=2');assert.equal(result.headers.get('access-control-allow-origin'),origin);
  const body=await result.json();assert.deepEqual(Object.keys(body).sort(),['asOf','count','since']);
  for(const privateField of ['sessionId','eventId','slug','videoId','events'])assert.ok(!(privateField in body));
  for(const method of ['POST','PUT','DELETE'])assert.equal((await worker.fetch(new Request('https://test.local/api/lever-total',{method}),{DB})).status,405);
  assert.equal((await worker.fetch(new Request('https://test.local/api/lever-total?slug=test'),{DB})).status,400);
  assert.equal((await worker.fetch(new Request('https://test.local/api/lever-total'),{})).status,503);
  assert.equal((await total(DB)).count,'0');
 }finally{sqlite.close()}
});
test('spin-specific rate allowance admits legitimate repeat spins without a duplicate click counter',async()=>{
 const {sqlite,DB}=localDatabase();try{
  const sessionId=crypto.randomUUID();
  for(let i=0;i<75;i++)assert.equal((await worker.fetch(request({...event(),sessionId}),{DB})).status,204);
  assert.equal((await total(DB)).count,'75');
  assert.equal(sqlite.prepare("SELECT COUNT(*) AS count FROM machine_statistics WHERE event_name='spin'").get().count,75);
 }finally{sqlite.close()}
});
test('read-only global totals support localhost/LAN previews but never broaden write access',async()=>{
 const {sqlite,DB}=localDatabase();try{
  for(const origin of ['http://localhost:8769','http://127.0.0.1:5000','http://192.168.0.79:8769','http://10.0.0.2:9000','http://172.16.0.2:5000']){
   const response=await worker.fetch(new Request('https://test.local/api/lever-total',{headers:{origin}}),{DB});
   assert.equal(response.status,200);assert.equal(response.headers.get('access-control-allow-origin'),origin);
   assert.equal((await worker.fetch(new Request('https://test.local/api/events',{method:'POST',headers:{origin},body:JSON.stringify(event())}),{DB})).status,403);
  }
  for(const origin of ['https://evil.test','http://172.32.0.1:90','http://192.168.1.1.evil.test','null'])assert.equal(counterOrigin(origin),null);
 }finally{sqlite.close()}
});
test('trigger installation precedes backfill so a concurrent installation-time event is not lost or doubled',()=>{
 const sqlite=new DatabaseSync(':memory:');try{
  for(const name of ['0004_machine_statistics.sql','0005_all_machine_spins.sql','0006_all_machine_details.sql'])sqlite.exec(fs.readFileSync('worker/migrations/'+name,'utf8'));
  const migration=fs.readFileSync('worker/migrations/0007_global_lever_total.sql','utf8'),i=migration.indexOf('INSERT OR IGNORE INTO network_lever_total');
  sqlite.exec(migration.slice(0,i));
  sqlite.exec("INSERT INTO machine_statistics(event_id,session_id,slug,event_name) VALUES('during-install','session','test','spin')");
  sqlite.exec(migration.slice(i));assert.equal(sqlite.prepare('SELECT total FROM network_lever_total').get().total,1);
  sqlite.exec("INSERT INTO machine_statistics(event_id,session_id,slug,event_name) VALUES('after-install','session','test','spin')");
  assert.equal(sqlite.prepare('SELECT total FROM network_lever_total').get().total,2);
 }finally{sqlite.close()}
});
