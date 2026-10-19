const {test,before,after}=require('node:test'),assert=require('node:assert/strict');
const fs=require('fs'),path=require('path'),{chromium}=require('playwright');
const script=fs.readFileSync(path.resolve('static/arcade-navigation.js'),'utf8');
let browser;before(async()=>{browser=await chromium.launch()});after(async()=>{await browser.close()});
async function page(eligible=true){
 const c=await browser.newContext();await c.route('**/*',r=>r.fulfill({contentType:'text/html',body:'<title>QA external destination</title><p>QA fixture only</p>'}));
 const p=await c.newPage();await p.goto('https://machine.test/artist/');
 await p.setContent(`<head>${eligible?'<meta name="crispy-arcade-theatre-url" content="https://raggedya.github.io/aggits-video-jukebox/crispy-bits/test/theatre.html">':''}</head><body><main class="music-machine" data-project-type="channel_master"><a id="external" href="https://external.test/destination" rel="nofollow">External QA fixture</a><a id="internal" href="/comedy-arcade/">Back</a><a id="relative" href="#details">Details</a></main></body>`);
 await p.addScriptTag({content:script});return{c,p};
}
test('eligible external anchors use a new tab, safe rel and unchanged destination',async()=>{
 const {c,p}=await page();try{
  const a=p.locator('#external');assert.equal(await a.getAttribute('target'),'_blank');
  for(const rel of ['nofollow','noopener','noreferrer'])assert.ok((await a.getAttribute('rel')).split(' ').includes(rel));
  assert.equal(await a.getAttribute('href'),'https://external.test/destination');
 }finally{await c.close()}
});
test('dynamically inserted and updated external links get the same safe treatment',async()=>{
 const {c,p}=await page();try{
  await p.evaluate(()=>{const a=document.createElement('a');a.id='later';a.href='https://later.test/path';document.querySelector('main').append(a)});
  await p.waitForFunction(()=>document.querySelector('#later').target==='_blank');
  await p.locator('#internal').evaluate(a=>a.href='https://changed.test/path');
  await p.waitForFunction(()=>document.querySelector('#internal').target==='_blank');
 }finally{await c.close()}
});
test('same-origin return links and fragments keep ordinary same-tab navigation',async()=>{
 const {c,p}=await page();try{
  assert.equal(await p.locator('#internal').getAttribute('target'),null);assert.equal(await p.locator('#relative').getAttribute('target'),null);
  await p.locator('#internal').click();await p.waitForURL('https://machine.test/comedy-arcade/');assert.equal(c.pages().length,1);
 }finally{await c.close()}
});
test('external anchor really opens a new tab with no opener, preserving the original machine tab',async()=>{
 const {c,p}=await page();try{
  await p.evaluate(()=>window.qaMachineState='preserved');
  const opened=c.waitForEvent('page');await p.locator('#external').click();const q=await opened;await q.waitForLoadState('domcontentloaded');
  assert.equal(q.url(),'https://external.test/destination');assert.equal(await q.evaluate(()=>window.opener),null);
  assert.equal(p.url(),'https://machine.test/artist/');assert.equal(await p.evaluate(()=>qaMachineState),'preserved');
 }finally{await c.close()}
});
test('unlisted standalone products are not modified',async()=>{
 const {c,p}=await page(false);try{assert.equal(await p.locator('#external').getAttribute('target'),null);assert.equal(await p.locator('#external').getAttribute('rel'),'nofollow')}finally{await c.close()}
});
