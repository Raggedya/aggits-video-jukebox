const {test,before,after}=require('node:test');
const assert=require('node:assert/strict'),http=require('node:http'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
let browser,server,origin;
const root=path.resolve(__dirname,'../build/cta2-preview');
before(async()=>{
 server=http.createServer((req,res)=>{
  const relative=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
  const file=path.resolve(root,'.'+relative+(relative.endsWith('/')?'index.html':''));
  if(!file.startsWith(root+path.sep)||!fs.existsSync(file)){res.writeHead(404);return res.end();}
  res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.png':'image/png','.webp':'image/webp'})[path.extname(file)]||'application/octet-stream');res.end(fs.readFileSync(file));
 });await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));origin=`http://127.0.0.1:${server.address().port}`;browser=await chromium.launch();
});
after(async()=>{await browser?.close();await new Promise(resolve=>server?.close(resolve));});
for(const width of [320,390,1320])test(`CTA 2 placement, sizing, safe link and pulse ${width}`,async()=>{
 const page=await browser.newPage({viewport:{width,height:width===1320?900:844}});
 await page.route('https://**/*',r=>r.fulfill({body:''}));
 await page.goto(origin+'/enabled/');await page.evaluate(()=>document.fonts.ready);
 const button=page.locator('.secondary-cta');await button.waitFor();
 assert.equal(await button.getAttribute('href'),'https://example.com/cta2');
 assert.equal(await button.getAttribute('rel'),'noopener noreferrer');assert.equal(await button.getAttribute('target'),'_blank');
 assert.equal(await page.locator('.machine-controls button').count(),4);
 const b=await button.boundingBox(),card=await page.locator('.content-card').boundingBox(),controls=await page.locator('.machine-controls').boundingBox();
 assert.ok(b.height>=44);assert.ok(b.x>=card.x&&b.x+b.width<=card.x+card.width+1);assert.ok(b.y+b.height<=card.y+card.height+1);assert.ok(card.y+card.height<=controls.y);
 const copy=await page.locator('.content-copy').boundingBox();
 assert.ok(b.x>=copy.x+copy.width-1,'CTA 2 must stay to the right of the information text');
 assert.ok(b.y<copy.y+copy.height&&b.y+b.height>copy.y,'CTA 2 must never stack below the text');
 assert.equal(await page.locator('.content-card').evaluate(e=>getComputedStyle(e).flexWrap),'nowrap');
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 assert.equal(await button.evaluate(e=>getComputedStyle(e,'::after').animationDuration),'15s');
 await button.focus();assert.notEqual(await button.evaluate(e=>getComputedStyle(e).outlineStyle),'none');
 await button.evaluate(e=>e.blur());
 await page.screenshot({path:path.join(root,`cta2-${width}.png`),fullPage:true});
 await page.emulateMedia({reducedMotion:'reduce'});assert.equal(await button.evaluate(e=>getComputedStyle(e,'::after').animationName),'none');
 await page.goto(origin+'/disabled/');assert.equal(await page.locator('.secondary-cta,[data-cta2]').count(),0);
 await page.close();
});

test('primary and secondary borders alternate with two quiet gaps; disabled and reduced-motion remain quiet',async()=>{
 const page=await browser.newPage();await page.route('https://**/*',r=>r.fulfill({body:''}));
 await page.goto(origin+'/enabled/');await page.locator('.secondary-cta').waitFor();
 const samples=await page.evaluate(()=>{
  const primary=document.querySelector('[data-action="shop"]'),secondary=document.querySelector('.secondary-cta');
  const animations=document.getAnimations().filter(a=>['primary-cta-pulse','secondary-cta-pulse'].includes(a.animationName));
  if(animations.length!==2)throw Error('Expected two synchronized border animations');
  animations.forEach(a=>a.pause());
  return [0,2500,6000,7500,10000,14000,17500].map(time=>{
   animations.forEach(a=>a.currentTime=time);
   return [Number(getComputedStyle(primary,'::after').opacity),Number(getComputedStyle(secondary,'::after').opacity)];
  });
 });
 for(const index of [0,2,3,5])assert.ok(samples[index].every(v=>v<.01));
 for(const index of [1,6])assert.ok(samples[index][0]>.6&&samples[index][1]<.01);
 assert.ok(samples[4][1]>.6&&samples[4][0]<.01);
 const primary=page.locator('[data-action="shop"]');
 await primary.evaluate(e=>e.disabled=true);
 assert.equal(await primary.evaluate(e=>getComputedStyle(e,'::after').visibility),'hidden');
 await page.emulateMedia({reducedMotion:'reduce'});
 for(const selector of ['.secondary-cta','[data-action="shop"]'])assert.equal(await page.locator(selector).evaluate(e=>getComputedStyle(e,'::after').animationName),'none');
 await page.goto(origin+'/disabled/');assert.equal(await primary.evaluate(e=>getComputedStyle(e,'::after').animationName),'none');
 await page.close();
});
