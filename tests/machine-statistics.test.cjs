const {test}=require('node:test');
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../static/machine-statistics.js'),'utf8');
const url='https://raggedya.github.io/aggits-video-jukebox/crispy-bits/doug-anthony-allstars/';

test('Arcade landing records exactly one page view, never machine spins or counter reads',async()=>{
 const browser=await chromium.launch();try{
  const page=await browser.newPage(),events=[];let counterReads=0;
  await page.route('**/*',r=>{
   if(r.request().method()==='POST'){events.push(r.request().postDataJSON());return r.fulfill({status:204})}
   if(r.request().url().includes('/api/spins'))counterReads++;
   return r.fulfill({contentType:'text/html',body:'<main class="machine-stack"><button>Lever</button></main>'});
  });
  await page.goto(url.replace('doug-anthony-allstars','comedy-arcade'));await page.addScriptTag({content:source});await page.addScriptTag({content:source});
  await page.locator('button').click();await page.waitForTimeout(50);
  assert.equal(events.length,1);assert.equal(events[0].slug,'comedy-arcade');assert.equal(events[0].name,'page_view');assert.equal(events[0].videoId,'');assert.equal(counterReads,0);assert.equal(await page.locator('[data-spin-counter]').count(),0);
 }finally{await browser.close()}
});

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
   assert.equal(events.length,2);assert.ok(events.every(e=>e.slug===kind));assert.deepEqual(events.map(e=>e.name),['page_view','spin']);
   await page.close();
  }
 }finally{await browser.close();}
});
test('DAAS collector actions, disabled controls, spin deduplication and session reload',async()=>{
 const browser=await chromium.launch();try{
  const page=await browser.newPage(),events=[];
  await page.route('**/*',async r=>{
   if(r.request().method()==='POST'){events.push(r.request().postDataJSON());return r.fulfill({status:204});}
   if(r.request().url().endsWith('/machine.json'))return r.fulfill({json:{customerConfig:{primaryAction:{destinationURL:'https://open.spotify.com/album/example'}}}});
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
test('local previews never collect; other machines collect page views and spins',async()=>{
 const browser=await chromium.launch();try{
  const page=await browser.newPage();let posts=0;
  await page.route('**/*',r=>{if(r.request().method()==='POST')posts++;return r.fulfill({contentType:'text/html',body:'<div class="music-machine"></div>'});});
  for(const location of ['http://localhost:1234/',url.replace('doug-anthony-allstars','another-machine')]){
   await page.goto(location);await page.addScriptTag({content:source});
  }await page.waitForTimeout(50);assert.equal(posts,1);
 await page.evaluate(()=>document.querySelector('.music-machine').dataset.machineState='SPINNING');
 await page.waitForTimeout(100);assert.equal(posts,2);
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
  assert.equal(posts,2);assert.equal(reads,1);
  await page.evaluate(()=>document.querySelector('.music-machine').dataset.machineState='IDLE');await page.waitForTimeout(20);
  accepted=true;fail=true;
  await page.evaluate(()=>document.querySelector('.music-machine').dataset.machineState='SPINNING');
  await page.waitForFunction(()=>document.querySelector('[data-spin-counter]').hidden);
  assert.equal(reads,2);assert.equal(posts,3);
 }finally{await browser.close();}
});

test('all machine actions are delegated once, private-safe, and CTA destinations are not mislabeled Spotify',async()=>{
 const browser=await chromium.launch();try{
  for(const slug of ['business','music','tourism','banjo','channel-master','white-label','love-my-locals','football','trivia-machine']){
   const page=await browser.newPage(),events=[];
   await page.route('**/*',r=>{
    if(r.request().method()==='POST'){events.push(r.request().postDataJSON());return r.fulfill({status:204});}
    if(r.request().url().endsWith('/machine.json'))return r.fulfill({json:{customerConfig:{primaryAction:{destinationURL:'https://example.com/tickets'}}}});
    if(r.request().url().includes('/api/spins'))return r.fulfill({json:{count:7}});
    return r.fulfill({contentType:'text/html',body:'<main class="music-machine" data-machine-state="IDLE"><section class="machine-controls"><button data-action="play"><b>Play</b></button><button data-action="share">Share</button><button data-action="shop">Tickets</button></section><a class="secondary-cta">CTA 2</a><section data-channel-master-contact><a>Contact</a></section><a data-football-membership>Membership</a><button data-action="watch-video">Watch</button></main>'});
   });
   await page.goto(url.replace('doug-anthony-allstars',slug));
   await page.evaluate(()=>{window.CrispyBitsMachine={getState:()=>({selectedId:'6waA8RXdDB8'})};});
   await page.addScriptTag({content:source});await page.addScriptTag({content:source});
   for(const selector of ['[data-action="play"] b','[data-action="share"]','[data-action="shop"]','.secondary-cta','[data-channel-master-contact] a','[data-football-membership]','[data-action="watch-video"]'])await page.locator(selector).click();
   await page.waitForTimeout(100);
   assert.deepEqual(events.map(e=>e.name).sort(),['page_view','play_click','play_click','share_click','cta_click','cta2_click','contact_click','membership_click'].sort());
   assert.ok(events.every(e=>e.slug===slug && e.videoId==='6waA8RXdDB8'));
   assert.ok(events.every(e=>Object.keys(e).sort().join(',')==='eventId,name,sessionId,slug,videoId'));
   assert.equal(new Set(events.map(e=>e.eventId)).size,events.length);
   const before=events.length;
   await page.evaluate(()=>{for(const e of document.querySelectorAll('button,a')){e.setAttribute('aria-disabled','true');e.click()}});
   await page.waitForTimeout(50);assert.equal(events.length,before);
   await page.close();
  }
 }finally{await browser.close()}
});

test('Football club CTA isolation and dynamically-added controls; failed metadata uses generic CTA',async()=>{
 const browser=await chromium.launch();try{
  const page=await browser.newPage(),events=[];
  await page.route('**/*',r=>{
   if(r.request().method()==='POST'){events.push(r.request().postDataJSON());return r.fulfill({status:204});}
   if(r.request().url().endsWith('/machine.json'))return r.fulfill({json:{footballConfig:{clubs:[{id:'a',ctaUrl:'https://open.spotify.com/artist/test'},{id:'b',ctaUrl:'https://example.com/shop'}]}}});
   if(r.request().url().includes('/api/spins'))return r.fulfill({json:{count:2}});
   return r.fulfill({contentType:'text/html',body:'<main class="music-machine"><button data-club-id="a">A</button><button data-club-id="b">B</button><button data-football-back>Back</button><button data-action="shop">CTA</button></main>'});
  });
  await page.goto(url.replace('doug-anthony-allstars','football'));await page.addScriptTag({content:source});
  for(const club of ['a','b','a']){await page.locator(`[data-club-id="${club}"]`).click();await page.locator('[data-action="shop"]').click();}
  await page.waitForTimeout(50);assert.deepEqual(events.filter(e=>e.name.endsWith('_click')).map(e=>e.name),['spotify_click','cta_click','spotify_click']);
  await page.evaluate(()=>{const a=document.createElement('a');a.className='secondary-cta';a.textContent='New CTA';document.querySelector('main').append(a)});
  await page.locator('.secondary-cta').click();await page.waitForTimeout(50);assert.equal(events.at(-1).name,'cta2_click');
  await page.route('**/machine.json',r=>r.fulfill({status:503}));await page.reload();await page.addScriptTag({content:source});
  await page.locator('[data-action="shop"]').click();await page.waitForTimeout(50);assert.equal(events.at(-1).name,'cta_click');
 }finally{await browser.close()}
});
