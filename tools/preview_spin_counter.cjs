// Local-only visual QA: all requests are intercepted; count is illustrative.
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'../build/spin-counter-preview');
 const browser=await chromium.launch();
 try{
  for(const width of [390,1320]){
   const page=await browser.newPage({viewport:{width,height:width===390?844:900},reducedMotion:'reduce'});
   await page.route('**/*',async r=>{
    const url=new URL(r.request().url());
    if(url.pathname==='/api/spins')return r.fulfill({json:{count:12345}});
    if(url.pathname==='/api/events')return r.fulfill({status:204});
    if(url.hostname!=='raggedya.github.io')return r.fulfill({body:''});
    const relative=url.pathname.replace('/aggits-video-jukebox/crispy-bits/doug-anthony-allstars/','')||'index.html';
    const file=path.resolve(root,relative);
    if(!file.startsWith(root+path.sep)||!fs.existsSync(file))return r.fulfill({status:404,body:''});
    const types={'.js':'text/javascript','.css':'text/css','.html':'text/html','.json':'application/json','.png':'image/png','.webp':'image/webp','.woff2':'font/woff2'};
    return r.fulfill({contentType:types[path.extname(file)]||'application/octet-stream',body:fs.readFileSync(file)});
   });
   await page.goto('https://raggedya.github.io/aggits-video-jukebox/crispy-bits/doug-anthony-allstars/');
   await page.locator('[data-spin-counter]').waitFor({state:'visible'});
   await page.evaluate(()=>document.fonts.ready);
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   const controls=await page.locator('.machine-controls').boundingBox();
   const counter=await page.locator('[data-spin-counter]').boundingBox();
   assert.ok(counter.y>=controls.y+controls.height);
   await page.screenshot({path:path.join(root,`counter-${width}.png`),fullPage:true});
   console.log(`PASS ${width}: counter below controls; no overflow; mocked count 12,345`);
   await page.close();
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
