// First-party aggregate collection. No advertising identifiers, third-party calls or raw referrers.
export function startAnalytics(config){
 if(!config.analyticsURL||config.publicationEnvironment!=='production'||document.body.dataset.preview)return;
 if(navigator.webdriver&&!config.analyticsTest)return;
 const endpoint=new URL(config.analyticsURL,location.href);if(endpoint.origin!==location.origin)return;
 let ready=false,stopped=false,sending=false,pending=[],last=performance.now(),activeUntil=last+60000,seconds=0,lastShare=-Infinity;
 const starts=new Set(),page=crypto.randomUUID();let generation=0,video=config.videos[0]?.videoId;
 const enqueue=(type,detail={})=>{if(stopped)return;pending.push({id:crypto.randomUUID(),at:Date.now(),type,...detail});if(pending.length>20)pending.shift();if(pending.length>=8)flush();};
 const active=()=>!document.hidden&&document.hasFocus()&&performance.now()<activeUntil;
 function tick(){const t=performance.now(),delta=Math.min((t-last)/1000,2);if(active())seconds+=delta;last=t;}
 function heartbeat(){tick();const whole=Math.min(60,Math.floor(seconds));if(whole){seconds-=whole;enqueue('engagement',{seconds:whole});}flush();}
 async function flush(beacon=false){if(!ready||stopped||sending||!pending.length)return;pending=pending.filter(e=>Date.now()-e.at<9*60000);if(!pending.length)return;const batch=pending.slice(0,20),payload=JSON.stringify({events:batch,releaseId:config.releaseId});
  if(beacon&&navigator.sendBeacon){if(navigator.sendBeacon(endpoint,new Blob([payload],{type:'application/json'})))pending.splice(0,batch.length);return;}
  sending=true;try{const r=await fetch(endpoint,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:payload,keepalive:true});if(r.ok){const value=await r.json();pending=pending.filter(e=>!batch.some(b=>b.id===e.id));if(value.excluded||value.limited){stopped=true;pending=[];}}else if([400,403,410].includes(r.status)){stopped=true;pending=[];}}catch{/* Bounded in-memory retry; navigation and playback remain independent. */}finally{sending=false;}
 }
 document.addEventListener('epicentre:visit-ready',e=>{if(e.detail?.excluded){stopped=true;pending=[];}else{ready=true;flush();}});
 document.addEventListener('splatters-video:playback',e=>{const d=e.detail;if(d.source!=='youtube-iframe-api'||d.state!=='playing')return;const key=page+':'+d.generation+':'+d.videoId;if(starts.has(key))return;starts.add(key);if(starts.size>200)starts.delete(starts.values().next().value);generation=d.generation;video=d.videoId;enqueue('video_start',{video});});
 document.addEventListener('epicentre:next',e=>{enqueue('next',{video:e.detail.videoId});});
 document.addEventListener('splatters-video:video-changed',e=>{video=e.detail.videoId;enqueue('video_selection',{video});});
 document.addEventListener('splatters-video:cta',e=>enqueue('cta',{cta:e.detail.id}));
 document.addEventListener('epicentre:hero-cta',()=>enqueue('hero_cta',{cta:'hero-cta'}));
 document.querySelector('#share')?.addEventListener('click',()=>{if(performance.now()-lastShare>1000){enqueue('share');lastShare=performance.now();}});
 for(const event of ['pointerdown','pointermove','keydown','focusin'])document.addEventListener(event,()=>{tick();activeUntil=performance.now()+60000;},{passive:true});
 document.addEventListener('visibilitychange',()=>{tick();last=performance.now();if(document.hidden)heartbeat();});window.addEventListener('blur',heartbeat);window.addEventListener('pagehide',()=>{heartbeat();flush(true);});
 setInterval(tick,1000);setInterval(heartbeat,60000);window.addEventListener('online',()=>flush());
}
