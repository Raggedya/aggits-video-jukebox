const {test}=require('node:test');
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../static/machine-statistics.js'),'utf8');
const url='https://raggedya.github.io/aggits-video-jukebox/crispy-bits/doug-anthony-allstars/';

test('all product shells, including Trivia and Football, count one accepted state transition per machine',async()=>{
 const browser=await chromium.launch();try{
  for(const kind of ['business','music','tourism','banjo','channel-master','white-label','love-my-locals','football','trivia-machine']){
   const page=await browser.newPage();const events=[];
   await page.route('**/*',r=>{
    if(r.request().method()==='POST'){events.push(r.request().postDataJSON());return r.fulfill({status:204});}
    if(r.request().url().includes('/api/spins?'))return r.fulfill({json:{count:0}});
    return r.fulfill({contentType:'text/html',body:`<main class="music-machine" data-project-type="${kind}" data-machine-state="IDLE"><section class="machine-controls"></section><footer>Crispy Bits</footer></main>`});
   });
   await page.goto(url.replace('doug-anthony-allstars',kind));await page.addScriptTag({content:source});
   await page.waitForFunction(()=>document.querySelector('[data-spin-counter]')?.textContent==='0 reel spins');
   await page.evaluate(()=>document.querySelector('.music-machine').dataset.machineState='SPINNING');
   await page.waitForTimeout(50);
   assert.equal(events.length,1);assert.equal(events[0].slug,kind);assert.equal(events[0].name,'spin');
   await page.close();
  }
 }finally{await browser.close();}
});
test('DAAS collector actions, disabled controls, spin deduplication and session reload',async()=>{
 const browser=await chromium.launch();try{
  const page=await browser.newPage(),events=[];
  await page.route('**/*',async r=>{
   if(r.request().method()==='POST'){events.push(r.request().postDataJSON());return r.fulfill({status:204});}
   return r.fulfill({contentType:'text/html',body:'<div class="music-machine" data-machine-state="IDLE"><button data-action="play">Play</button><button data-action="share">Share</button><button data-action="shop">Spotify</button></div>'});
  });
  await page.goto(url);await page.evaluate(()=>{window.CrispyBitsMachine={getState:()=>({selectedId:'6waA8RXdDB8'})};});
  await page.addScriptTag({content:source});await page.addScriptTag({content:source});
  for(const action of ['play','share','shop'])await page.locator(`[data-action="${action}"]`).click();
  await page.evaluate(()=>{document.querySelector('.music-machine').dataset.machineState='SPINNING';});
  await page.waitForTimeout(50);
  await page.evaluate(()=>{document.querySelector('.music-machine').dataset.machineState='SPINNING';document.querySelector('[data-action="play"]').disabled=true;document.querySelector('[data-action="play"]').click();});
  await page.waitForTimeout(50);
  assert.deepEqual(events.map(e=>e.name),['page_view','play_click','share_click','spotify_click','spin']);
  assert.ok(events.every(e=>e.videoId==='6waA8RXdDB8'));
  assert.equal(new Set(events.map(e=>e.eventId)).size,5);
  await page.reload();await page.addScriptTag({content:source});await page.waitForTimeout(50);
  assert.equal(events.length,6);assert.equal(events[0].sessionId,events[5].sessionId);
 }finally{await browser.close();}
});
test('local previews never collect; other machines collect only spins',async()=>{
 const browser=await chromium.launch();try{
  const page=await browser.newPage();let posts=0;
  await page.route('**/*',r=>{if(r.request().method()==='POST')posts++;return r.fulfill({contentType:'text/html',body:'<div class="music-machine"></div>'});});
  for(const location of ['http://localhost:1234/',url.replace('doug-anthony-allstars','another-machine')]){
   await page.goto(location);await page.addScriptTag({content:source});
  }assert.equal(posts,0);
 await page.evaluate(()=>document.querySelector('.music-machine').dataset.machineState='SPINNING');
 await page.waitForTimeout(100);assert.equal(posts,1);
 }finally{await browser.close();}
});

test('counter formats aggregate, isolates slug, hides failures and never polls or increments rejected spins',async()=>{
 const browser=await chromium.launch();try{
  const page=await browser.newPage();let reads=0,posts=0,fail=false,accepted=false;
  await page.route('**/*',r=>{
   if(r.request().method()==='POST'){posts++;return r.fulfill({status:accepted?204:202});}
   if(r.request().url().includes('/api/spins?')){reads++;assert.ok(r.request().url().endsWith('slug=football'));return r.fulfill({status:fail?503:200,contentType:'application/json',body:JSON.stringify({count:12345})});}
   return r.fulfill({contentType:'text/html',body:'<main class="music-machine" data-machine-state="IDLE"><section class="machine-controls">Controls</section><footer>CRISPY BITS</footer></main>'});
  });
  await page.goto(url.replace('doug-anthony-allstars','football'));await page.addScriptTag({content:source});
  await page.waitForFunction(()=>document.querySelector('[data-spin-counter]')?.textContent==='12,345 reel spins');
  assert.equal(await page.locator('[data-spin-counter]').getAttribute('title'),'Recorded reel spins since tracking was enabled for this machine.');
  for(const viewport of [{width:390,height:844},{width:1320,height:900}]){
   await page.setViewportSize(viewport);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  }
  await page.evaluate(()=>document.querySelector('.music-machine').dataset.machineState='SPINNING');await page.waitForTimeout(100);
  assert.equal(posts,1);assert.equal(reads,1);
  await page.evaluate(()=>document.querySelector('.music-machine').dataset.machineState='IDLE');await page.waitForTimeout(20);
  accepted=true;fail=true;
  await page.evaluate(()=>document.querySelector('.music-machine').dataset.machineState='SPINNING');
  await page.waitForFunction(()=>document.querySelector('[data-spin-counter]').hidden);
  assert.equal(reads,2);assert.equal(posts,2);
 }finally{await browser.close();}
});
