// Local browser QA. Remote YouTube is stubbed: fixtures are NOT real club content.
const {test, before, after} = require('node:test');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../build/football-preview');
let server, browser, origin;
for(const width of [390,1320]) test(`Padded logo prominence in grid and circle ${width}`,async()=>{
  const page=await browser.newPage({viewport:{width,height:width===390?844:900},reducedMotion:'reduce'});
  await mockPlayer(page);
  await page.route('https://**/*',r=>r.fulfill({body:'TEST PLAYER'}));
  await page.route('**/machine.json',async r=>{
    const data=await (await r.fetch()).json();
    data.footballConfig.clubs.forEach((club,i)=>{
      club.logo=`assets/football-logo-${i?'ccc':'aaa'}.png`;
      club.logoLayout={width:512,height:512,bounds:i?[96,146,320,220]:[59,44,394,424]};
    });await r.fulfill({json:data});
  });
  await page.route('**/football-logo-*.png',r=>r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512"><rect x="100" y="150" width="310" height="210" fill="white"/></svg>'}));
  await page.goto(origin+'/two-club-test/site/');
  await page.waitForFunction(()=>[...document.querySelectorAll('.football-grid img')].every(i=>i.naturalWidth===512));
  assert.equal(await page.locator('.football-grid img').count(),2);
  const crows=await page.locator('.football-grid .football-logo-art').nth(1).boundingBox();
  const slot=await page.locator('.football-grid .football-logo-slot').nth(1).boundingBox();
  assert.ok(crows.width>100); // Previously the mark occupied only ~50px of an 80px image.
  assert.ok(crows.width<=slot.width && crows.height<=slot.height);
  for(const index of [0,1]){
    await page.locator('[data-club-id]').nth(index).click();
    await page.waitForFunction(()=>document.querySelector('[data-football-logo]').naturalWidth===512);
    const art=await page.locator('.football-logo-slot--hero .football-logo-art').boundingBox();
    const circle=await page.locator('.football-medallion').boundingBox();
    assert.ok(Math.hypot(art.width,art.height)<circle.width-6);
    assert.ok(Math.hypot(art.width,art.height)>circle.width*.8);
    if(index===1)assert.ok(art.width>circle.width*.65);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.locator('[data-football-back]').click();
  }await page.close();
});
for (const width of [320,390,1320]) test(`Symmetric membership identity and club isolation ${width}`, async()=>{
  const page=await browser.newPage({viewport:{width,height:width===1320?900:844},reducedMotion:'reduce'});
  await mockPlayer(page);
  await page.route('https://**/*',r=>r.fulfill({body:'TEST PLAYER'}));
  await page.route('**/machine.json',async r=>{
    const data=await (await r.fetch()).json();
    data.footballConfig.clubs.forEach((club,i)=>{
      club.membershipUrl=`https://example.com/membership-${i}`;
      club.logo=`assets/football-logo-${i?'bbb':'aaa'}.png`;
      club.baseColour=i?'#ffffff':'#001b37';
      club.primaryColour=i?'#ffdd00':'#245c9e';
      club.highlightColour=i?'#000000':'#ffffff';
    });
    await r.fulfill({json:data});
  });
  // Deliberately non-club test artwork: both wide and portrait images include edge text.
  await page.route('**/football-logo-*.png',r=>{
    const wide=r.request().url().includes('aaa');
    const w=wide?300:100,h=wide?100:300;
    r.fulfill({contentType:'image/svg+xml',body:`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}"><rect x="1" y="1" width="${w-2}" height="${h-2}" fill="white" stroke="black"/><text x="3" y="20" font-size="12">TEST LOGO</text><text x="3" y="${h-8}" font-size="12">FULL WORDING</text></svg>`});
  });
  await page.goto(origin+'/two-club-test/site/');
  for(const index of [0,1,0]){
    await page.locator('[data-club-id]').nth(index).click();
    const links=page.locator('[data-football-membership]');
    const boxes=await Promise.all([links.nth(0).boundingBox(),links.nth(1).boundingBox()]);
    const badge=await page.locator('.football-medallion').boundingBox();
    const logo=await page.locator('.football-logo-slot--hero .football-logo-art').boundingBox();
    assert.ok(Math.abs(boxes[0].width-boxes[1].width)<1);
    assert.equal(boxes[0].height,boxes[1].height);
    assert.deepEqual(await links.evaluateAll(nodes=>nodes.map(e=>getComputedStyle(e).backgroundImage)),
      Array(2).fill(await links.first().evaluate(e=>getComputedStyle(e).backgroundImage)));
    assert.ok(boxes.every(b=>b.height>=44 && b.width>=44));
    assert.ok(Math.abs((boxes[0].x+boxes[0].width+boxes[1].x)/2-(badge.x+badge.width/2))<1);
    assert.ok(Math.hypot(logo.width,logo.height)<badge.width-6);
    assert.equal(await page.locator('[data-football-logo]').evaluate(e=>getComputedStyle(e).objectFit),'contain');
    for(const link of await links.all()){
      assert.equal(await link.getAttribute('href'),`https://example.com/membership-${index}`);
      assert.equal(await link.getAttribute('rel'),'noopener noreferrer');
      assert.equal(await link.getAttribute('target'),'_blank');
      assert.equal(await link.getAttribute('aria-label'),'Become a Member');
      assert.equal(await link.evaluate(e=>e.scrollWidth<=e.clientWidth),true);
      assert.equal(await link.locator('span').evaluate(e=>getComputedStyle(e).borderBottomColor),index?'rgb(0, 0, 0)':'rgb(255, 255, 255)');
    }
    assert.equal(await page.locator('.music-machine').evaluate(e=>e.style.getPropertyValue('--football-base')),index?'#ffffff':'#001b37');
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.screenshot({path:path.resolve(__dirname,`../build/football-preview/membership-${width}-${index}.png`),fullPage:true});
    await page.locator('[data-football-back]').click();
    assert.equal(await links.nth(0).getAttribute('href'),null);
    assert.equal(await links.nth(1).getAttribute('href'),null);
  }
  await page.close();
});
test('Absent and unsafe membership links hide both buttons',async()=>{
  for(const value of ['', 'javascript:alert(1)', 'https://user:pass@example.com', 'https://bad host/']){
    const page=await browser.newPage();
    await mockPlayer(page);
    await page.route('https://**/*',r=>r.fulfill({body:'TEST PLAYER'}));
    await page.route('**/machine.json',async r=>{
      const data=await (await r.fetch()).json();data.footballConfig.clubs[0].membershipUrl=value;await r.fulfill({json:data});
    });
    await page.goto(origin+'/test-fixture/site/');await page.locator('[data-club-id]').click();
    for(const link of await page.locator('[data-football-membership]').all()){
      assert.equal(await link.isVisible(),false);assert.equal(await link.getAttribute('href'),null);
    }
    await page.close();
  }
});
async function mockPlayer(page) {
  await page.addInitScript(() => {
    window.YT = {Player: class {
      constructor(frame, options) { window.qaPlayerOptions = options; window.qaPlayerFrame = frame; queueMicrotask(()=>options.events.onReady?.()); }
      playVideo() { window.postMessage({qaCommand:'playVideo'},'*'); }
      destroy() {}
    }};
  });
}
before(async () => {
  server = http.createServer((req, res) => {
    let file = path.resolve(root, '.' + decodeURIComponent(req.url.split('?')[0]));
    if (!file.startsWith(root + path.sep)) { res.writeHead(403).end(); return; }
    if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
    if (!fs.existsSync(file)) { res.writeHead(404).end(); return; }
    const type = {'.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.json':'application/json', '.png':'image/png', '.webp':'image/webp', '.mp3':'audio/mpeg'}[path.extname(file)] || 'application/octet-stream';
    res.setHeader('Content-Type', type);
    fs.createReadStream(file).pipe(res);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  origin = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({headless:true});
});
after(async () => { await browser?.close(); await new Promise(resolve => server.close(resolve)); });

test('Football validates IDs/URLs and canonical embed parameters', async () => {
  const page = await browser.newPage();
  await mockPlayer(page);
  await page.goto(origin+'/test-fixture/site/');
  const result = await page.evaluate(async () => {
    const {footballVideoUrl, youtubeId} = await import('./assets/football-video.js');
    const id = '6waA8RXdDB8';
    return {
      valid: footballVideoUrl({videoId:id, url:`https://youtu.be/${id}`}, location.origin),
      invalid: ['', 'short', '<script>123'].map(videoId=>footballVideoUrl({videoId},location.origin)),
      mismatch: footballVideoUrl({videoId:id,embedUrl:'https://youtube.com/embed/M7lc1UVf-VE'},location.origin),
      unsafe: ['javascript:alert(1)', 'https://youtube.com.evil.test/watch?v='+id].map(youtubeId)
    };
  });
  assert.match(result.valid,/^https:\/\/www.youtube.com\/embed\/6waA8RXdDB8\?/);
  const url = new URL(result.valid);
  assert.equal(url.searchParams.get('autoplay'),'0');
  assert.equal(url.searchParams.get('enablejsapi'),'1');
  assert.equal(url.searchParams.get('origin'),origin);
  assert.deepEqual(result.invalid,['','','']);
  assert.equal(result.mismatch,'');
  assert.deepEqual(result.unsafe,['','']);
  await page.close();
});

test('Play waits for YouTube ready; invalid catalogue records are excluded', async () => {
  const page = await browser.newPage({reducedMotion:'reduce'});
  await page.addInitScript(()=>{
    window.qaPlays=0;
    window.YT={Player:class {
      constructor(frame,options){window.qaReady=options.events.onReady;}
      playVideo(){window.qaPlays++;}
      destroy(){}
    }};
  });
  await page.route('https://**/*',route=>route.fulfill({body:'TEST PLAYER'}));
  await page.route('**/machine.json',async route=>{
    const data=await (await route.fetch()).json();
    data.footballConfig.clubs[0].videos.push({videoId:'invalid',url:'javascript:alert(1)'});
    await route.fulfill({json:data});
  });
  await page.goto(origin+'/test-fixture/site/');
  await page.locator('[data-club-id]').click();
  await page.waitForFunction(()=>window.CrispyBitsMachine.getState().state==='VIDEO_READY');
  assert.notEqual(await page.evaluate(()=>window.CrispyBitsMachine.getState().selectedId),'invalid');
  assert.equal(await page.evaluate(()=>window.qaPlays),0);
  await page.locator('[data-action="play"]').click();
  assert.equal(await page.evaluate(()=>window.qaPlays),0);
  await page.evaluate(()=>window.qaReady());
  assert.equal(await page.evaluate(()=>window.qaPlays),1);
  await page.close();
});

test('Embed waits for API error listeners; initial failure is cleared with fallback', async () => {
  const page = await browser.newPage({reducedMotion:'reduce'});
  let apiRoute;
  await page.route('https://www.youtube.com/iframe_api', route=>{apiRoute=route;});
  await page.route('https://www.youtube.com/embed/**', route=>route.fulfill({body:'UNAVAILABLE TEST'}));
  await page.goto(origin+'/test-fixture/site/');
  await page.locator('[data-club-id]').click();
  await page.waitForFunction(()=>document.querySelector('script[src="https://www.youtube.com/iframe_api"]'));
  assert.equal(await page.locator('[data-youtube-player]').getAttribute('src'),'about:blank');
  await page.evaluate(()=>{
    window.YT={Player:class {
      constructor(frame,options){queueMicrotask(()=>options.events.onError({data:150}));}
      destroy(){}
    }};
    window.onYouTubeIframeAPIReady();
  });
  await page.waitForFunction(()=>window.CrispyBitsMachine.getState().state==='VIDEO_UNAVAILABLE');
  assert.equal(await page.locator('[data-youtube-player]').getAttribute('src'),'about:blank');
  assert.equal(await page.locator('.football-video-error a').isVisible(),true);
  assert.equal(await page.locator('[data-action="spin-again"]').isEnabled(),true);
  await apiRoute?.fulfill({contentType:'text/javascript',body:'/* mocked API */'});
  await page.close();
});

for (const width of [390,1320]) test(`Football YouTube errors and lever recovery ${width}`, async () => {
  const page = await browser.newPage({viewport:{width,height:width===390?844:900},reducedMotion:'reduce'});
  await mockPlayer(page);
  await page.route('https://**/*',route=>route.fulfill({body:'MOCK YOUTUBE'}));
  await page.goto(origin+'/test-fixture/site/');
  await page.locator('[data-club-id]').click();
  for (const code of [2,5,100,101,150,153]) {
    await page.waitForFunction(()=>window.CrispyBitsMachine.getState().state==='VIDEO_READY');
    const before = await page.evaluate(()=>window.CrispyBitsMachine.getState().selectedId);
    await page.evaluate(code=>window.qaPlayerOptions.events.onError({data:code}), code);
    assert.equal(await page.locator('[data-youtube-player]').getAttribute('src'),'about:blank');
    assert.equal(await page.locator('.football-video-error').isVisible(),true);
    assert.equal(await page.locator('.football-video-error a').getAttribute('href'),`https://www.youtube.com/watch?v=${before}`);
    assert.equal(await page.locator('[data-action="play"]').isDisabled(),true);
    assert.equal(await page.locator('.lever').isEnabled(),true);
    assert.equal(await page.evaluate(()=>window.CrispyBitsMachine.getState().selectedId),before);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.locator('[data-action="spin-again"]').click();
    await page.waitForFunction(id=>window.CrispyBitsMachine.getState().state==='VIDEO_READY' && window.CrispyBitsMachine.getState().selectedId!==id,before);
    assert.equal(await page.locator('.football-video-error').isVisible(),false);
    assert.match(await page.locator('[data-youtube-player]').getAttribute('src'),/autoplay=0/);
  }
  await page.evaluate(()=>{window.staleError=window.qaPlayerOptions.events.onError;});
  await page.locator('[data-football-back]').click();
  await page.evaluate(()=>window.staleError({data:100}));
  assert.equal(await page.locator('.football-video-error').isVisible(),false);
  assert.equal(await page.evaluate(()=>window.CrispyBitsMachine.getState().state),'CHOOSE_CLUB');
  await page.close();
});

for (const viewport of [{width:390,height:844}, {width:1320,height:900}]) {
  test(`Configured eighteen-club roster grid ${viewport.width}`, async () => {
    const page = await browser.newPage({viewport,reducedMotion:'reduce'});
    await mockPlayer(page);
    await page.goto(origin+'/eighteen-club-test/site/');
    await page.waitForFunction(()=>window.CrispyBitsMachine?.getState().state==='CHOOSE_CLUB');
    assert.equal(await page.locator('[data-club-id]').count(),18);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.screenshot({path:path.join(root,`eighteen-grid-${viewport.width}.png`),fullPage:true});
    await page.locator('[data-club-id="test-club-18"]').click();
    await page.waitForFunction(()=>window.CrispyBitsMachine.getState().state==='VIDEO_READY');
    assert.equal(await page.locator('[data-football-name]').textContent(),'TEST ONLY CLUB 18');
    const selected = await page.evaluate(()=>window.CrispyBitsMachine.getState().selectedId);
    assert.ok(['master00170','master00171','master00172'].includes(selected));
    assert.equal(await page.locator('.music-machine').evaluate(el=>el.style.getPropertyValue('--football-primary')),'#703050');
    await page.locator('[data-football-back]').click();
    assert.equal(await page.locator('[data-club-id]').count(),18);
    await page.locator('[data-club-id="north-melbourne"]').click();
    await page.waitForFunction(()=>window.CrispyBitsMachine.getState().state==='VIDEO_READY');
    assert.match(await page.evaluate(()=>window.CrispyBitsMachine.getState().selectedId),/^master0000[0-2]$/);
    await page.close();
  });
  test(`Football club selection, controls, reset and layout ${viewport.width}`, async () => {
    const context = await browser.newContext({viewport});
    const page = await context.newPage();
    await mockPlayer(page);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await context.route('https://**/*', route => route.fulfill({contentType:'text/html; charset=utf-8', body:'<html><body style="background:#081426;color:#f7e6bf;display:grid;place-items:center;height:90vh;font:16px sans-serif">PLAYER TEST FIXTURE - NOT CLUB CONTENT<script>addEventListener("message",event=>{try{parent.postMessage({qaCommand:JSON.parse(event.data).func},"*")}catch{}})</script></body></html>'}));
    await page.goto(origin + '/test-fixture/site/');
    await page.waitForFunction(() => window.CrispyBitsMachine?.getState().state === 'CHOOSE_CLUB');
    assert.equal(await page.locator('[data-club-id]').count(), 1);
    assert.equal(await page.locator('[data-reel] strong').textContent(), 'CHOOSE YOUR CLUB');
    assert.equal(await page.locator('.lever').isVisible(), false);
    await page.screenshot({path:path.join(root, `grid-${viewport.width}.png`), fullPage:true});
    await page.locator('[data-club-id="north-melbourne"]').click();
    await page.waitForFunction(() => window.CrispyBitsMachine.getState().state === 'VIDEO_READY');
    const first = await page.evaluate(() => window.CrispyBitsMachine.getState().selectedId);
    const frame = await page.locator('[data-youtube-player]').getAttribute('src');
    assert.match(frame, /autoplay=0/);
    assert.match(frame, new RegExp(first));
    assert.equal(await page.locator('[data-football-name]').textContent(), 'North Melbourne');
    assert.equal(await page.locator('.lever').isVisible(), true);
    assert.equal(await page.locator('.lever').isEnabled(), true);
    assert.equal(await page.locator('.football-maker').isVisible(), false);
    const tickerBox = await page.locator('.football-ticker').boundingBox();
    const reelBox = await page.locator('.reel-and-lever').boundingBox();
    assert.ok(tickerBox.y + tickerBox.height <= reelBox.y);
    assert.equal(await page.locator('.football-identity h2').count(), 0);
    const plaque = await page.locator('[data-football-name]').boundingBox();
    assert.ok(Math.abs(plaque.x + plaque.width / 2 - (reelBox.x + reelBox.width / 2)) < 2);
    assert.ok(plaque.y >= reelBox.y + reelBox.height - 40);
    assert.equal(await page.locator('[data-football-name]').evaluate(el=>getComputedStyle(el).textTransform), 'uppercase');
    assert.match(await page.locator('[data-football-ticker]').textContent(), /TEST FIXTURE/);
    assert.equal(await page.locator('[data-action="shop"] b').textContent(), 'Visit club');
    assert.equal(await page.locator('[data-football-no-logo]').isVisible(), true);
    assert.equal(await page.locator('.music-machine').evaluate(el => el.style.getPropertyValue('--football-primary')), '#005EB8');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.equal(await page.locator('[data-action="play"]').isEnabled(), true);
    await page.evaluate(() => {
      window.qaCommands = [];
      addEventListener('message', event => { if (event.data?.qaCommand) window.qaCommands.push(event.data.qaCommand); });
      window.open = url => { window.qaDestination = url; };
    });
    await page.locator('[data-action="play"]').click();
    await page.waitForFunction(() => window.qaCommands.includes('playVideo'));
    await page.locator('[data-action="shop"]').click();
    assert.equal(await page.evaluate(() => window.qaDestination), 'https://example.com/club');
    // Capture the shared flow, without triggering a native share sheet.
    await page.evaluate(() => Object.defineProperty(navigator, 'share', {configurable:true, value:async data => {window.shared = data;}}));
    await page.locator('[data-action="share"]').click();
    assert.equal(await page.evaluate(() => window.shared.url), `https://www.youtube.com/watch?v=${first}`);
    await page.screenshot({path:path.join(root, `club-${viewport.width}.png`), fullPage:true});
    // Real pointer pull through the existing resistance/trigger mechanism.
    await page.evaluate(()=>{window.qaCommands=[];});
    await page.locator('.lever').scrollIntoViewIfNeeded();
    const leverBox = await page.locator('.lever').boundingBox();
    await page.mouse.move(leverBox.x + leverBox.width / 2, leverBox.y + leverBox.height / 2);
    await page.mouse.down();
    await page.mouse.move(leverBox.x + leverBox.width / 2, leverBox.y + leverBox.height / 2 + 130, {steps:8});
    await page.mouse.up();
    await page.waitForFunction(previous => !window.CrispyBitsMachine.getState().spinning && window.CrispyBitsMachine.getState().selectedId !== previous, first);
    assert.notEqual(await page.evaluate(() => window.CrispyBitsMachine.getState().selectedId), first);
    await page.waitForFunction(()=>window.CrispyBitsMachine.getState().state==='VIDEO_READY');
    assert.match(await page.locator('[data-youtube-player]').getAttribute('src'),/autoplay=0/);
    assert.equal(await page.evaluate(()=>window.qaCommands.includes('playVideo')),false);
    await page.locator('[data-action="play"]').click();
    await page.waitForFunction(()=>window.qaCommands.includes('playVideo'));
    // Back while the automatic reveal is pending.
    await page.locator('[data-football-back]').click();
    await page.waitForTimeout(1300);
    assert.equal(await page.locator('[data-youtube-player]').getAttribute('src'), 'about:blank');
    assert.equal(await page.evaluate(() => window.CrispyBitsMachine.getState().selectedId), null);
    assert.equal(await page.locator('[data-reel] strong').textContent(), 'CHOOSE YOUR CLUB');
    // Back during the reel animation also leaves a stationary clean grid.
    await page.locator('[data-club-id]').click();
    await page.waitForFunction(() => window.CrispyBitsMachine.getState().state === 'VIDEO_READY');
    await page.locator('[data-action="spin-again"]').click();
    await page.waitForFunction(() => window.CrispyBitsMachine.getState().state === 'SPINNING');
    await page.locator('[data-football-back]').click();
    await page.waitForTimeout(2800);
    assert.equal(await page.locator('[data-reel] strong').textContent(), 'CHOOSE YOUR CLUB');
    assert.equal(await page.evaluate(() => window.CrispyBitsMachine.getState().spinning), false);
    assert.equal(await page.locator('[data-youtube-player]').getAttribute('src'), 'about:blank');
    assert.deepEqual(errors, []);
    await context.close();
  });
}

test('Imported logo replaces top branding; keyboard lever and rapid Back cancel safely', async () => {
  const page = await browser.newPage({viewport:{width:390,height:844},reducedMotion:'reduce'});
  await mockPlayer(page);
  await page.route('**/machine.json', async route => {
    const response = await route.fetch();
    const data = await response.json();
    data.footballConfig.clubs[0].logo = 'assets/football-logo-abc.png';
    await route.fulfill({json:data});
  });
  // Transparent test pixel, not a club logo or production content.
  await page.route('**/football-logo-abc.png', route=>route.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=','base64')}));
  await page.route('https://**/*',route=>route.fulfill({body:'TEST PLAYER ONLY'}));
  await page.goto(origin+'/test-fixture/site/');
  await page.locator('[data-club-id]').click();
  await page.waitForFunction(()=>window.CrispyBitsMachine.getState().state==='VIDEO_READY');
  assert.equal(await page.locator('[data-football-logo]').isVisible(),true);
  assert.match(await page.locator('[data-football-logo]').getAttribute('src'),/football-logo-abc.png$/);
  assert.equal(await page.locator('.football-maker').isVisible(),false);
  const logo = await page.locator('.football-logo-slot--hero .football-logo-art').boundingBox();
  const badge = await page.locator('.football-medallion').boundingBox();
  assert.ok(badge.width >= 112);
  assert.ok(Math.abs(logo.width-logo.height)<1);
  assert.ok(Math.hypot(logo.width,logo.height) < badge.width - 4);
  assert.equal(await page.locator('[data-football-logo]').evaluate(el=>getComputedStyle(el).objectFit), 'contain');
  const ticker = await page.locator('.football-ticker').boundingBox();
  assert.ok(logo.y+logo.height <= ticker.y);
  // Trigger delayed lever animation and leave before its callback can spin.
  await page.locator('.lever').focus();
  await page.keyboard.press('Enter');
  await page.locator('[data-football-back]').click();
  await page.waitForTimeout(800);
  assert.equal(await page.evaluate(()=>window.CrispyBitsMachine.getState().state),'CHOOSE_CLUB');
  assert.equal(await page.locator('[data-youtube-player]').getAttribute('src'),'about:blank');
  assert.equal(await page.locator('[data-football-logo]').getAttribute('src'),null);
  await page.close();
});

test('Missing real club content is explicit and can return to the grid', async () => {
  const page = await browser.newPage({viewport:{width:390,height:844}});
  await mockPlayer(page);
  await page.goto(origin + '/north-melbourne/site/');
  await page.locator('[data-club-id]').click();
  await page.waitForFunction(() => window.CrispyBitsMachine.getState().state === 'EMPTY_CLUB');
  assert.equal(await page.locator('[data-action="play"]').isEnabled(), false);
  assert.equal(await page.locator('[data-action="shop"]').isEnabled(), false);
  assert.match(await page.locator('[data-winner-title]').textContent(), /NOT SUPPLIED/);
  await page.locator('[data-football-back]').click();
  assert.equal(await page.locator('[data-football-grid]').isVisible(), true);
  await page.close();
});

for (const viewport of [{width:390,height:844}, {width:1320,height:900}]) {
  test(`Two-club isolation A → B → A at ${viewport.width}`, async () => {
    const context = await browser.newContext({viewport, reducedMotion:'reduce'});
    const page = await context.newPage();
    await mockPlayer(page);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(origin + '/two-club-test/site/');
    await page.waitForFunction(() => window.CrispyBitsMachine?.getState().state === 'CHOOSE_CLUB');
    const data = await page.evaluate(async () => (await fetch('machine.json')).json());
    const [a,b] = data.footballConfig.clubs;
    assert.equal(await page.locator('[data-club-id]').count(), 2);
    await page.evaluate(() => {
      Object.defineProperty(navigator, 'share', {configurable:true,value:async data => {window.shared=data;}});
      window.open = url => {window.destination=url;};
    });
    await page.screenshot({path:path.join(root,`two-grid-${viewport.width}.png`),fullPage:true});
    for (const club of [a,b,a]) {
      await page.locator(`[data-club-id="${club.id}"]`).click();
      await page.waitForFunction(() => window.CrispyBitsMachine.getState().state === 'VIDEO_READY');
      assert.equal(await page.locator('[data-football-name]').textContent(), club.name);
      assert.equal(await page.locator('[data-football-ticker]').textContent(), club.ticker);
      assert.equal(await page.locator('[data-action="shop"] b').textContent(), club.ctaLabel);
      for (const [css,key] of [['base','baseColour'],['primary','primaryColour'],['highlight','highlightColour']])
        assert.equal(await page.locator('.music-machine').evaluate((el,css)=>el.style.getPropertyValue(`--football-${css}`),css),club[key]);
      assert.equal(await page.locator('[data-football-logo]').getAttribute('src'),null);
      assert.equal(await page.locator('[data-football-no-logo]').isVisible(),true);
      assert.equal(await page.locator('.lever').isEnabled(),true);
      const ids = club.videos.map(video=>video.videoId);
      assert.match(await page.locator('[data-youtube-player]').getAttribute('src'), /fixture-player\.html/);
      const first = await page.evaluate(()=>window.CrispyBitsMachine.getState().selectedId);
      assert.ok(ids.includes(first));
      await page.locator('[data-action="shop"]').click();
      assert.equal(await page.evaluate(()=>window.destination),club.ctaUrl);
      await page.locator('[data-action="spin-again"]').click();
      await page.waitForFunction(first=>window.CrispyBitsMachine.getState().state==='VIDEO_READY' && window.CrispyBitsMachine.getState().selectedId!==first,first);
      const next = await page.evaluate(()=>window.CrispyBitsMachine.getState().selectedId);
      assert.ok(ids.includes(next));
      await page.locator('[data-action="share"]').click();
      assert.equal(await page.evaluate(()=>window.shared.url),`https://www.youtube.com/watch?v=${next}`);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth),true);
      await page.screenshot({path:path.join(root,`${club.id}-${viewport.width}.png`),fullPage:true});
      // Leave during a pending spin, then switch immediately: no previous reveal may win.
      await page.locator('[data-action="spin-again"]').click();
      await page.locator('[data-football-back]').click();
      assert.equal(await page.locator('[data-youtube-player]').getAttribute('src'),'about:blank');
      assert.equal(await page.evaluate(()=>window.CrispyBitsMachine.getState().selectedId),null);
      assert.equal(await page.locator('[data-football-ticker]').textContent(),'');
      assert.equal(await page.locator('.music-machine').evaluate(el=>el.style.getPropertyValue('--football-primary')),'');
    }
    await page.waitForTimeout(1500);
    assert.equal(await page.locator('[data-youtube-player]').getAttribute('src'),'about:blank');
    assert.equal(await page.locator('[data-reel] strong').textContent(),'CHOOSE YOUR CLUB');
    assert.equal(await page.locator('.lever').isEnabled(),false);
    assert.equal(await page.locator('.football-maker').isVisible(),true);
    assert.deepEqual(errors,[]);
    await context.close();
  });
}
